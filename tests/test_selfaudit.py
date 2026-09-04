#!/usr/bin/env python3
"""Regression tests for scripts/check_selfaudit.py.

这个 gate 存在的理由是三轮演练重复栽的同一处，所以测试也按那三处组织：
写了自检没跑、承诺只在散文里没进台账、把"本来就该做掉的活"写成了局限。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"mathmodel_selfaudit_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sa = load_script("check_selfaudit")


def kinds(issues) -> set[str]:
    return {i["kind"] for i in issues}


def run(tex: str, ledger: dict, results_dir=None):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "paper.tex"
        p.write_text(tex, encoding="utf-8")
        promises, limits, shortcuts = sa.scan([p])
    return sa.check(ledger, promises, limits, shortcuts, results_dir), \
        (promises, limits, shortcuts)


EMPTY = {"claims": [], "limitations": []}


class SentenceSplitTest(unittest.TestCase):
    def test_hard_wrapped_sentence_not_cut(self):
        """LaTeX 源码是硬换行的，按 \\n 断句会把一句话截成半截。"""
        tex = "本文对它们做了逐项敏感性分析（推荐时点落在 11.0--12.5 周），\n但无法从数据中确定。"
        sents = sa.sentences(tex)
        self.assertEqual(len(sents), 1)
        self.assertIn("但无法从数据中确定", sents[0])

    def test_environment_name_not_a_sentence(self):
        """只删命令名会把 enumerate / itemize 这些环境名留在正文里当句子扫。"""
        tex = "\\begin{enumerate}\n\\item 模型未考虑风场影响，这是一处简化。\n\\end{enumerate}"
        self.assertTrue(all("enumerate" not in s for s in sa.sentences(tex)))

    def test_table_row_skipped(self):
        tex = "solve\\_q1.py & 问题 1：逐项解析数值 + 八项极限退化自检 \\\\"
        self.assertEqual(sa.sentences(tex), [])

    def test_code_listing_skipped(self):
        tex = ("\\begin{lstlisting}\npython solve_q1.py  # 八项自检\n"
               "\\end{lstlisting}\n正文一句话，长度足够通过过滤。")
        self.assertTrue(all("solve_q1" not in s for s in sa.sentences(tex)))


class PromiseScanTest(unittest.TestCase):
    def test_unlogged_promise_is_fail(self):
        """演练里真正发生的那种：承诺写在散文里，从没进过台账。

        只查台账等于自己查自己——这条 FAIL 是整个 gate 的承重墙。
        """
        tex = "为确认符号无误，下面对 β=0 与 β=90° 做极限退化自检。"
        issues, _ = run(tex, EMPTY)
        self.assertIn("unlogged-promise", kinds(issues))

    def test_logged_and_done_passes(self):
        tex = "为确认符号无误，下面对 β=0 与 β=90° 做极限退化自检。"
        ledger = {"claims": [{
            "id": "SA1", "claim": "极限退化", "source_quote": "极限退化自检",
            "status": "done", "result_file": "results/selfaudit_q1.json",
            "verdict": "pass"}], "limitations": []}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "selfaudit_q1.json").write_text("{}", encoding="utf-8")
            issues, _ = run(tex, ledger, results_dir=Path(d))
        self.assertEqual(issues, [])

    def test_promised_but_not_run_is_fail(self):
        tex = "为确认符号无误，下面对 β=0 与 β=90° 做极限退化自检。"
        ledger = {"claims": [{"id": "SA1", "claim": "极限退化",
                              "source_quote": "极限退化自检",
                              "status": "promised"}], "limitations": []}
        issues, _ = run(tex, ledger)
        self.assertIn("unrun", kinds(issues))

    def test_done_without_evidence_is_fail(self):
        tex = "为确认符号无误，下面对 β=0 与 β=90° 做极限退化自检。"
        ledger = {"claims": [{"id": "SA1", "claim": "极限退化",
                              "source_quote": "极限退化自检",
                              "status": "done", "verdict": "pass"}],
                  "limitations": []}
        self.assertIn("no-evidence", kinds(run(tex, ledger)[0]))

    def test_failed_selfcheck_needs_action(self):
        """自检 fail 不是坏事，但必须写清后来怎么处理的。"""
        tex = "为确认符号无误，下面对 β=0 与 β=90° 做极限退化自检。"
        ledger = {"claims": [{"id": "SA1", "claim": "极限退化",
                              "source_quote": "极限退化自检", "status": "done",
                              "result_file": "results/x.json", "verdict": "fail"}],
                  "limitations": []}
        self.assertIn("unhandled-fail", kinds(run(tex, ledger)[0]))

    def test_dropped_needs_real_reason(self):
        tex = "为确认符号无误，下面对 β=0 与 β=90° 做极限退化自检。"
        ledger = {"claims": [{"id": "SA1", "claim": "极限退化",
                              "source_quote": "极限退化自检",
                              "status": "dropped", "dropped_reason": "没时间"}],
                  "limitations": []}
        self.assertIn("thin-reason", kinds(run(tex, ledger)[0]))

    def test_quote_must_be_substring(self):
        """引用对不上就报未了结——措辞改了必须重新确认，不能悄悄放过。"""
        tex = "为确认符号无误，下面对 β=0 与 β=90° 做极限退化自检。"
        ledger = {"claims": [{"id": "SA1", "claim": "极限退化",
                              "source_quote": "这句话论文里根本没有",
                              "status": "done", "result_file": "results/x.json",
                              "verdict": "pass"}], "limitations": []}
        self.assertIn("unlogged-promise", kinds(run(tex, ledger)[0]))


class LimitationScanTest(unittest.TestCase):
    def test_limitation_section_block_detected(self):
        """2025B 实测：局限写在 \\paragraph{局限。} 底下，分条里都没有"局限"二字。

        剥掉命令后标题只剩两个字，会被当碎片丢弃——只靠句式匹配就整段漏掉。
        """
        tex = ("\\paragraph{局限。}(1) 碳化硅的精度上限由介电常数的已知程度决定，"
               "若能独立反演之则可进一步收紧。\n")
        _, (_, limits, _) = run(tex, EMPTY)
        self.assertEqual(len(limits), 1)
        self.assertIn("区块内", limits[0]["why"])

    def test_unadjudicated_limitation_is_fail(self):
        tex = "\\paragraph{局限。}本方法未能考虑背面反射的影响，需要后续处理。"
        self.assertIn("unadjudicated-limit", kinds(run(tex, EMPTY)[0]))

    def test_should_have_done_unresolved_is_fail(self):
        """旗舰用例：自己指出了出路，却把它写成局限。"""
        tex = ("\\paragraph{局限。}本方法的精度上限由折射率的已知程度决定，"
               "若能独立反演折射率则可进一步收紧。")
        ledger = {"claims": [], "limitations": [{
            "id": "LM1", "quote": "精度上限由折射率的已知程度决定",
            "ruling": "should-have-done", "resolved": False}]}
        self.assertIn("should-have-done", kinds(run(tex, ledger)[0]))

    def test_should_have_done_resolved_passes(self):
        tex = ("\\paragraph{局限。}本方法的精度上限由折射率的已知程度决定，"
               "若能独立反演折射率则可进一步收紧。")
        ledger = {"claims": [], "limitations": [{
            "id": "LM1", "quote": "精度上限由折射率的已知程度决定",
            "ruling": "should-have-done", "resolved": True}]}
        self.assertEqual(run(tex, ledger)[0], [])

    def test_inherent_needs_basis(self):
        tex = "\\paragraph{局限。}本数据不具备真实标签，未能验证第二类结论。"
        ledger = {"claims": [], "limitations": [{
            "id": "LM1", "quote": "本数据不具备真实标签",
            "ruling": "inherent", "basis": ""}]}
        issues = run(tex, ledger)[0]
        self.assertIn("thin-basis", kinds(issues))
        self.assertTrue(all(i["level"] == "WARN" for i in issues
                            if i["kind"] == "thin-basis"))

    def test_population_description_not_a_limitation(self):
        """裸『尚未』会把"对一位尚未检测过的新孕妇"这种人群描述报成局限（2025C 实测）。"""
        tex = "对一位尚未检测过的新孕妇，单次检测可判读的概率约为八成。"
        _, (_, limits, _) = run(tex, EMPTY)
        self.assertEqual(limits, [])

    def test_body_section_named_不足_not_swept_in(self):
        """正文小节『搜索覆盖不足，不是题目性质』不是局限节，不该把整节拖进来。"""
        tex = ("\\subsection{搜索覆盖不足，不是题目性质}"
               "改为全段扫描后五机对三弹均有可行方案，说明原先是搜索范围的问题。")
        _, (_, limits, _) = run(tex, EMPTY)
        self.assertEqual(limits, [])


class ShortcutScanTest(unittest.TestCase):
    def test_constant_admission_flagged(self):
        """反模式 Z22 的机器可检形式。2025B paper.tex 里就明写着「硅在中红外取常数」。"""
        tex = "外延层介电函数取本征值：硅在中红外取常数 11.6964，碳化硅用单振子模型。"
        issues, (_, _, shortcuts) = run(tex, EMPTY)
        self.assertEqual(len(shortcuts), 1)
        self.assertIn("unadjudicated-shortcut", kinds(issues))

    def test_adjudicated_shortcut_passes(self):
        tex = "外延层介电函数取本征值：硅在中红外取常数 11.6964。"
        ledger = {"claims": [], "limitations": [{
            "id": "LM1", "quote": "硅在中红外取常数",
            "ruling": "out-of-scope",
            "basis": "题面只要求碳化硅层厚度，未提及硅层色散"}]}
        self.assertEqual(run(tex, ledger)[0], [])


class ScaffoldTest(unittest.TestCase):
    def test_scaffold_covers_every_hit(self):
        tex = ("下面做极限退化自检。\n"
               "\\paragraph{局限。}未能考虑背面反射。\n"
               "硅在中红外取常数 11.6964，属简化处理。")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "paper.tex"
            p.write_text(tex, encoding="utf-8")
            promises, limits, shortcuts = sa.scan([p])
        sk = sa.scaffold(promises, limits, shortcuts)
        self.assertEqual(len(sk["claims"]), len(promises))
        self.assertEqual(len(sk["limitations"]), len(limits) + len(shortcuts))

    def test_scaffold_output_fails_until_filled(self):
        """骨架是"全部待办"的状态，直接拿去检查必须不通过。"""
        tex = "下面做极限退化自检。\n\\paragraph{局限。}未能考虑背面反射。"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "paper.tex"
            p.write_text(tex, encoding="utf-8")
            promises, limits, shortcuts = sa.scan([p])
            sk = sa.scaffold(promises, limits, shortcuts)
            issues = sa.check(sk, promises, limits, shortcuts, None)
        self.assertTrue([i for i in issues if i["level"] == "FAIL"])


class TemplateTest(unittest.TestCase):
    def test_shipped_template_parses_and_documents_every_status(self):
        tpl = json.loads((ROOT / "templates" / "shared" / "self_audit.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(set(tpl["_status_doc"]), set(sa.VALID_STATUS))
        self.assertEqual(set(tpl["_ruling_doc"]), set(sa.VALID_RULING))


class CliTest(unittest.TestCase):
    def test_missing_ledger_returns_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "paper.tex"
            p.write_text("正文一句话，长度足够通过过滤。", encoding="utf-8")
            rc = sa.main(["--paper", str(p), "--ledger",
                          str(Path(d) / "nope.json")])
        self.assertEqual(rc, 2)

    def test_no_input_returns_2(self):
        self.assertEqual(sa.main(["--ledger", "x.json"]), 2)


if __name__ == "__main__":
    unittest.main()
