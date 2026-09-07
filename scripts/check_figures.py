#!/usr/bin/env python3
r"""图表交付体检：数量对分位、引用对得上、文件对得上。

为什么需要这个脚本
------------------
`stage_08_writing.md` 的检查清单写着「图表数量与一等奖分位大致可比
（图 ~20、表 ~9），显著偏少要检查是否交付不足」，`empirical.json` 里也存着
44 篇实测的分位数——但**没人去数**。而组委会反复点名的恰恰是这一类：
2022A「评阅中发现的问题」9 条里 5 条与建模无关，全是"计算方法不清楚 /
结果不完整 / 没有很好地呈现结果 / 没有对结果进行分析 / 结果文件格式不对"。

查四件，性质不同，**退出码只认前两件**：

| 检查 | 级别 | 为什么 |
|---|---|---|
| `\includegraphics` 指向的文件不存在 | **FAIL** | 编译直接断，或图位置留白 |
| `\ref` 没有对应 `\label` | **FAIL** | PDF 里印出 `??`，评委看得见 |
| 图/表数量低于一等奖 p25 | WARN | **经验分布不是规则**（`stage_08_writing.md` §35 明写） |
| figures/ 里有图但正文没引用 | WARN | 可能漏了交付，也可能是中间产物 |

**数量绝不能判成 FAIL。** 本仓库的一贯立场是"经验值不能当官方评分线"——
图少不违规，图少只是**可能**交付不足。把它做成硬门会逼人凑图，
而组委会点名的是"没有对结果进行分析"，不是"图不够多"。

用法
----
    python scripts/check_figures.py --paper paper.tex --figures figures/
    python scripts/check_figures.py --paper paper.tex --figures figures/ --topic A
    python scripts/check_figures.py --workspace paper_workspace/ --figures figures/ --json

`--topic A|B|C` 用该题型的分位（A 题图 p50=20/表 p50=7，B 题图 p50=26，
C 题图 p50=19），不给就用全体分位（图 p50=20、表 p50=9）。

退出码：0 = 无 FAIL（WARN 不影响）；1 = 有 FAIL；2 = 没跑成。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]

IMG_EXT = (".png", ".pdf", ".jpg", ".jpeg", ".eps", ".svg")

# `\includegraphics[...]{path}`；可选参数里可能有换行
INCLUDE_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}",
                        re.DOTALL)
# Markdown 图片 `![caption](path)`
MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
TABLE_ENV_RE = re.compile(r"\\begin\{(table\*?|longtable|tabular)\}")
# Markdown 表格：以 `|---|` 分隔行判定
MD_TABLE_RE = re.compile(r"^\s*\|?[\s:|-]*-{3,}[\s:|-]*\|", re.MULTILINE)
LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:auto|c|C|eq|page|name)?ref\s*\{([^}]+)\}")

# 参考文献段里的 label/ref 不参与统计
BIB_START = re.compile(
    r"\\begin\{thebibliography\}|\\bibliography\b|"
    r"\\section\*?\{\s*(?:参考文献|References?)\s*\}",
    re.IGNORECASE)


class Finding:
    __slots__ = ("level", "code", "msg", "action")

    def __init__(self, level: str, code: str, msg: str, action: str = ""):
        self.level, self.code, self.msg, self.action = level, code, msg, action

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code,
                "msg": self.msg, "action": self.action}


def _strip_comments(text: str) -> str:
    r"""去掉 LaTeX 注释行与参考文献段。

    注释掉的 `% \includegraphics{...}` 不该被算进图数——否则改稿时注释掉一张图，
    计数还照旧，这个检查就开始骗人了。
    """
    m = BIB_START.search(text)
    if m:
        text = text[: m.start()]
    out = []
    for line in text.splitlines():
        # 只砍未被转义的 %
        idx, esc = None, False
        for i, ch in enumerate(line):
            if ch == "\\":
                esc = not esc
                continue
            if ch == "%" and not esc:
                idx = i
                break
            esc = False
        out.append(line if idx is None else line[:idx])
    return "\n".join(out)


def collect_sources(paper: Path | None, workspace: Path | None
                    ) -> list[tuple[Path, str]]:
    srcs: list[tuple[Path, str]] = []
    if paper and paper.is_file():
        srcs.append((paper, paper.read_text(encoding="utf-8", errors="replace")))
    if workspace and workspace.is_dir():
        for p in sorted(workspace.rglob("*.md")):
            srcs.append((p, p.read_text(encoding="utf-8", errors="replace")))
    return srcs


def _quantiles(topic: str | None) -> tuple[dict, str]:
    path = SKILL_ROOT / "competitions" / "cumcm" / "empirical.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if topic:
        node = (data.get("by_topic") or {}).get(topic.upper())
        if node:
            return node, "%s 题（n=%s）" % (topic.upper(),
                                          node.get("figure_count", {}).get("n"))
    node = data.get("dims") or {}
    return node, "全体（n=%s）" % (node.get("figure_count", {}).get("n"))


def check(paper: Path | None, workspace: Path | None, figures: Path | None,
          topic: str | None = None) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    srcs = collect_sources(paper, workspace)
    if not srcs:
        raise SystemExit("没有可分析的论文源：--paper 或 --workspace 至少给一个")

    referenced: set[str] = set()      # 正文引用到的图文件（原样路径）
    labels: dict[str, int] = {}
    refs: dict[str, int] = {}
    n_tables = 0
    n_fig_includes = 0
    missing_files: list[str] = []

    base_dirs = [s[0].parent for s in srcs]
    if figures:
        base_dirs.append(figures)
        base_dirs.append(figures.parent)

    for path, raw in srcs:
        text = _strip_comments(raw) if path.suffix == ".tex" else raw
        hits = list(INCLUDE_RE.findall(text)) + list(MD_IMG_RE.findall(text))
        for h in hits:
            h = h.strip()
            n_fig_includes += 1
            referenced.add(h)
            # LaTeX 允许省略扩展名，逐个候选试
            cands = [h] if Path(h).suffix else [h + e for e in IMG_EXT]
            found = False
            for cand in cands:
                p = Path(cand)
                if p.is_absolute() and p.is_file():
                    found = True
                    break
                for base in base_dirs:
                    if (base / cand).is_file():
                        found = True
                        break
                if found:
                    break
            if not found:
                missing_files.append(h)

        if path.suffix == ".tex":
            # 只数 `table` 浮动体，不数裸 `tabular`——一个 table 里可以套
            # 多个 tabular，按 tabular 数会把一个表报成好几个。
            n_tables += sum(1 for m in TABLE_ENV_RE.finditer(text)
                            if m.group(1).startswith("table"))
        else:
            n_tables += len(MD_TABLE_RE.findall(text))

        for lb in LABEL_RE.findall(text):
            labels[lb] = labels.get(lb, 0) + 1
        for rf in REF_RE.findall(text):
            refs[rf] = refs.get(rf, 0) + 1

    # ---- FAIL 1：引用的图文件不存在
    if missing_files:
        findings.append(Finding(
            "FAIL", "missing_image_file",
            "%d 个图文件引用不到：%s" % (len(missing_files),
                                        missing_files[:6]),
            "路径写错或图还没生成。**LaTeX 缺图不一定报错**——"
            "有的引擎只在图位置留一个方框，PDF 照样出。"
            "逐个核对相对路径的基准目录。"))

    # ---- FAIL 2：悬挂交叉引用
    dangling = sorted(k for k in refs if k not in labels)
    if dangling:
        findings.append(Finding(
            "FAIL", "dangling_ref",
            "%d 个 \\ref 没有对应的 \\label：%s"
            % (len(dangling), dangling[:8]),
            "PDF 里会印成 `??`，**评委看得见**。补 label 或改 ref。"))

    dup = sorted(k for k, v in labels.items() if v > 1)
    if dup:
        findings.append(Finding(
            "FAIL", "duplicate_label",
            "%d 个 \\label 重复定义：%s" % (len(dup), dup[:8]),
            "重复 label 会让 \\ref 指到其中任意一个——编号看着对，指向是错的。"))

    # ---- WARN：有 label 但从未被引用
    unref = sorted(k for k in labels
                   if k not in refs and re.match(r"(fig|tab|图|表)", k, re.I))
    if unref:
        findings.append(Finding(
            "WARN", "label_never_referenced",
            "%d 个图/表 label 正文从未引用：%s" % (len(unref), unref[:8]),
            "图表要在正文里被指名讨论。**只放图不解读**正是"
            "2022A 讲评点名的「没有对结果进行分析」。"))

    # ---- WARN：figures/ 里有图但没被引用
    orphans: list[str] = []
    if figures and figures.is_dir():
        used = {Path(r).name for r in referenced}
        used |= {Path(r).stem for r in referenced}
        for p in sorted(figures.rglob("*")):
            if p.suffix.lower() not in IMG_EXT:
                continue
            if p.name.endswith("_gray.png"):
                continue              # 灰度校样是给自己看的，不进论文
            if p.name not in used and p.stem not in used:
                orphans.append(str(p.relative_to(figures)))
    if orphans:
        findings.append(Finding(
            "WARN", "orphan_figure",
            "figures/ 里有 %d 张图没被正文引用：%s"
            % (len(orphans), orphans[:8]),
            "要么是漏了交付（画了没用上），要么是中间产物。"
            "中间产物挪出 figures/，免得最后打包时混进支撑材料。"))

    # ---- WARN：数量对分位。**只报不判**——经验分布不是规则。
    quant, quant_label = _quantiles(topic)
    stats = {"figures": n_fig_includes, "tables": n_tables}
    for key, name in (("figure_count", "图"), ("table_count", "表")):
        q = quant.get(key) or {}
        got = stats["figures" if key == "figure_count" else "tables"]
        p25, p50 = q.get("p25"), q.get("p50")
        if p25 is None:
            continue
        if got < p25:
            findings.append(Finding(
                "WARN", "below_p25_" + key,
                "%s数 %d，低于一等奖 p25=%s（p50=%s，%s）"
                % (name, got, p25, p50, quant_label),
                "**这不是规则，是经验分布**——%s少不违规。" % name +
                "但请回头确认每个子问都有：数值表 + 图 + 方法说明 + 分析段 + "
                "结果文件。真正被官方点名的是「结果不完整」「没有对结果进行分析」。"))

    return findings, {
        "sources": [str(p) for p, _ in srcs],
        "figures": n_fig_includes, "tables": n_tables,
        "labels": len(labels), "refs": len(refs),
        "quantile_basis": quant_label,
        "figure_p25": (quant.get("figure_count") or {}).get("p25"),
        "figure_p50": (quant.get("figure_count") or {}).get("p50"),
        "table_p25": (quant.get("table_count") or {}).get("p25"),
        "table_p50": (quant.get("table_count") or {}).get("p50"),
    }


def main(argv: list[str] | None = None) -> int:
    _console.init()
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper", type=Path, help="paper.tex 或 paper.md")
    ap.add_argument("--workspace", type=Path,
                    help="paper_workspace/，扫其中的 *.md")
    ap.add_argument("--figures", type=Path, help="figures/ 图目录")
    ap.add_argument("--topic", choices=list("ABCabc"),
                    help="按题型取分位（A/B/C）；不给用全体分位")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    if not args.paper and not args.workspace:
        print("--paper 或 --workspace 至少给一个", file=sys.stderr)
        return 2
    if args.paper and not args.paper.is_file():
        print("找不到论文 %s" % args.paper, file=sys.stderr)
        return 2
    if args.workspace and not args.workspace.is_dir():
        print("找不到 workspace %s" % args.workspace, file=sys.stderr)
        return 2

    findings, stats = check(args.paper, args.workspace, args.figures,
                            args.topic)
    fails = [f for f in findings if f.level == "FAIL"]
    warns = [f for f in findings if f.level == "WARN"]

    if args.as_json:
        print(json.dumps({**stats, "fail": len(fails), "warn": len(warns),
                          "findings": [f.as_dict() for f in findings]},
                         ensure_ascii=False, indent=2))
        return 1 if fails else 0

    print("图表体检：%s" % "、".join(stats["sources"][:3]))
    print("  图 %d 张 / 表 %d 个；label %d 个、ref %d 处"
          % (stats["figures"], stats["tables"], stats["labels"], stats["refs"]))
    print("  一等奖分位（%s）：图 p25=%s p50=%s，表 p25=%s p50=%s"
          % (stats["quantile_basis"], stats["figure_p25"], stats["figure_p50"],
             stats["table_p25"], stats["table_p50"]))
    if not findings:
        print(_console.sym("\n✓ 通过：引用与文件都对得上，数量在分位区间内。"))
        return 0
    for f in findings:
        mark = {"FAIL": "✗", "WARN": "⚠"}[f.level]
        print(_console.sym("\n%s [%s] %s" % (mark, f.code, f.msg)))
        if f.action:
            print("    → " + f.action)
    print("\n%d 个 FAIL，%d 个 WARN。" % (len(fails), len(warns)))
    if not fails:
        print(_console.sym("✓ 无 FAIL。数量类 WARN 是经验参考，不是规则。"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
