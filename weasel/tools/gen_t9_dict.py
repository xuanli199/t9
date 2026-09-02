# -*- coding: utf-8 -*-
"""
gen_t9_dict.py - 生成九键(T9)拼音词典
将标准拼音词典(明月拼音 luna_pinyin.dict.yaml / essay.txt 词频表)整理为
Rime 可用的 t9 词典。

编码模式(--code):
  pinyin (默认): 词条保留拼音编码, 由方案的 speller/algebra 在棱镜编译时
                 把拼音映射为九键数字, 从而预览栏可显示拼音。
  digit        : 词条直接输出手机九键数字编码(旧模式)。

字母-数字映射(标准手机键盘布局):
  2: a b c    3: d e f    4: g h i
  5: j k l    6: m n o    7: p q r s
  8: t u v(ü) 9: w x y z

用法:
  python gen_t9_dict.py --luna <luna_pinyin.dict.yaml> \
                        --essay <essay.txt> \
                        --out <t9.dict.yaml> [--code pinyin|digit]
"""

import argparse
import io
import sys

T9_MAP = {}
for digit, letters in {
    "2": "abc",
    "3": "def",
    "4": "ghi",
    "5": "jkl",
    "6": "mno",
    "7": "pqrs",
    "8": "tuv",
    "9": "wxyz",
}.items():
    for ch in letters:
        T9_MAP[ch] = digit
# ü 在拼音词典中常写作 v, 归入 8 键
T9_MAP["v"] = "8"
T9_MAP["ü"] = "8"


def syllable_to_t9(syllable):
    """把一个拼音音节转成 T9 数字串, 无法转换时返回 None"""
    syllable = syllable.strip().lower()
    if not syllable:
        return None
    digits = []
    for ch in syllable:
        d = T9_MAP.get(ch)
        if d is None:
            return None
        digits.append(d)
    return "".join(digits)


def pinyin_to_t9(pinyin):
    """把空格分隔的拼音串转成 T9 数字串"""
    syllables = pinyin.split()
    digits = []
    for s in syllables:
        d = syllable_to_t9(s)
        if d is None:
            return None
        digits.append(d)
    return "".join(digits)


def iter_luna_entries(path):
    """解析 luna_pinyin.dict.yaml, 产出 (word, pinyin, weight)"""
    in_entries = False
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not in_entries:
                if line.strip() == "...":
                    in_entries = True
                continue
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            word, pinyin = cols[0], cols[1]
            weight = cols[2] if len(cols) > 2 else "100"
            yield word, pinyin, weight


def iter_essay_entries(path):
    """解析 essay.txt 词频表, 产出 (word, pinyin, weight)

    essay.txt 有两种格式:
      旧版三列: word\\tpinyin(空格分隔)\\tweight
      新版二列: word\\tweight (无拼音, 使用 pypinyin 自动标注)
    """
    with io.open(path, "r", encoding="utf-8") as f:
        first = None
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if first is None:
                first = len(cols)
            if len(cols) >= 3:
                yield cols[0], cols[1], cols[2]
            elif len(cols) == 2 and first == 2:
                # 二列格式: 需要借助 pypinyin 标注拼音
                yield cols[0], None, cols[1]
            else:
                continue


def is_all_hanzi(word):
    for ch in word:
        if not ("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"):
            return False
    return True


def normalize_pinyin(pinyin):
    """规范化空格分隔的拼音串(小写、去首尾空白), 非法时返回 None"""
    syllables = pinyin.strip().lower().split()
    if not syllables:
        return None
    for s in syllables:
        if not s:
            return None
    return " ".join(syllables)


def essay_word_to_pinyin(word, pinyin_helper):
    """用 pypinyin 给词标注无声调拼音"""
    try:
        syllables = pinyin_helper(word)
    except Exception:
        return None
    return normalize_pinyin(" ".join(syllables))


def essay_word_to_t9(word, pinyin_helper):
    """用 pypinyin 给词标注无声调拼音并转成 T9 编码"""
    pinyin = essay_word_to_pinyin(word, pinyin_helper)
    if pinyin is None:
        return None
    return pinyin_to_t9(pinyin)


def main():
    parser = argparse.ArgumentParser(description="生成 T9 九键拼音词典")
    parser.add_argument("--luna", required=True, help="luna_pinyin.dict.yaml 路径")
    parser.add_argument("--essay", required=False, default=None, help="essay.txt 路径")
    parser.add_argument("--out", required=True, help="输出的 t9.dict.yaml 路径")
    parser.add_argument(
        "--code",
        choices=["pinyin", "digit"],
        default="pinyin",
        help="词条编码模式: pinyin(默认, 配合方案 algebra 使用) 或 digit",
    )
    args = parser.parse_args()
    use_digit_code = args.code == "digit"

    # (word, t9code) -> max weight
    entries = {}
    stats = {"total": 0, "converted": 0, "skipped": 0}

    # pypinyin 延迟导入, 仅在 essay 二列格式需要时才使用
    pinyin_helper = None
    if args.essay:
        try:
            from pypinyin import lazy_pinyin

            def pinyin_helper(word):
                return lazy_pinyin(word)

        except ImportError:
            pinyin_helper = None

    sources = [("luna_pinyin.dict.yaml", iter_luna_entries(args.luna))]
    if args.essay:
        sources.append(("essay.txt", iter_essay_entries(args.essay)))

    for source_name, it in sources:
        for word, pinyin, weight in it:
            stats["total"] += 1
            if pinyin is None:
                # 二列 essay: 自动标注拼音, 只处理纯汉字词条
                if pinyin_helper is None or not is_all_hanzi(word):
                    stats["skipped"] += 1
                    continue
                code = essay_word_to_pinyin(word, pinyin_helper)
                if code is not None and use_digit_code:
                    code = pinyin_to_t9(code)
            else:
                code = normalize_pinyin(pinyin)
                if code is not None and use_digit_code:
                    code = pinyin_to_t9(code)
            if code is None:
                stats["skipped"] += 1
                continue
            try:
                w = int(weight)
            except ValueError:
                w = 100
            key = (word, code)
            if key not in entries or w > entries[key]:
                entries[key] = w
            stats["converted"] += 1

    # 按词频降序输出
    items = sorted(entries.items(), key=lambda kv: kv[1], reverse=True)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Rime dictionary\n")
        f.write("# encoding: utf-8\n")
        f.write("#\n")
        f.write("# 九键(T9)拼音词典\n")
        f.write("# 由 gen_t9_dict.py 从明月拼音(luna_pinyin)与 essay 词频表自动生成\n")
        f.write("#\n\n")
        f.write("---\n")
        f.write("name: t9\n")
        f.write('version: "2.0.0"\n')
        f.write("sort: by_weight\n")
        f.write("use_preset_vocabulary: false\n")
        f.write("...\n\n")
        for (word, code), weight in items:
            f.write("%s\t%s\t%d\n" % (word, code, weight))

    sys.stderr.write(
        "entries total=%d converted=%d skipped=%d unique=%d -> %s\n"
        % (stats["total"], stats["converted"], stats["skipped"], len(items), args.out)
    )


if __name__ == "__main__":
    main()
