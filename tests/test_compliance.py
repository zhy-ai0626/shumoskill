#!/usr/bin/env python3
"""Regression tests for scripts/check_compliance.py.

不造真 PDF：pypdf 只被用来取「每页文本 + mediabox + metadata」三样东西，
用一个假 reader 就能把所有判定分支覆盖到，而且跑得比编译 LaTeX 快得多。
真 PDF 上的实测由 doctor 与开赛前的手动跑覆盖。
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"mathmodel_compliance_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cc = load_script("check_compliance")


class FakeBox:
    def __init__(self, w=595.276, h=841.89):
        self.width, self.height = w, h


class FakePage:
    def __init__(self, text, box=None):
        self._text = text
        self.mediabox = box or FakeBox()

    def extract_text(self):
        return self._text


class FakeReader:
    def __init__(self, pages, metadata=None):
        self.pages = [FakePage(t) for t in pages]
        self.metadata = metadata


# 一份"什么都对"的论文，各用例只改动其中一页来制造单点违规。
GOOD_PAGES = [
    "摘 要\n本文针对某问题建立了模型。\n关键词：模型；求解",
    "1 问题重述\n题目要求……" + "中文" * 200,
    "2 模型建立\n" + "中文" * 200,
    "参考文献\n[1] 某某. 某书. 2020.\n"
    "AI 工具使用声明\n本参赛队在竞赛过程中未使用任何 AI 工具",
    "附录\n附录 A 源程序\nimport numpy",
]
# AI 声明必须在参考文献之前，上面那页顺序是反的，单独给一份正确的
GOOD_PAGES_AI_OK = GOOD_PAGES[:3] + [
    "AI 工具使用声明\n本参赛队在竞赛过程中未使用任何 AI 工具\n"
    "参考文献\n[1] 某某. 某书. 2020.",
    GOOD_PAGES[4],
]


def run(pages, metadata=None, support=None, size_bytes=1024):
    """跑一遍 check_paper，返回 {check_id: level}。"""
    rep = cc.Report()
    reader = FakeReader(pages, metadata)
    with mock.patch("pypdf.PdfReader", return_value=reader), \
         mock.patch("os.path.getsize", return_value=size_bytes):
        cc.check_paper("fake.pdf", support, rep)
    return {i["id"]: i["level"] for i in rep.items}, rep


class PageIndexTest(unittest.TestCase):
    def test_heading_mid_page_is_found(self):
        """回归：`^\\s*附\\s*录` 不带 re.M 时只匹配整页开头，永远找不到附录页。

        真实 PDF 里附录标题前面必然还有上一节的残余文本。
        这个 bug 让『正文页数』这条永远退化成人工项。
        """
        pages = ["摘要", "正文", "26-32.\n附录\n附录 A 程序清单"]
        self.assertEqual(cc._page_index(pages, r"^\s*附\s*录"), 3)

    def test_missing_returns_zero(self):
        self.assertEqual(cc._page_index(["摘要"], r"^\s*附\s*录"), 0)


class AppendixHeadingTest(unittest.TestCase):
    """附录标题的编号前缀。2023A 演练实测：\\appendix 渲染成 "A 附录：源程序清单"，
    只认行首裸『附录』会让正文页数这一项永远退化成人工。"""

    def _page_of_appendix(self, pages):
        levels, rep = run(pages)
        item = next(i for i in rep.items if i["id"] == "body_pages")
        return item["level"], item.get("detail", "") + item.get("note", "")

    def test_lettered_appendix_found(self):
        pages = GOOD_PAGES_AI_OK[:4] + ["A 附录：源程序清单\nimport numpy"]
        level, _ = self._page_of_appendix(pages)
        self.assertNotEqual(level, "MANUAL", "带编号的附录标题应被定位到")

    def test_bare_appendix_still_found(self):
        pages = GOOD_PAGES_AI_OK[:4] + ["附录\n附录 A 程序清单"]
        level, _ = self._page_of_appendix(pages)
        self.assertNotEqual(level, "MANUAL")

    def test_prose_mention_not_mistaken_for_heading(self):
        """正文里的"按题面附录"「见附录B」不能被当成附录页起点。"""
        self.assertEqual(
            cc._page_index(["按题面附录，赤纬角的起算点是春分。见附录 B 的推导。"],
                           r"^\s*(?:[A-Z]|\d+)?[\s.、:：]*附\s*录"), 0)


class ZipNameTest(unittest.TestCase):
    def test_gbk_filename_recovered(self):
        """WinRAR 打的中文包：GBK 字节 + 不置 UTF-8 标志位，ZipFile 按 cp437 解成乱码。

        这里直接测解码函数——zipfile 写文件时对非 ASCII 名一律置 UTF-8 标志，
        用它造不出老式条目。
        """
        legacy = cc.AI_DETAIL_NAME.encode("gbk").decode("cp437")
        self.assertNotEqual(legacy, cc.AI_DETAIL_NAME)
        self.assertEqual(cc._decode_entry_name(legacy, utf8_flag=False),
                         cc.AI_DETAIL_NAME)

    def test_utf8_flagged_name_untouched(self):
        self.assertEqual(cc._decode_entry_name(cc.AI_DETAIL_NAME, utf8_flag=True),
                         cc.AI_DETAIL_NAME)

    def test_modern_zip_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.zip"
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr(cc.AI_DETAIL_NAME, b"x")
            self.assertIn(cc.AI_DETAIL_NAME, cc._zip_names(str(p)))

    def test_non_zip_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.rar"
            p.write_bytes(b"Rar!\x1a\x07\x00not really")
            self.assertIsNone(cc._zip_names(str(p)))


class PaperCheckTest(unittest.TestCase):
    def test_clean_paper_passes(self):
        levels, rep = run(GOOD_PAGES_AI_OK)
        fails = [i for i in rep.items if i["level"] == "FAIL"]
        self.assertEqual(fails, [], "干净论文不该有 FAIL：%s"
                         % [(i["id"], i["note"]) for i in fails])

    def test_garbled_chinese_fails(self):
        """fontset=fandol 的症状：编译成功、显示正常，提取出来是乱码。"""
        levels, _ = run(["ק ᅋေ ӱҵ"] * 5)
        self.assertEqual(levels["zh_extractable"], "FAIL")

    def test_abstract_overflow_detected(self):
        pages = list(GOOD_PAGES_AI_OK)
        pages[0] += "\n1 问题重述"
        levels, _ = run(pages)
        self.assertEqual(levels["abstract_one_page"], "FAIL")

    def test_toc_and_cover_rejected(self):
        pages = ["目录"] + GOOD_PAGES_AI_OK
        levels, _ = run(pages)
        self.assertEqual(levels["no_toc"], "FAIL")
        pages = ["承诺书"] + GOOD_PAGES_AI_OK
        levels, _ = run(pages)
        self.assertEqual(levels["no_cover"], "FAIL")

    def test_official_phrase_must_be_verbatim(self):
        pages = list(GOOD_PAGES_AI_OK)
        pages[3] = ("AI 工具使用声明\n本队未使用任何人工智能工具\n参考文献\n[1] x")
        levels, _ = run(pages)
        self.assertEqual(levels["ai_verbatim"], "FAIL")

    def test_ai_declaration_after_references_fails(self):
        levels, _ = run(GOOD_PAGES)      # 这份里声明排在参考文献之后
        self.assertEqual(levels["ai_before_ref"], "FAIL")

    def test_competition_name_is_not_identity_leak(self):
        """『全国大学生数学建模竞赛』里的"大学"不能触发身份泄露误报。"""
        pages = list(GOOD_PAGES_AI_OK)
        pages[1] += "\n本文参加全国大学生数学建模竞赛。"
        levels, _ = run(pages)
        self.assertEqual(levels["identity_text"], "PASS")

    def test_real_identity_leak_caught(self):
        pages = list(GOOD_PAGES_AI_OK)
        pages[1] += "\n指导教师：张某某"
        levels, _ = run(pages)
        self.assertEqual(levels["identity_text"], "FAIL")

    def test_metadata_identity_caught(self):
        """正文擦干净了，文件属性里还留着作者——肉眼查不到的那一类。"""
        levels, _ = run(GOOD_PAGES_AI_OK, metadata={"/Author": "某某大学 张三"})
        self.assertEqual(levels["identity_meta"], "FAIL")

    def test_body_page_count_computed(self):
        levels, rep = run(GOOD_PAGES_AI_OK)
        item = next(i for i in rep.items if i["id"] == "body_pages")
        self.assertEqual(item["level"], "PASS")
        self.assertIn("正文约 3 页", item["detail"])   # 第2页问题重述 → 第5页附录

    def test_oversize_paper_fails(self):
        levels, _ = run(GOOD_PAGES_AI_OK, size_bytes=21 * 1024 * 1024)
        self.assertEqual(levels["size"], "FAIL")


class SupportArchiveTest(unittest.TestCase):
    def _zip(self, d, names):
        p = Path(d) / "support.zip"
        with zipfile.ZipFile(p, "w") as zf:
            for n in names:
                zf.writestr(n, b"x")
        return str(p)

    def test_missing_ai_detail_caught(self):
        pages = list(GOOD_PAGES_AI_OK)
        pages[3] = ("AI 工具使用声明\n本参赛队在竞赛过程中使用了 AI 工具\n"
                    "参考文献\n[1] x")
        with tempfile.TemporaryDirectory() as d:
            sup = self._zip(d, ["solve.py"])
            levels, _ = run(pages, support=sup)
        self.assertEqual(levels["support_ai_detail"], "FAIL")
        self.assertEqual(levels["support_code"], "PASS")

    def test_no_code_in_archive_caught(self):
        with tempfile.TemporaryDirectory() as d:
            sup = self._zip(d, ["结果.xlsx", "图1.png"])
            levels, _ = run(GOOD_PAGES_AI_OK, support=sup)
        self.assertEqual(levels["support_code"], "FAIL")

    def test_credential_file_warned(self):
        with tempfile.TemporaryDirectory() as d:
            sup = self._zip(d, ["solve.py", ".env"])
            levels, _ = run(GOOD_PAGES_AI_OK, support=sup)
        self.assertEqual(levels["support_no_secret"], "WARN")


class Stage9FieldsTest(unittest.TestCase):
    def test_manual_yields_null_not_false(self):
        rep = cc.Report()
        rep.add("identity_text", "x", True)
        rep.add("identity_meta", "x", True)
        rep.add("body_pages", "x", None)
        rep.add("size", "x", True)
        rep.add("abstract_one_page", "x", True)
        fields = cc.stage9_fields(rep)
        self.assertTrue(fields["anonymity_passed"])
        self.assertIsNone(fields["page_limit_passed"],
                          "没测到必须是 null，写成 false 会让人去修不存在的问题")

    def test_fail_yields_false(self):
        rep = cc.Report()
        rep.add("identity_text", "x", False)
        rep.add("identity_meta", "x", True)
        self.assertFalse(cc.stage9_fields(rep)["anonymity_passed"])


class CliTest(unittest.TestCase):
    def test_other_competition_refused(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cc.main(["--paper", "fake.pdf", "--competition", "mcm"])
        self.assertEqual(rc, 2, "只编码了 CUMCM 规则，不能冒充检查别的赛事")

    def test_missing_paper_refused(self):
        rc = cc.main(["--paper", "does-not-exist-xyz.pdf"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()


class CheckNumbersThousandsTest(unittest.TestCase):
    """LaTeX 千分位 `\,` 必须先合并再取数。

    2023A 演练实测：论文里写 119\,120（= 119120 m²），
    被切成 119 与 120 两个数，双双报成"结果文件里找不到"。
    这类误报会让人直接不信任这个脚本。
    """

    def setUp(self):
        self.cn = load_script("check_numbers")

    def test_thin_space_thousands_merged(self):
        vals = [v for v, _ in self.cn.extract_numbers(r"总面积 119\,120 m$^2$")]
        self.assertIn(119120.0, vals)
        self.assertNotIn(119.0, vals)

    def test_plain_number_untouched(self):
        vals = [v for v, _ in self.cn.extract_numbers("效率 0.5038")]
        self.assertIn(0.5038, vals)

    def test_not_a_thousands_separator(self):
        """`\,` 后面不是恰好三位数字时不合并，例如 5\,MW。"""
        vals = [v for v, _ in self.cn.extract_numbers(r"功率 60.01\,MW")]
        self.assertIn(60.01, vals)

    def test_bare_long_number_extracted(self):
        """四位以上的裸数字原先一个都匹配不上——静默跳过，不检查也不报。"""
        vals = [v for v, _ in self.cn.extract_numbers("镜面总面积 119120 平方米")]
        self.assertIn(119120.0, vals)

    def test_comma_thousands_still_work(self):
        vals = [v for v, _ in self.cn.extract_numbers("总计 1,234.56 元")]
        self.assertIn(1234.56, vals)


class GatesSmokeTest(unittest.TestCase):
    """doctor 的 gates-smoke：真跑三个提交门，而不是只确认文件存在。

    两个坑都是实测踩出来的，测试盯住它们：
    1. 只看退出码不行——Python 抛 SyntaxError 时退出码也是 1，与"门正确报出问题"撞车；
    2. `text=True` 在中文 Windows 上按 GBK 解码子进程的 UTF-8 输出，
       UnicodeDecodeError 在 subprocess 的读取线程里抛出，父进程拿到的 stdout 是
       **None** 且看不到任何异常——标记匹配永远不成立，检查静默失效。
    """

    def setUp(self):
        self.doctor = load_script("doctor")

    def test_healthy_tree_passes(self):
        ok, detail = self.doctor._smoke_gates()
        self.assertTrue(ok, detail)
        for name in ("selfaudit", "numbers", "compliance"):
            self.assertIn(name, detail)

    def test_check_is_registered(self):
        checks = self.doctor.run_checks(competition="cumcm", check_tools=False)
        self.assertIn("gates-smoke", {c.name for c in checks})
