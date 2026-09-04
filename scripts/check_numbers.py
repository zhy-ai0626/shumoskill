#!/usr/bin/env python3
"""数值可追溯性检查：论文里出现的每个数字，都要能在结果文件里找到同一个值。

为什么需要这个脚本
------------------
`competitions/cumcm/winning_patterns.md` 写着「数值要能追溯」，
`references/stage_09_review.md` §3 写着 "all headline values reproduce from stored results"，
但这两条一直只是散文清单项，没有任何可执行的检查。而论文里的数字大多是**手抄**进去的
（从终端输出复制到 LaTeX），抄错一位不会报错，评委却能核出来。

官方对这一点点名过多次：2022A 讲评「评阅中发现的问题」第 3 条"计算结果不完整"、
第 4 条"没有很好地呈现结果"；2023B「没有给出测线的具体坐标」。

做法
----
1. 从论文（.tex / .md）里抽出所有数值 token，剔除明显不需要追溯的
   （章节号、年份、页码、公式里的整数系数、参考文献编号等）；
2. 把 results/ 下的 .json / .csv 全部展平成一个数值池；
3. 逐个数值在池子里按相对容差匹配；
4. 报告「论文里有、结果文件里找不到」的数值。

这是**单向**检查：结果文件里有而论文没用到的值不算问题。
它也不保证语义正确——只保证纸面上的数字确实来自程序输出。

用法
----
    python scripts/check_numbers.py --paper paper.tex --results results/
    python scripts/check_numbers.py --paper paper.tex --results results/ --json
    python scripts/check_numbers.py --paper paper.tex --results results/ --rtol 1e-3

退出码：0 = 全部可追溯；1 = 有无法追溯的数值。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

# 论文里出现但**不需要**追溯到结果文件的数值：结构性数字，不是计算结果。
IGNORE_PATTERNS = (
    r"\\(?:sub)*section\b",      # 章节命令
    r"\\cite\b", r"\\ref\b", r"\\label\b", r"\\includegraphics\b",
    r"\\begin\{.*?\}", r"\\end\{.*?\}",
    r"\\(?:hspace|vspace|setlength|geometry|documentclass|usepackage)\b",
    # 排版常数不是结果值：行距、字号、列宽、表格拉伸等。
    # 漏掉它们会把 \linespread{1.08} 报成"论文里有、结果文件里没有的数字"。
    r"\\(?:linespread|baselinestretch|arraystretch|selectfont|fontsize"
    r"|captionsetup|lstset|hypersetup|includegraphics|resizebox|scalebox"
    r"|colorbox|rule|width|height|textwidth|columnwidth|linewidth|zihao)\b",
)
# 独立成词的这些值一律跳过：0/1 常量、常见显著性水平、百分比刻度等
TRIVIAL = {0.0, 1.0, 2.0, 0.5, 100.0, 0.05, 0.01, 0.1, 95.0, 99.0, 90.0}


# 参考文献里全是卷号、期号、页码范围，一个都不需要追溯。整段砍掉。
BIB_START = re.compile(
    r"\\begin\{thebibliography\}|\\bibliography\b|"
    r"\\section\*?\{\s*(?:参考文献|References?)\s*\}|"
    r"^#{1,3}\s*(?:参考文献|References?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _strip_noise(text: str) -> str:
    """去掉参考文献段、注释行，以及不需要追溯的 LaTeX 命令所在片段。"""
    m = BIB_START.search(text)
    if m:
        text = text[: m.start()]
    # LaTeX 的 `--` / `---` 是范围连字符（页码 963--974、区间 11--13 周），
    # 不处理会把后半段读成负数。统一换成空格。
    text = re.sub(r"-{2,}", " ", text)
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("%"):
            continue
        for pat in IGNORE_PATTERNS:
            line = re.sub(pat + r"[^\s]*", " ", line)
        lines.append(line)
    return "\n".join(lines)


NUM_RE = re.compile(
    r"(?<![\w.])"                       # 左边不能紧挨字母/数字/点
    # 两种写法：带千分逗号的 1,234.56，或不带分隔符的一长串数字。
    # 原来只写了 `\d{1,3}(?:,\d{3})*`，四位以上的**裸数字**（如 119120）
    # 一个都匹配不上——不是报成未追溯，而是**静默跳过不检查**。
    r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*\\?times\s*10\^\{?[-+]?\d+\}?|[eE][-+]?\d+)?"  # 科学计数
    r"(?![\w])"
)


# LaTeX 里的千分位是细空格 `\,`：119\,120 表示 119120。
# 不先合并的话会被切成 119 与 120 两个数，双双报成"结果文件里找不到"——
# 这类误报会让人直接不信任这个脚本（2023A 演练实测，29 个未追溯值里 7 个是它造成的）。
THIN_SPACE_THOUSANDS = re.compile(r"(?<=\d)\\[,;:]\s*(?=\d{3}(?!\d))")


def extract_numbers(text: str, min_digits: int = 2) -> list[tuple[float, str]]:
    """返回 [(数值, 原文片段)]。min_digits 过滤掉只有一位有效数字的值。"""
    out: list[tuple[float, str]] = []
    text = THIN_SPACE_THOUSANDS.sub("", text)
    for m in NUM_RE.finditer(_strip_noise(text)):
        raw = m.group(0)
        norm = raw.replace(",", "").replace(" ", "")
        norm = re.sub(r"\\?times10\^\{?([-+]?\d+)\}?", r"e\1", norm)
        try:
            val = float(norm)
        except ValueError:
            continue
        if not math.isfinite(val):
            continue
        digits = len(re.sub(r"[^0-9]", "", norm.split("e")[0]).lstrip("0"))
        if digits < min_digits:
            continue
        if abs(val) in TRIVIAL:
            continue
        out.append((val, raw))
    return out


def _walk_json(node, pool: set[float]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _walk_json(v, pool)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _walk_json(v, pool)
    elif isinstance(node, bool):
        return
    elif isinstance(node, (int, float)) and math.isfinite(float(node)):
        pool.add(float(node))
    elif isinstance(node, str):
        try:
            v = float(node.replace(",", ""))
        except ValueError:
            return
        if math.isfinite(v):
            pool.add(v)


def collect_results(results_dir: Path, include_text: bool = False) -> tuple[set[float], list[Path]]:
    """把 results/ 下的数值展平成一个池子。

    默认只收 .json / .csv —— 这是程序输出里**机器可读、口径明确**的那部分，
    严格。加 --include-text 才把 .txt / .md 报告一起收进来：报告里数字多、
    上下文散，池子会显著变大，匹配随之变松，只在确认过口径时才用。
    """
    pool: set[float] = set()
    seen: list[Path] = []
    for path in sorted(results_dir.rglob("*")):
        if path.suffix.lower() == ".json":
            try:
                _walk_json(json.loads(path.read_text(encoding="utf-8")), pool)
                seen.append(path)
            except (OSError, json.JSONDecodeError):
                continue
        elif include_text and path.suffix.lower() in (".txt", ".md"):
            try:
                for m in NUM_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
                    try:
                        v = float(m.group(0).replace(",", "").replace(" ", ""))
                    except ValueError:
                        continue
                    if math.isfinite(v):
                        pool.add(v)
                seen.append(path)
            except OSError:
                continue
        elif path.suffix.lower() == ".csv":
            try:
                with path.open(encoding="utf-8-sig", newline="") as fh:
                    for row in csv.reader(fh):
                        for cell in row:
                            try:
                                v = float(cell.replace(",", ""))
                            except ValueError:
                                continue
                            if math.isfinite(v):
                                pool.add(v)
                seen.append(path)
            except OSError:
                continue
    return pool, seen


def _sig_digits(as_written: str) -> int:
    r"""论文里这个数写了几位有效数字。'0.0421'→3, '9.6\times10^{-6}'→2, '1082'→4。"""
    mantissa = re.split(r"[eE]|\\?times", as_written)[0]
    digits = re.sub(r"[^0-9]", "", mantissa).lstrip("0")
    return len(digits)


def _round_sig(x: float, sig: int) -> float:
    if x == 0 or not math.isfinite(x) or sig <= 0:
        return 0.0 if x == 0 else x
    return round(x, -int(math.floor(math.log10(abs(x)))) + (sig - 1))


def traceable(value: float, pool: set[float], rtol: float, as_written: str = "") -> bool:
    """论文里的数字是四舍五入过的，所以除了相对容差，还允许
    「按论文写出的有效数字位数回合后相等」这一种命中方式。"""
    if value in pool:
        return True
    sig = _sig_digits(as_written)
    for candidate in pool:
        # abs_tol 必须接近 0。曾经写成 abs_tol=rtol，等于给所有小数值一个 5e-3 的
        # 绝对容差：论文把 0.182 抄成 0.187 也能匹配上 0.1887，检查形同虚设。
        if math.isclose(value, candidate, rel_tol=rtol, abs_tol=1e-12):
            return True
        # 论文里的数字是四舍五入过的。按**有效数字**回合，而不是小数位——
        # 后者对 9.6×10⁻⁶ 这种科学计数法写法完全失效。
        if sig and _round_sig(candidate, sig) == _round_sig(value, sig):
            return True
        # 百分数写法：论文 13.4 ↔ 结果 0.1338
        if candidate != 0:
            if math.isclose(value / 100.0, candidate, rel_tol=rtol, abs_tol=0):
                return True
            if sig and _round_sig(candidate * 100.0, sig) == _round_sig(value, sig):
                return True
    return False


def main() -> int:
    _console.init()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper", type=Path, required=True, help="论文文件 (.tex / .md)")
    ap.add_argument("--results", type=Path, required=True, help="结果目录 (含 .json/.csv)")
    ap.add_argument("--rtol", type=float, default=5e-3, help="相对容差，默认 5e-3")
    ap.add_argument("--min-digits", type=int, default=2,
                    help="少于这么多位有效数字的值不检查，默认 2")
    ap.add_argument("--include-text", action="store_true",
                    help="把 results/ 下的 .txt/.md 报告也纳入数值池（更宽松）")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if not args.paper.exists():
        print(f"论文不存在: {args.paper}", file=sys.stderr)
        return 2
    if not args.results.is_dir():
        print(f"结果目录不存在: {args.results}", file=sys.stderr)
        return 2

    pool, files = collect_results(args.results, include_text=args.include_text)
    if not pool:
        print(f"结果目录里没有可解析的数值: {args.results}", file=sys.stderr)
        return 2

    numbers = extract_numbers(args.paper.read_text(encoding="utf-8"), args.min_digits)
    checked = {v: raw for v, raw in numbers}          # 去重，保留一个原文片段
    missing = [(v, raw) for v, raw in sorted(checked.items())
               if not traceable(v, pool, args.rtol, raw)]

    if args.as_json:
        print(json.dumps({
            "paper": str(args.paper),
            "result_files": [str(p) for p in files],
            "pool_size": len(pool),
            "checked": len(checked),
            "missing": [{"value": v, "as_written": raw} for v, raw in missing],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"论文: {args.paper}")
        print(f"结果文件: {len(files)} 个，数值池 {len(pool)} 个不同取值")
        print(f"检查了 {len(checked)} 个数值（去重后，≥{args.min_digits} 位有效数字）")
        if missing:
            print(_console.sym(f"\n✗ {len(missing)} 个数值在结果文件里找不到："))
            for v, raw in missing:
                print(f"    {raw:>18}   （解析为 {v!r}）")
            print("\n逐个确认：是手抄错了，还是这个数就没进结果文件？")
            print("后者要么把它写进 results/，要么在论文里说明它的来源。")
        else:
            print(_console.sym("\n✓ 全部可追溯。"))

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
