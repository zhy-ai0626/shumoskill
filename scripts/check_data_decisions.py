#!/usr/bin/env python3
"""Stage 2 数据口径闸门：**"要不要动数据"这个决定必须逐问写下来，并给出依据。**

为什么需要这个脚本
------------------
`题型与算法对照.md` §四第一步、`anti_patterns.md` Z3 + Z18、`winning_patterns.md`
都写着那条判据——**这一步是统计习惯，还是领域方法的组成部分**——
`stage_02_analysis.md` Step 4b 也做成了决策闸门。但闸门此前只是**散文清单**，
没有任何可执行的检查，于是"忘了填"和"这题不需要填"在状态文件里长得一模一样。

这条教条是**两轮演练、两个方向都栽过**换来的，所以这个门也必须双向查：

| 方向 | 现象 | 本脚本 |
|---|---|---|
| Z3 | 拿到附件先清洗、删补、按 3σ/分位删异常值 | **FAIL**（`nature` 写"统计习惯"却真动了数据） |
| Z18 | 反过来把"无需预处理"泛化到所有子问，连领域质控也放弃 | **WARN**（全问全 `keep_as_is`，附上 2025C 的量化证据） |

Z18 只能是 WARN 不能是 FAIL：**多数题目全 `keep_as_is` 是正确答案**
（2025C 问题 1–3、绝大多数 A/B 题）。把它判成 FAIL 会逼人为了过门去动数据，
正好掉进 Z3。数据类题型 + 全 keep_as_is 时警告说得更重一些。

用法
----
    # 首次：从附件体检报告生成骨架
    python scripts/scan_attachments.py 附件/ --json > state/scan.json
    python scripts/check_data_decisions.py --decision-log state/decision_log.json \
        --scan state/scan.json --scaffold > state/preproc.json

    # 过门
    python scripts/check_data_decisions.py --decision-log state/decision_log.json
    python scripts/check_data_decisions.py --decision-log state/decision_log.json \
        --scan state/scan.json --json

退出码：0 = 通过（WARN 不影响）；1 = 有 FAIL，Stage 2 不得退出；2 = 没跑成。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

# `action` 枚举。和 `stage_02_analysis.md` Step 4b 的 JSON 骨架一致。
ACTIONS = {
    "keep_as_is":   "原样使用，不动",
    "aggregate":    "聚合 / 口径统一（原始流水必做，属建模的一部分）",
    "qc_filter":    "领域方法内在要求的质控（须写依据）",
    "unit_convert": "量纲统一 / 单位换算 / 仪器量程截断",
    "impute":       "插补（默认不做；做就必须说清凭什么不是统计习惯）",
}
# 动了数据的动作。这些动作配上 nature="统计习惯" 就是 Z3。
MUTATING = {"qc_filter", "impute"}

# `nature` 里出现这些词，等于自认是常规统计预处理
STATISTICAL_HABIT = ("统计习惯", "常规预处理", "常规统计", "惯例")

# `rationale` 的套话黑名单：写了这些等于没写依据
BOILERPLATE = ("常规做法", "标准流程", "通用做法", "惯例", "一般都这么做",
               "行业惯例", "todo", "待补", "待定", "同上")

# 可追溯的出处标记。**判据是"有没有出处"，不是"写得长不长"**——
# 「题面 85%~105% 为有效数据」只有 11 个字但依据完整，
# 而「按 3σ 剔除极值」同样短却一个出处都没有。
# 第一版只按 `len < 8` 判，把前者也会误伤，而且报出的理由（"套话"）是错的。
EVIDENCE_MARKERS = (
    "题面", "题目", "题干", "附件", "讲评", "评阅", "官方",
    "规范", "标准", "GB", "国标", "文献", "论文", "教材",
    "业务", "定义", "口径", "规定", "量程", "单位", "量纲",
    "临床", "仪器", "物理", "机理", "上游", "评审",
)
MIN_RATIONALE_CHARS = 6

REQUIRED_FIELDS = ("column", "action", "nature", "rationale")

DATA_SHAPES = {"data_statistics", "compositional"}

# scan_attachments 的这些 kind 必须在决策表里有对应的处置说明——
# 体检报了却没有任何决定，等于扫了不看。
KINDS_NEEDING_DECISION = {
    "compositional", "compositional_approx", "merged_cells",
    "mixed_dtype", "case_collision", "derived_mismatch",
    "identity_collinear", "edge_row_text", "constant",
}


class Finding:
    __slots__ = ("level", "code", "msg", "action")

    def __init__(self, level: str, code: str, msg: str, action: str = ""):
        self.level, self.code, self.msg, self.action = level, code, msg, action

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code,
                "msg": self.msg, "action": self.action}


def _load_json(path: Path, what: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit("读不到%s %s: %s" % (what, path, exc))
    except json.JSONDecodeError as exc:
        raise SystemExit("%s 不是合法 JSON: %s" % (what, exc))


def _scan_columns(scan: list | dict) -> dict[str, set[str]]:
    """从 scan_attachments --json 报告里抽出 {列名: {kind, ...}}。"""
    out: dict[str, set[str]] = {}
    frames = scan if isinstance(scan, list) else [scan]
    for frame in frames:
        for item in (frame or {}).get("findings", []):
            kind = item.get("kind")
            if kind not in KINDS_NEEDING_DECISION:
                continue
            for col in item.get("columns") or []:
                out.setdefault(str(col), set()).add(kind)
    return out


def check(log: dict, scan_cols: dict[str, set[str]] | None = None
          ) -> list[Finding]:
    out: list[Finding] = []
    stage2 = (log.get("stages") or {}).get("2") or {}
    schema = stage2.get("data_schema") or {}
    decisions = stage2.get("preprocessing_decisions") or {}
    decomposition = stage2.get("decomposition") or []
    shape = log.get("problem_shape")

    has_attachment_data = bool(schema) or bool(scan_cols)

    # ---- 没有附件数据的题（如 2024B 型只给参数表），这个门整体不适用
    if not has_attachment_data:
        if decisions:
            out.append(Finding(
                "WARN", "no_data_but_decisions",
                "`data_schema` 是空的，却填了 preprocessing_decisions",
                "确认这题到底有没有附件数据。data_schema 没填就先跑 Step 4。"))
        else:
            out.append(Finding(
                "INFO", "not_applicable",
                "`data_schema` 为空且未提供 --scan：判为无附件数据题，本门不适用",
                "若实际有附件，先跑 Step 4 扫 schema，再回来过门。"))
        return out

    # ---- F1 有数据就必须有决策
    if not decisions:
        out.append(Finding(
            "FAIL", "missing_decisions",
            "`data_schema` 非空（有附件数据），但 `preprocessing_decisions` 是空的",
            "走 `stage_02_analysis.md` Step 4b 的闸门，**逐问**填。"
            "全部原样使用也要显式写 action=keep_as_is —— "
            "「没填」和「决定不动」在状态文件里长得一模一样。"))
        return out

    if not isinstance(decisions, dict):
        out.append(Finding(
            "FAIL", "bad_shape",
            "`preprocessing_decisions` 必须是 {Qi: [条目...]}，实际是 %s"
            % type(decisions).__name__,
            "键就是子问编号——**结构上强制逐问填**（anti_pattern Z18）。"))
        return out

    # ---- F7 静默坑排查结论
    if "silent_traps" not in schema:
        out.append(Finding(
            "FAIL", "missing_silent_traps",
            "`data_schema` 里没有 `silent_traps`（Step 4c 的产出）",
            "静默陷阱 §四 四条（混合类型 / 大小写 / 两列对不上 / 恒等式共线）"
            "要在本题附件上逐条验过，结论写进 `data_schema.silent_traps`。"
            "跑 `scan_attachments.py` 拿候选，判断仍要人做。"))

    # ---- F6 每个 Qi 都要有键
    qi_ids = []
    for card in decomposition:
        if isinstance(card, dict):
            qid = card.get("id") or card.get("qi") or card.get("name")
            if qid:
                qi_ids.append(str(qid))
        elif isinstance(card, str):
            m = re.match(r"\s*(Q\d+)", card)
            if m:
                qi_ids.append(m.group(1))
    for qid in qi_ids:
        if qid not in decisions:
            out.append(Finding(
                "FAIL", "missing_qi",
                "子问 %s 在 decomposition 里，但 preprocessing_decisions 没有它的键"
                % qid,
                "**逐问判断，不要一次性写死**：同一列在建模里可以是协变量、"
                "在判定质控里可以是门槛，两种用法并存不矛盾（Z18）。"
                "这一问不涉数据就写 [] 并在 rationale 里说明。"))

    # ---- 逐条校验
    all_actions: list[str] = []
    covered_cols: set[str] = set()
    for qid, entries in decisions.items():
        if not isinstance(entries, list):
            out.append(Finding(
                "FAIL", "bad_entry_list",
                "%s 的值必须是列表，实际是 %s" % (qid, type(entries).__name__)))
            continue
        for i, e in enumerate(entries):
            where = "%s[%d]" % (qid, i)
            if not isinstance(e, dict):
                out.append(Finding("FAIL", "bad_entry",
                                   "%s 不是对象" % where))
                continue
            missing = [f for f in REQUIRED_FIELDS if not str(e.get(f) or "").strip()]
            if missing:
                out.append(Finding(
                    "FAIL", "missing_field",
                    "%s 缺字段：%s" % (where, "、".join(missing)),
                    "每条都要写 column / action / nature / rationale。"))
                continue

            action = str(e["action"]).strip()
            nature = str(e["nature"]).strip()
            rationale = str(e["rationale"]).strip()
            covered_cols.add(str(e["column"]).strip())
            all_actions.append(action)

            if action not in ACTIONS:
                out.append(Finding(
                    "FAIL", "bad_action",
                    "%s 的 action=%r 不在枚举里" % (where, action),
                    "可选：" + "、".join("%s（%s）" % kv for kv in ACTIONS.items())))
                continue

            # ---- F4 Z3 方向：真动了数据，却自认是统计习惯
            if action != "keep_as_is" and any(h in nature
                                              for h in STATISTICAL_HABIT):
                out.append(Finding(
                    "FAIL", "statistical_habit",
                    "%s：action=%s（动了数据）但 nature=%r"
                    % (where, action, nature),
                    "**这正是 2025C 讲评点名不要做的那一类**（anti_pattern Z3）："
                    "「对问题附件中的数据无需进行清洗、删补、平衡等常规的、"
                    "无益于问题解决的预处理」。要么改成 keep_as_is，"
                    "要么说清它凭什么是领域方法的组成部分 / 题面要求 / 口径统一。"))

            # ---- F5 依据必须可追溯。三条判据分开报，理由才准确。
            low = rationale.lower()
            if any(b.lower() in low for b in BOILERPLATE):
                out.append(Finding(
                    "FAIL", "boilerplate_rationale",
                    "%s 的 rationale 是套话：%r" % (where, rationale[:40]),
                    "「常规做法」「标准流程」不是依据——组委会点名的恰恰是"
                    "「不从『问题』出发，乱套『方法』」。"
                    "写清这一步对**这道题**为什么必须做。"))
            elif action != "keep_as_is" and not any(m in rationale
                                                    for m in EVIDENCE_MARKERS):
                out.append(Finding(
                    "FAIL", "unsourced_rationale",
                    "%s 动了数据，但 rationale 里没有任何可追溯的出处：%r"
                    % (where, rationale[:40]),
                    "至少指到一个出处：题面原文 / 官方讲评 / 领域规范(GB…) / "
                    "文献 / 业务定义 / 仪器量程。**判据是有没有出处，不是写得长不长**"
                    "——「题面 85%~105% 为有效数据」只有 11 个字但依据完整，"
                    "「按 3σ 剔除极值」同样短却一个出处都没有。"))
            elif len(rationale) < MIN_RATIONALE_CHARS:
                out.append(Finding(
                    "FAIL", "thin_rationale",
                    "%s 的 rationale 只有 %d 个字：%r"
                    % (where, len(rationale), rationale),
                    "至少写清「依据是什么」和「因此这一步做/不做」。"))

            # ---- W2 说做了质控但一行没筛
            if action in MUTATING:
                rows = e.get("rows_affected")
                if isinstance(rows, (int, float)) and rows == 0:
                    out.append(Finding(
                        "WARN", "zero_rows_affected",
                        "%s：action=%s 但 rows_affected=0" % (where, action),
                        "写了要筛却一行没筛——多半是口径没真正落到代码里，"
                        "或者阈值写反了。核对一遍实际影响行数。"))

    # ---- W1 Z18 方向：全问全 keep_as_is
    if all_actions and set(all_actions) == {"keep_as_is"}:
        heavier = shape in DATA_SHAPES
        out.append(Finding(
            "WARN", "blanket_keep_as_is",
            "所有子问的所有条目都是 keep_as_is（共 %d 条）%s"
            % (len(all_actions),
               "，而 problem_shape=%s 属数据类题型" % shape if heavier else ""),
            "**多数题目这是正确答案，所以只是提醒。** 但请逐问再问一遍："
            "有没有哪一问的**领域方法内在就要求质控**？"
            "2025C 讲评那句「无需预处理」的限定语是「常规的、无益于问题解决的」，"
            "而同一份讲评里官方解问题 4 的第一步就是测序质控"
            "（5 个质量指标做中心 90% 截断，604 例筛到 501 例）。"
            "端到端复现实测：不做质控的合并模型 Sp 95% 时 Se 只有 0.373，"
            "官方逐染色体是 Se 0.92–1.00 @ Sp 99%——**差一个量级**（Z18）。"))

    # ---- W3 体检报了却没有对应决定
    if scan_cols:
        undecided = {c: sorted(k) for c, k in scan_cols.items()
                     if c not in covered_cols}
        if undecided:
            preview = list(undecided.items())[:6]
            out.append(Finding(
                "WARN", "scan_findings_undecided",
                "附件体检报了 %d 列，决策表里没有它们：%s"
                % (len(undecided),
                   "；".join("%s(%s)" % (c, "/".join(k)) for c, k in preview)),
                "体检报了却不给决定，等于扫了不看。每一列写一条——"
                "**包括决定原样使用**（action=keep_as_is + 理由）。"))

    return out


def scaffold(log: dict, scan_cols: dict[str, set[str]]) -> dict:
    """从附件体检结果生成决策表骨架，每个命中列一条待填条目。

    生成的条目 action 一律是 `TODO`，**故意不合法**——过门时会被
    `bad_action` 拦下。骨架的作用是列出"该决定哪些列"，不是替你决定。
    """
    stage2 = (log.get("stages") or {}).get("2") or {}
    qi_ids = []
    for card in stage2.get("decomposition") or []:
        if isinstance(card, dict):
            qid = card.get("id") or card.get("qi") or card.get("name")
            if qid:
                qi_ids.append(str(qid))
    if not qi_ids:
        qi_ids = ["Q1"]

    entries = [{
        "column": col,
        "action": "TODO",
        "nature": "TODO：统计习惯 / 领域方法组成部分 / 口径统一",
        "rationale": "TODO：引题面原文、官方讲评、领域规范或业务定义",
        "rows_affected": 0,
        "_scan_kinds": sorted(kinds),
    } for col, kinds in sorted(scan_cols.items())]

    return {"preprocessing_decisions": {qi: [dict(e) for e in entries]
                                        for qi in qi_ids},
            "_note": "action=TODO 是故意不合法的占位；填完再过门。"
                     "判据见 stage_02_analysis.md Step 4b。"
                     "**逐问填**：同一列在不同子问里可以有不同用法。"}


def main(argv: list[str] | None = None) -> int:
    _console.init()
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--decision-log", type=Path, required=True,
                    help="state/decision_log.json")
    ap.add_argument("--scan", type=Path,
                    help="scan_attachments.py --json 的报告，用于对账")
    ap.add_argument("--scaffold", action="store_true",
                    help="从 --scan 生成决策表骨架并打印，不过门")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    if not args.decision_log.is_file():
        print("找不到 decision_log: %s" % args.decision_log, file=sys.stderr)
        return 2
    log = _load_json(args.decision_log, "decision_log")

    scan_cols: dict[str, set[str]] | None = None
    if args.scan:
        if not args.scan.is_file():
            print("找不到 scan 报告: %s" % args.scan, file=sys.stderr)
            return 2
        scan_cols = _scan_columns(_load_json(args.scan, "scan 报告"))

    if args.scaffold:
        if not scan_cols:
            print("--scaffold 需要 --scan（骨架按体检命中的列生成）",
                  file=sys.stderr)
            return 2
        print(json.dumps(scaffold(log, scan_cols),
                         ensure_ascii=False, indent=2))
        return 0

    findings = check(log, scan_cols)
    fails = [f for f in findings if f.level == "FAIL"]
    warns = [f for f in findings if f.level == "WARN"]

    if args.as_json:
        print(json.dumps({
            "decision_log": str(args.decision_log),
            "fail": len(fails), "warn": len(warns),
            "findings": [f.as_dict() for f in findings],
        }, ensure_ascii=False, indent=2))
        return 1 if fails else 0

    print("数据口径闸门（Stage 2 Step 4b/4c）：%s" % args.decision_log)
    if not findings:
        print(_console.sym("\n✓ 通过：逐问都有决策，动数据的都给了非统计习惯的依据。"))
        return 0
    for f in findings:
        mark = {"FAIL": "✗", "WARN": "⚠", "INFO": "·"}[f.level]
        print(_console.sym("\n%s [%s] %s" % (mark, f.code, f.msg)))
        if f.action:
            print("    → " + f.action)
    print("\n%d 个 FAIL，%d 个 WARN。" % (len(fails), len(warns)))
    if fails:
        print("**有 FAIL 时 Stage 2 不得退出。** 判据见 "
              "题型与算法对照.md §四第一步 / anti_patterns.md Z3+Z18。")
    else:
        print(_console.sym("✓ 无 FAIL。WARN 逐条读一遍再决定要不要动。"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
