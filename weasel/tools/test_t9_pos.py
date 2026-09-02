# -*- coding: utf-8 -*-
"""
test_t9_pos.py - 九键位置对应方案(t9_pos)端到端测试
验证小键盘按物理位置映射手机九键:
  KP_7->1(标点) KP_8->2(abc) KP_9->3(def)
  KP_4->4       KP_5->5      KP_6->6
  KP_1->7(pqrs) KP_2->8(tuv) KP_3->9(wxyz)  KP_0->0(空格)
"""
import ctypes
import os
import re
import shutil
import sys
import time

RIME_DLL = r"d:\desktop\input\weasel\output\Win32\rime.dll"
SHARED_DIR = r"d:\desktop\input\weasel\output\data"
USER_DIR = r"d:\desktop\input\rime-user-pos"

if os.path.isdir(USER_DIR):
    shutil.rmtree(USER_DIR)
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


class RimeContext(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", ctypes.c_char_p),
        ("select_labels", ctypes.POINTER(ctypes.c_char_p)),
    ]


def STRUCT_INIT(Struct):
    return ctypes.sizeof(Struct) - ctypes.sizeof(ctypes.c_int)


dll.RimeSetup.argtypes = [ctypes.POINTER(RimeTraits)]
dll.RimeInitialize.argtypes = [ctypes.POINTER(RimeTraits)]
dll.RimeStartMaintenance.argtypes = [ctypes.c_bool]
dll.RimeCreateSession.argtypes = []
dll.RimeProcessKey.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_int]
dll.RimeGetContext.argtypes = [ctypes.c_uint, ctypes.POINTER(RimeContext)]
dll.RimeFreeContext.argtypes = [ctypes.POINTER(RimeContext)]
dll.RimeGetCommit.argtypes = [ctypes.c_uint, ctypes.POINTER(RimeCommit)]
dll.RimeFreeCommit.argtypes = [ctypes.POINTER(RimeCommit)]
dll.RimeSelectSchema.argtypes = [ctypes.c_uint, ctypes.c_char_p]

traits = RimeTraits()
traits.data_size = STRUCT_INIT(RimeTraits)
traits.shared_data_dir = SHARED_DIR.encode("utf-8")
traits.user_data_dir = USER_DIR.encode("utf-8")
traits.distribution_name = b"Weasel T9 Pos Test"
traits.distribution_code_name = b"weasel-t9-pos-test"
traits.distribution_version = b"1.0.0"
traits.app_name = b"rime.weasel-t9-pos-test"

dll.RimeSetup(ctypes.byref(traits))
dll.RimeInitialize(ctypes.byref(traits))

print("=== start maintenance ===")
dll.RimeStartMaintenance(True)
t0 = time.time()
while dll.RimeIsMaintenancing():
    time.sleep(1)
    if time.time() - t0 > 900:
        print("TIMEOUT")
        sys.exit(1)
print("maintenance finished in %.1fs" % (time.time() - t0))

sess = dll.RimeCreateSession()
assert dll.RimeSelectSchema(sess, b"t9_pos"), "select schema t9_pos failed"

XK_KP0 = 0xFFB0
XK_SPACE = 0x20
XK_BACKSPACE = 0xFF08


def kp(n):
    return XK_KP0 + n


def press(keycode, mask=0):
    return dll.RimeProcessKey(sess, keycode, mask)


def get_context():
    ctx = RimeContext()
    ctx.data_size = STRUCT_INIT(RimeContext)
    if not dll.RimeGetContext(sess, ctypes.byref(ctx)):
        return None
    return ctx


def preedit():
    ctx = get_context()
    if not ctx:
        return ""
    p = ctx.composition.preedit
    r = p.decode("utf-8", "replace") if p else ""
    dll.RimeFreeContext(ctypes.byref(ctx))
    return r


def candidates():
    ctx = get_context()
    if not ctx:
        return []
    n = ctx.menu.num_candidates
    out = []
    for i in range(n):
        t = ctx.menu.candidates[i].text
        out.append(t.decode("utf-8", "replace") if t else "")
    dll.RimeFreeContext(ctypes.byref(ctx))
    return out


def take_commit():
    commit = RimeCommit()
    commit.data_size = STRUCT_INIT(RimeCommit)
    if dll.RimeGetCommit(sess, ctypes.byref(commit)):
        txt = commit.text.decode("utf-8", "replace") if commit.text else ""
        dll.RimeFreeCommit(ctypes.byref(commit))
        return txt
    return ""


def clear():
    for _ in range(32):
        if not preedit():
            return
        press(XK_BACKSPACE)


passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("PASS", name, "|", detail)
    else:
        failed += 1
        print("FAIL", name, "|", detail)


# 测试 1: KP_8 KP_9 -> 手机九键编码 23 (abc/def 组), 预览栏显示拼音
clear()
press(kp(8))
press(kp(9))
pe = preedit()
check("KP_8 KP_9 预览栏为拼音(不含数字)", bool(pe) and re.fullmatch(r"[a-zü]+('[a-zü]+)*", pe), repr(pe))

# 测试 2: 我们 = 手机编码 96636 -> 位置键 KP_3 KP_6 KP_6 KP_9 KP_6
clear()
for k in (3, 6, 6, 9, 6):
    press(kp(k))
cands = candidates()
check("位置键 36696 候选含 我们", "我们" in cands, str(cands))
press(XK_SPACE)
check("上屏=我们", take_commit() == "我们", "")

# 测试 3: KP_7 -> 标点 ，
clear()
press(kp(7))
check("KP_7 上屏=，", take_commit() == "，", "")

# 测试 4: KP_0 -> 空格
clear()
press(kp(0))
check("KP_0 上屏=空格", take_commit() == " ", "")

# 测试 5: KP_1 KP_2 KP_3 -> 手机九键编码 789 (pqrs/tuv/wxyz 组), 预览栏显示拼音
clear()
press(kp(1))
press(kp(2))
press(kp(3))
pe = preedit()
check("KP_1 KP_2 KP_3 预览栏为拼音(不含数字)", bool(pe) and re.fullmatch(r"[a-zü]+('[a-zü]+)*", pe), repr(pe))
clear()

print("========== SUMMARY: %d/%d PASSED ==========" % (passed, passed + failed))
print("ALL TESTS PASSED" if failed == 0 else "SOME TESTS FAILED")
sys.exit(0 if failed == 0 else 1)
