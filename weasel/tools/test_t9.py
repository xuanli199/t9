# -*- coding: utf-8 -*-
"""
test_t9.py - 九键(T9)方案端到端测试
通过 ctypes 调用 weasel 发布版中的 rime.dll:
  1. 部署全部方案(编译 t9 词典/棱镜/配置)
  2. 创建会话, 模拟按键输入, 验证候选与上屏结果
"""
import ctypes
import os
import re
import sys
import time

RIME_DLL = r"d:\desktop\input\weasel\output\Win32\rime.dll"
SHARED_DIR = r"d:\desktop\input\weasel\output\data"
USER_DIR = r"d:\desktop\input\rime-user"

os.makedirs(USER_DIR, exist_ok=True)

dll = ctypes.CDLL(RIME_DLL)


class RimeTraits(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("shared_data_dir", ctypes.c_char_p),
        ("user_data_dir", ctypes.c_char_p),
        ("distribution_name", ctypes.c_char_p),
        ("distribution_code_name", ctypes.c_char_p),
        ("distribution_version", ctypes.c_char_p),
        ("app_name", ctypes.c_char_p),
        ("modules", ctypes.POINTER(ctypes.c_char_p)),
    ]


class RimeCandidate(ctypes.Structure):
    _fields_ = [
        ("text", ctypes.c_char_p),
        ("comment", ctypes.c_char_p),
        ("reserved", ctypes.c_char_p),
    ]


class RimeMenu(ctypes.Structure):
    _fields_ = [
        ("page_size", ctypes.c_int),
        ("page_no", ctypes.c_int),
        ("is_last_page", ctypes.c_bool),
        ("highlighted_candidate_index", ctypes.c_int),
        ("num_candidates", ctypes.c_int),
        ("candidates", ctypes.POINTER(RimeCandidate)),
        ("select_keys", ctypes.c_char_p),
    ]


class RimeComposition(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_int),
        ("cursor_pos", ctypes.c_int),
        ("sel_start", ctypes.c_int),
        ("sel_end", ctypes.c_int),
        ("preedit", ctypes.c_char_p),
    ]


class RimeCommit(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("text", ctypes.c_char_p),
    ]


def STRUCT_INIT(Struct):
    """RIME_STRUCT_INIT: data_size = sizeof - sizeof(data_size)"""
    return ctypes.sizeof(Struct) - ctypes.sizeof(ctypes.c_int)


class RimeContext(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", ctypes.c_char_p),
        ("select_labels", ctypes.POINTER(ctypes.c_char_p)),
    ]


dll.RimeSetup.argtypes = [ctypes.POINTER(RimeTraits)]
dll.RimeInitialize.argtypes = [ctypes.POINTER(RimeTraits)]
dll.RimeStartMaintenance.argtypes = [ctypes.c_bool]
dll.RimeIsMaintenancing.argtypes = []
dll.RimeJoinMaintenanceThread.argtypes = []
dll.RimeCreateSession.argtypes = []
dll.RimeFindSession.argtypes = [ctypes.c_uint]
dll.RimeDestroySession.argtypes = [ctypes.c_uint]
dll.RimeProcessKey.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_int]
dll.RimeGetContext.argtypes = [ctypes.c_uint, ctypes.POINTER(RimeContext)]
dll.RimeFreeContext.argtypes = [ctypes.POINTER(RimeContext)]
dll.RimeGetCommit.argtypes = [ctypes.c_uint, ctypes.POINTER(RimeCommit)]
dll.RimeFreeCommit.argtypes = [ctypes.POINTER(RimeCommit)]

traits = RimeTraits()
traits.data_size = STRUCT_INIT(RimeTraits)
traits.shared_data_dir = SHARED_DIR.encode("utf-8")
traits.user_data_dir = USER_DIR.encode("utf-8")
traits.distribution_name = b"Weasel T9 Test"
traits.distribution_code_name = b"weasel-t9-test"
traits.distribution_version = b"1.0.0"
traits.app_name = b"rime.weasel-t9-test"

dll.RimeSetup(ctypes.byref(traits))
dll.RimeInitialize(ctypes.byref(traits))

print("=== start maintenance (deploy schemas) ===")
dll.RimeStartMaintenance(True)
t0 = time.time()
while dll.RimeIsMaintenancing():
    time.sleep(1)
    if time.time() - t0 > 900:
        print("TIMEOUT waiting maintenance")
        sys.exit(1)
print("maintenance finished in %.1fs" % (time.time() - t0))

# 检查部署产物
build_dir = os.path.join(USER_DIR, "build")
if os.path.isdir(build_dir):
    files = sorted(os.listdir(build_dir))
    print("build files:", [f for f in files if "t9" in f or f.endswith(".yaml")][:15])
    print("t9.prism.bin exists:", os.path.exists(os.path.join(build_dir, "t9.prism.bin")))
    print("t9.table.bin exists:", os.path.exists(os.path.join(build_dir, "t9.table.bin")))

session = dll.RimeCreateSession()
if not dll.RimeFindSession(session):
    print("ERROR: create session failed")
    sys.exit(1)
print("session created:", session)


def get_context(sess):
    ctx = RimeContext()
    ctx.data_size = STRUCT_INIT(RimeContext)
    if not dll.RimeGetContext(sess, ctypes.byref(ctx)):
        return None
    return ctx


def menu_texts(ctx):
    return [
        ctx.menu.candidates[i].text.decode("utf-8", "replace")
        for i in range(ctx.menu.num_candidates)
    ]


def press(sess, key, mask=0):
    return dll.RimeProcessKey(sess, key, mask)


