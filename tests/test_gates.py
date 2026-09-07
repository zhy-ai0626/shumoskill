#!/usr/bin/env python3
# 本文件的 docstring 里有 `\includegraphics`，所以必须是 raw 字符串。
# **这条测试写完第一次运行就抓住了本文件自己**——第四次踩同一脚，
# 而这正是 SyntaxWarningTest 存在的理由。留着这条注释当纪念。
r"""两个新提交门的回归测试，外加一条全仓 SyntaxWarning 守卫。

`check_data_decisions.py`（Stage 2 数据口径闸门）
------------------------------------------------
这条教条是**两轮演练、两个方向都栽过**换来的，所以门必须双向查，
测试也必须双向写：

- Z3 方向（动了数据却自认统计习惯）→ 必须 **FAIL**
- Z18 方向（全问全 keep_as_is）→ 只能 **WARN**

Z18 判成 FAIL 会逼人为了过门去动数据，正好掉进 Z3——**所以"只是 WARN"
本身就是一条需要被测试钉住的设计决定**，不是宽松。

`check_figures.py`（Stage 8/9 图表体检）
--------------------------------------
数量类判据只能是 WARN。仓库一贯立场是"经验值不能当官方评分线"
（`stage_08_writing.md` 明写 Do not treat empirical distributions as official rules）。
把图数做成硬门会逼人凑图，而官方点名的是"没有对结果进行分析"。
所以这里专门测：**图数为 0 也不许让退出码变 1**。

全仓 SyntaxWarning
------------------
`\includegraphics`、`\lambda`、`\,` 这类 LaTeX 片段写进非 raw 字符串，
Python 3.12 只给 SyntaxWarning（照跑），3.15 起变 SyntaxError。
**这一类在本轮开发中重复出现了三次**（gallery.py、test_compliance.py×2、
flow_pptx.py、check_figures.py），靠记性显然不行，做成测试。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import py_compile
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"gate_test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dd = load_script("check_data_decisions")
cf = load_script("check_figures")

TEMPLATE = json.loads(
    (ROOT / "templates" / "shared" / "decision_log.json")
    .read_text(encoding="utf-8"))


def make_log(decisions, *, shape="data_statistics", schema=None,
             qis=("Q1",)) -> dict:
    log = copy.deepcopy(TEMPLATE)
    log["problem_shape"] = shape
    s = log["stages"]["2"]
    s["decomposition"] = [{"id": q} for q in qis]
    s["data_schema"] = schema if schema is not None else {
        "附件1": {"rows": 100},
        "silent_traps": {"mixed_dtype": "已逐列查过，无混合类型列"},
    }
    s["preprocessing_decisions"] = decisions
    return log


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def levels(findings) -> dict[str, str]:
    return {f.code: f.level for f in findings}


OK_ENTRY = {
    "column": "全部列",
    "action": "keep_as_is",
    "nature": "口径统一",
    "rationale": "题面明确附件数据已整理，本问只做趋势描述，无需筛样本",
    "rows_affected": 0,
}
QC_ENTRY = {
    "column": "原始读段数等 5 个质量指标",
    "action": "qc_filter",
    "nature": "领域方法组成部分",
    "rationale": "官方讲评问题 4 第一步即测序质控：5 个质量指标做中心 90% 截断",
    "rows_affected": 103,
}


class DataDecisionsGateTest(unittest.TestCase):
    def test_clean_log_passes(self):
        log = make_log({"Q1": [OK_ENTRY], "Q2": [QC_ENTRY]}, qis=("Q1", "Q2"))
        self.assertEqual(dd.check(log), [])

    def test_missing_decisions_fails(self):
        log = make_log({})
        self.assertEqual(levels(dd.check(log)).get("missing_decisions"), "FAIL")

    def test_no_attachment_data_is_not_applicable(self):
        """无附件数据题（如 2024B 型只给参数表）这个门不适用，不能报 FAIL。"""
        log = make_log({}, shape="discrete_decision", schema={})
        found = dd.check(log)
        self.assertEqual(codes(found), {"not_applicable"})
        self.assertEqual(found[0].level, "INFO")

    def test_missing_silent_traps_fails(self):
        log = make_log({"Q1": [OK_ENTRY]}, schema={"附件1": {"rows": 100}})
        self.assertEqual(levels(dd.check(log)).get("missing_silent_traps"),
                         "FAIL")

    def test_missing_qi_key_fails(self):
        log = make_log({"Q1": [OK_ENTRY]}, qis=("Q1", "Q2", "Q3"))
        found = [f for f in dd.check(log) if f.code == "missing_qi"]
        self.assertEqual(len(found), 2, "Q2/Q3 都该被报出来")

    # ---- Z3 方向：必须 FAIL
    def test_z3_statistical_habit_fails(self):
        bad = dict(OK_ENTRY, action="qc_filter", nature="统计习惯",
                   rationale="题面要求剔除无效样本")
        self.assertEqual(levels(dd.check(make_log({"Q1": [bad]})))
                         .get("statistical_habit"), "FAIL")

    def test_z3_variants_of_habit_wording_all_caught(self):
        for wording in ("统计习惯", "常规预处理", "常规统计做法", "惯例"):
            bad = dict(OK_ENTRY, action="impute", nature=wording,
                       rationale="题面第 3 段要求补全缺测")
            self.assertIn("statistical_habit",
                          codes(dd.check(make_log({"Q1": [bad]}))), wording)

    def test_keep_as_is_with_habit_nature_is_allowed(self):
        """`keep_as_is` + nature="统计习惯" 是**正当**的——
        意思正是"这一步属于统计习惯，所以不做"。不能误判成 Z3。"""
        e = dict(OK_ENTRY, nature="统计习惯",
                 rationale="去重/插补属常规统计预处理，按讲评不做")
        self.assertNotIn("statistical_habit",
                         codes(dd.check(make_log({"Q1": [e]}))))

    # ---- rationale 三条判据要分得开
    def test_boilerplate_rationale_fails(self):
        e = dict(QC_ENTRY, rationale="常规做法")
        self.assertEqual(levels(dd.check(make_log({"Q1": [e]})))
                         .get("boilerplate_rationale"), "FAIL")

    def test_unsourced_rationale_fails(self):
        e = dict(QC_ENTRY, rationale="按 3σ 剔除极值")
        got = levels(dd.check(make_log({"Q1": [e]})))
        self.assertEqual(got.get("unsourced_rationale"), "FAIL")
        self.assertNotIn("boilerplate_rationale", got,
                         "有具体做法但没出处，理由应是『没有出处』而不是『套话』")

    def test_short_but_sourced_rationale_passes(self):
        """**判据是有没有出处，不是写得长不长。**
        「题面 85%~105% 有效」只有 12 个字但依据完整。"""
        e = dict(QC_ENTRY, rationale="题面 85%~105% 为有效数据")
        got = codes(dd.check(make_log({"Q1": [e]})))
        for c in ("boilerplate_rationale", "unsourced_rationale",
                  "thin_rationale"):
            self.assertNotIn(c, got)

    def test_keep_as_is_rationale_not_required_to_cite_source(self):
        """决定"不动"时不强求出处——不做是默认，做才需要举证。"""
        e = dict(OK_ENTRY, rationale="本问只做描述统计，不筛样本")
        self.assertNotIn("unsourced_rationale",
                         codes(dd.check(make_log({"Q1": [e]}))))

    def test_bad_action_enum_fails(self):
        e = dict(OK_ENTRY, action="TODO")
        self.assertEqual(levels(dd.check(make_log({"Q1": [e]})))
                         .get("bad_action"), "FAIL")

    def test_missing_field_fails(self):
        e = {k: v for k, v in QC_ENTRY.items() if k != "rationale"}
        self.assertEqual(levels(dd.check(make_log({"Q1": [e]})))
                         .get("missing_field"), "FAIL")

    # ---- Z18 方向：只能 WARN
    def test_z18_blanket_keep_as_is_is_warn_not_fail(self):
        """**这条是设计决定，不是宽松。** 判成 FAIL 会逼人为过门去动数据，
        正好掉进 Z3；而多数题目全 keep_as_is 就是正确答案。"""
        log = make_log({"Q1": [OK_ENTRY], "Q2": [OK_ENTRY]}, qis=("Q1", "Q2"))
        found = dd.check(log)
        self.assertEqual(levels(found).get("blanket_keep_as_is"), "WARN")
        self.assertEqual([f for f in found if f.level == "FAIL"], [])

    def test_z18_warning_carries_the_quantitative_evidence(self):
        """警告里必须带 2025C 的实测数字。没有数字的警告会被当噪声划过去。"""
        log = make_log({"Q1": [OK_ENTRY]})
        w = [f for f in dd.check(log) if f.code == "blanket_keep_as_is"][0]
        self.assertIn("0.373", w.action)
        self.assertIn("501", w.action)

    def test_zero_rows_affected_warns(self):
        e = dict(QC_ENTRY, rows_affected=0)
        self.assertEqual(levels(dd.check(make_log({"Q1": [e]})))
                         .get("zero_rows_affected"), "WARN")

    # ---- 与 scan_attachments 对账
    def test_scan_findings_without_decision_warn(self):
        scan_cols = {"孕妇BMI": {"identity_collinear"},
                     "检测孕周": {"mixed_dtype", "derived_mismatch"}}
        log = make_log({"Q1": [OK_ENTRY]})
        found = dd.check(log, scan_cols)
        self.assertEqual(levels(found).get("scan_findings_undecided"), "WARN")

    def test_scan_column_covered_no_warn(self):
        scan_cols = {"孕妇BMI": {"identity_collinear"}}
        e = dict(OK_ENTRY, column="孕妇BMI")
        self.assertNotIn("scan_findings_undecided",
                         codes(dd.check(make_log({"Q1": [e]}), scan_cols)))

    def test_scan_columns_parsed_from_real_report_shape(self):
        report = [{"file": "附件.xlsx", "sheet": "s", "findings": [
            {"kind": "identity_collinear", "msg": "...",
             "columns": ["体重", "孕妇BMI"]},
            {"kind": "all_nan", "msg": "...", "columns": ["Unnamed: 20"]},
        ]}]
        got = dd._scan_columns(report)
        self.assertEqual(set(got), {"体重", "孕妇BMI"},
                         "all_nan 不在需要决策的 kind 里，不该进来")

    def test_scaffold_lists_every_flagged_column_per_qi(self):
        log = make_log({}, qis=("Q1", "Q2"))
        out = dd.scaffold(log, {"a": {"mixed_dtype"}, "b": {"case_collision"}})
        pd = out["preprocessing_decisions"]
        self.assertEqual(set(pd), {"Q1", "Q2"})
        self.assertEqual({e["column"] for e in pd["Q1"]}, {"a", "b"})
        # 骨架里的 action 故意不合法，过门时会被 bad_action 拦下
        self.assertTrue(all(e["action"] == "TODO" for e in pd["Q1"]))

    def test_scaffold_output_fails_the_gate(self):
        """骨架**必须过不了门**——否则生成完直接过关，等于没填也算填了。"""
        log = make_log({}, qis=("Q1",))
        out = dd.scaffold(log, {"a": {"mixed_dtype"}})
        log["stages"]["2"]["preprocessing_decisions"] = \
            out["preprocessing_decisions"]
        self.assertTrue([f for f in dd.check(log) if f.level == "FAIL"])


class FiguresCheckTest(unittest.TestCase):
    def _write(self, d: Path, tex: str, files=()) -> Path:
        (d / "figs").mkdir(exist_ok=True)
        for name in files:
            (d / "figs" / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        p = d / "paper.tex"
        p.write_text(tex, encoding="utf-8")
        return p

    def test_missing_image_file_fails(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "\\includegraphics{figs/nope.png}\n")
            found, _ = cf.check(p, None, d / "figs")
            self.assertEqual(levels(found).get("missing_image_file"), "FAIL")

    def test_existing_image_passes(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "\\includegraphics{figs/a.png}\n", ["a.png"])
            self.assertNotIn("missing_image_file",
                             codes(cf.check(p, None, d / "figs")[0]))

    def test_extension_may_be_omitted(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "\\includegraphics{figs/a}\n", ["a.png"])
            self.assertNotIn("missing_image_file",
                             codes(cf.check(p, None, d / "figs")[0]))

    def test_commented_include_is_not_counted(self):
        """注释掉一张图，计数必须跟着降。否则改稿之后这个检查开始骗人。"""
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d,
                            "\\includegraphics{figs/a.png}\n"
                            "% \\includegraphics{figs/ghost.png}\n",
                            ["a.png"])
            found, stats = cf.check(p, None, d / "figs")
            self.assertEqual(stats["figures"], 1)
            self.assertNotIn("missing_image_file", codes(found))

    def test_escaped_percent_is_not_a_comment(self):
        r"""`±10\%` 里的 `\%` 是转义百分号，不是注释起点。
        砍错了会把后半行连同 `\includegraphics` 一起吃掉，图数静默变少。"""
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d,
                            "扰动 ±10\\% 时 \\includegraphics{figs/a.png}\n",
                            ["a.png"])
            self.assertEqual(cf.check(p, None, d / "figs")[1]["figures"], 1)

    def test_dangling_ref_fails(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "见图~\\ref{fig:nowhere}。\n")
            self.assertEqual(levels(cf.check(p, None, None)[0])
                             .get("dangling_ref"), "FAIL")

    def test_duplicate_label_fails(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "\\label{fig:a}\\label{fig:a}\\ref{fig:a}\n")
            self.assertEqual(levels(cf.check(p, None, None)[0])
                             .get("duplicate_label"), "FAIL")

    def test_unreferenced_label_warns(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "\\label{fig:lonely}\n")
            self.assertEqual(levels(cf.check(p, None, None)[0])
                             .get("label_never_referenced"), "WARN")

    def test_gray_proof_is_not_an_orphan(self):
        """`_gray.png` 是给自己看的灰度校样，不进论文，不该报成漏用。"""
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "\\includegraphics{figs/a.png}\n",
                            ["a.png", "a_gray.png"])
            self.assertNotIn("orphan_figure",
                             codes(cf.check(p, None, d / "figs")[0]))

    def test_orphan_figure_warns(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "\\includegraphics{figs/a.png}\n",
                            ["a.png", "unused.png"])
            self.assertEqual(levels(cf.check(p, None, d / "figs")[0])
                             .get("orphan_figure"), "WARN")

    def test_counts_are_warn_only_never_fail(self):
        """**这是设计决定：经验分布不是规则。** 一张图都没有也不许 FAIL。"""
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "纯文字，没有任何图表。\n")
            found, stats = cf.check(p, None, None, topic="A")
            self.assertEqual(stats["figures"], 0)
            self.assertIn("below_p25_figure_count", codes(found))
            self.assertEqual([f for f in found if f.level == "FAIL"], [])

    def test_topic_quantiles_differ_from_overall(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(d, "x\n")
            a = cf.check(p, None, None, topic="A")[1]
            allq = cf.check(p, None, None, topic=None)[1]
            self.assertIn("A 题", a["quantile_basis"])
            self.assertIn("全体", allq["quantile_basis"])
            self.assertIsNotNone(a["figure_p25"])

    def test_markdown_workspace_supported(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            ws = d / "ws"
            ws.mkdir()
            (d / "figs").mkdir()
            (d / "figs" / "a.png").write_bytes(b"x")
            (ws / "06_models.md").write_text(
                "![龙卷风图](../figs/a.png)\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                encoding="utf-8")
            found, stats = cf.check(None, ws, d / "figs")
            self.assertEqual(stats["figures"], 1)
            self.assertEqual(stats["tables"], 1)
            self.assertNotIn("missing_image_file", codes(found))

    def test_bibliography_labels_excluded(self):
        """参考文献段里全是 bibitem 的 label，不该参与悬挂引用统计。"""
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            p = self._write(
                d,
                "正文。\n\\begin{thebibliography}{9}\n"
                "\\bibitem{x}\\label{bib:x}\n\\end{thebibliography}\n")
            self.assertNotIn("label_never_referenced",
                             codes(cf.check(p, None, None)[0]))


class SyntaxWarningTest(unittest.TestCase):
    """全仓不许有 SyntaxWarning。

    最常见的来源是 LaTeX 片段写进非 raw 字符串：`\\includegraphics`、
    `\\lambda`、`\\,` 里的 `\\i` `\\l` `\\,` 都是无效转义。
    Python 3.12 只给警告（代码照跑），**3.15 起变 SyntaxError**。
    这一类在本轮开发里重复出现了三次以上，靠记性不行。
    """

    def test_no_syntax_warnings_anywhere(self):
        offenders: list[str] = []
        for path in sorted(ROOT.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", SyntaxWarning)
                try:
                    py_compile.compile(str(path), cfile=str(
                        Path(tempfile.gettempdir()) / "syntaxcheck.pyc"),
                        doraise=True)
                except py_compile.PyCompileError as exc:
                    offenders.append("%s 编译失败：%s"
                                     % (path.relative_to(ROOT),
                                        str(exc).strip()[:120]))
                    continue
            for w in caught:
                if issubclass(w.category, SyntaxWarning):
                    offenders.append("%s:%s %s"
                                     % (path.relative_to(ROOT),
                                        w.lineno, w.message))
        self.assertEqual(offenders, [], "\n".join(
            ["有 SyntaxWarning（3.15 起会变 SyntaxError）："] + offenders
            + ["修法：含 LaTeX 反斜杠的字符串/docstring 加 `r` 前缀。"]))


if __name__ == "__main__":
    unittest.main()