def clear_composition(sess):
    """用 BackSpace 逐字清空编码 (API 测试环境; 真实环境中 Escape 由 weasel 客户端处理)"""
    XK_BACKSPACE = 0xFF08
    for _ in range(32):
        ctx = get_context(sess)
        if not ctx or not ctx.composition.preedit:
            return
        press(sess, XK_BACKSPACE)


def take_commit(sess):
    commit = RimeCommit()
    commit.data_size = STRUCT_INIT(RimeCommit)
    if dll.RimeGetCommit(sess, ctypes.byref(commit)):
        txt = commit.text.decode("utf-8", "replace") if commit.text else ""
        dll.RimeFreeCommit(ctypes.byref(commit))
        return txt
    return ""


results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("PASS " if cond else "FAIL ") + name + (" | " + detail if detail else ""))


# ---- 测试 1: 输入 96636 (wo men) -> 我們 ----
print("\n=== test 1: 96636 -> 我们 ===")
for ch in "96636":
    press(session, ord(ch))
ctx = get_context(session)
texts = menu_texts(ctx)
preedit = ctx.composition.preedit.decode("utf-8", "replace") if ctx.composition.preedit else ""
print("preedit:", preedit, "candidates:", texts)
check("96636 首选=我们", texts[0] == "我们", str(texts[:5]))
check("96636 预览栏显示拼音", bool(re.fullmatch(r"[a-zü]+('[a-zü]+)*", preedit)), repr(preedit))
press(session, ord(" "))
c = take_commit(session)
check("96636 空格上屏=我们", c == "我们", repr(c))

# ---- 测试 2: 输入 64426 -> 你好 ----
print("\n=== test 2: 64426 -> 你好 ===")
for ch in "64426":
    press(session, ord(ch))
ctx = get_context(session)
texts = menu_texts(ctx)
print("candidates:", texts)
check("64426 候选含你好", "你好" in texts, str(texts[:5]))
clear_composition(session)

# ---- 测试 3: 输入 7487832 -> 输入法; 94664486 候选含中国 ----
print("\n=== test 3: 7487832 -> 输入法 ===")
for ch in "7487832":
    press(session, ord(ch))
ctx = get_context(session)
texts = menu_texts(ctx)
print("candidates:", texts)
check("7487832 首选=输入法", texts[0] == "输入法", str(texts[:5]))
press(session, ord(" "))
c = take_commit(session)
check("7487832 上屏=输入法", c == "输入法", repr(c))
for ch in "94664486":
    press(session, ord(ch))
ctx = get_context(session)
texts = menu_texts(ctx)
print("94664486 candidates:", texts)
check("94664486 候选含中国", ("中国" in texts) or ("你好中国" in texts), str(texts[:5]))
clear_composition(session)

# ---- 测试 4: 逐键补全 - 输入 94 出现 一/是 等单字 ----
print("\n=== test 4: 94 单字候选 ===")
for ch in "94":
    press(session, ord(ch))
ctx = get_context(session)
texts = menu_texts(ctx)
print("candidates:", texts)
check("94 候选含 一", "一" in texts, str(texts[:5]))
clear_composition(session)

# ---- 测试 5: 按键 1 上屏标点, 0 上屏空格 ----
print("\n=== test 5: 标点键 1 / 空格键 0 ===")
press(session, ord("1"))
c = take_commit(session)
check("按 1 上屏逗号", c == "，", repr(c))
press(session, ord("0"))
c = take_commit(session)
check("按 0 上屏空格", c == " ", repr(c))

# ---- 测试 6: 模拟 KP_2 绑定效果 (key_binder 把 KP_2 转为 2) ----
# KP_2 在 rime 内部 keycode = 0xFFB2 (XK_KP_2)
print("\n=== test 6: KP_* 小键盘键绑定 ===")
KP_2, KP_3 = 0xFFB2, 0xFFB3
press(session, KP_2)
press(session, KP_3)
ctx = get_context(session)
preedit = ctx.composition.preedit.decode("utf-8", "replace") if ctx.composition.preedit else ""
check("KP_2 KP_3 预览栏为拼音(不含数字)", bool(preedit) and not re.search(r"[0-9]", preedit) and re.fullmatch(r"[a-zü]+('[a-zü]+)*", preedit), repr(preedit))
clear_composition(session)

# ---- 测试 7: Control+Shift+2 切换中英文 (ascii 模式下数字键不被消费) ----
print("\n=== test 7: Control+Shift+2 切换 ascii_mode ===")
# 确保会话处于空编码状态
clear_composition(session)
ctx = get_context(session)
pre = ctx.composition.preedit
assert not pre, "preedit not cleared: %r" % pre
SHIFT_MASK = 0x1
CONTROL_MASK = 0x4
toggle_mask = SHIFT_MASK | CONTROL_MASK
press(session, ord("2"), toggle_mask)
consumed = press(session, ord("2"))
check("Control+Shift+2 切到西文模式(数字键直通)", consumed == 0, "consumed=%d" % consumed)
press(session, ord("2"), toggle_mask)
consumed = press(session, ord("2"))
check("再按 Control+Shift+2 切回中文(数字键作为编码)", consumed == 1, "consumed=%d" % consumed)
clear_composition(session)

dll.RimeDestroySession(session)

fails = [r for r in results if not r[1]]
print("\n========== SUMMARY: %d/%d PASSED ==========" % (len(results) - len(fails), len(results)))
if fails:
    print("FAILED:", [r[0] for r in fails])
    sys.exit(1)
print("ALL TESTS PASSED")
