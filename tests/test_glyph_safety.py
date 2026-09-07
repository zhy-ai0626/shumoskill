#!/usr/bin/env python3
"""字形与编码安全：**图上不能出现方框，终端不能因为一个符号崩掉。**

为什么单独一个文件
------------------
这两件事都不报错，只出错：

- **图上的方框**：matplotlib 遇到字体里没有的字形，只刷一条 findfont 警告，
  图照出——一个空方框。`axes.unicode_minus=False` 只管刻度标签自动生成的负号，
  **管不了你自己写进 `label=` 里的 U+2212**。实测 SimHei 没有 U+2212 的字形，
  `label="参数 −10%"` 在图例里就是个框。
- **终端崩掉**：中文 Windows 把 stdout 编码定成 cp936(GBK)。一旦输出被管道或
  重定向接走，`print("✓ 通过")` 抛 UnicodeEncodeError，脚本**当场崩**。
  实测 `python ahp_template.py > log.txt` 就会。

两条都踩过（`静默陷阱.md §3.5.3`、`scripts/_console.py` 的模块 docstring），
所以做成测试盯住，不靠记性。

判据
----
GBK 里**有**这些：`→ U+2192`、`— U+2014`、`± U+00B1`、`× U+00D7`——可以用。
GBK 里**没有**这些：`✓ U+2713`、`✗ U+2717`、`⚠ U+26A0`、`− U+2212`、
`↳ U+21B3`、`✅ ❌ ⭐`——**不许出现在 print 的字符串或图的文字里**。
注释和 docstring 不受限制（它们不进输出）。

例外：`scripts/` 下的脚本可以用，因为它们统一走 `_console.sym()`
——那个函数会在编不出的时候把符号降级成 ASCII。
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# GBK 编不出的状态符号。逐个用 encode 验，不硬编码码点表——
# 硬编码的表会和实际的 codec 行为漂移。
CANDIDATES = "✓✗⚠✅❌⭐↳−✔✘►•‣"


def _gbk_unsafe() -> set[str]:
    bad = set()
    for ch in CANDIDATES:
        try:
            ch.encode("gbk")
        except UnicodeEncodeError:
            bad.add(ch)
    return bad


UNSAFE = _gbk_unsafe()

# 会进"输出"的地方：终端 print，或 matplotlib 的文字参数
OUTPUT_SITE = re.compile(
    r"\bprint\s*\(|\blabel\s*=|\btitle\s*=|set_title|set_xlabel|set_ylabel|"
    r"\.text\s*\(|annotate_value\s*\(|add_units_note\s*\(|cbar_label\s*=")

# scripts/ 走 _console.sym() 统一降级，不在本测试的管辖范围
SCOPE = ("code-templates", "templates", "figures")


def _py_files():
    for top in SCOPE:
        for p in sorted((ROOT / top).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            yield p


def _string_literals(path: Path, skip_sym: bool = True) -> list[tuple[int, str]]:
    """只取**字符串字面量**，跳过注释、docstring，以及 `_console.sym()` 的参数。

    用 AST 而不是正则扫行，两个原因：

    1. 注释里写"别用 ✓"是完全正当的（本仓库到处都是）。按行正则扫会把这些
       说明文字全报成问题，测试就没人看了——**输出太长和没有输出等价**。
    2. `print(_console.sym("✓ ..."))` 是**正确**写法：`sym()` 会在当前编码
       编不出时把符号降级成 `[OK]`。豁免必须精确到"这个字面量是不是 sym 的
       参数"，而不是"这个文件里有没有出现过 sym"——后者等于整文件免检，
       同一文件里漏包一个 print 就查不出来了。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                exempt.add(id(body[0].value))          # docstring
        if skip_sym and isinstance(node, ast.Call):
            fn = node.func
            is_sym = (isinstance(fn, ast.Attribute) and fn.attr == "sym") or \
                     (isinstance(fn, ast.Name) and fn.id == "sym")
            if is_sym:
                # sym() 的参数可能是 `"..." % (...)` 这种 BinOp，
                # 所以要把整棵子树里的字符串都豁免掉
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) \
                            and isinstance(sub.value, str):
                        exempt.add(id(sub))

    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in exempt:
            out.append((node.lineno, node.value))
    return out


class GbkUnsafeGlyphTest(unittest.TestCase):
    def test_candidates_actually_unsafe(self):
        """先确认判据本身成立——否则这个测试可能在空转。"""
        self.assertIn("✓", UNSAFE)
        self.assertIn("⚠", UNSAFE)
        self.assertIn("−", UNSAFE)          # U+2212，不是 ASCII 连字符
        # 这几个 GBK 有，不该被误判
        for ch in ("→", "—", "±", "×"):
            self.assertNotIn(ch, UNSAFE, ch)

    def test_no_unsafe_glyph_in_output_strings(self):
        """print / matplotlib 文字里不许出现 GBK 编不出的符号。"""
        offenders: list[str] = []
        for path in _py_files():
            lines = path.read_text(encoding="utf-8").splitlines()
            for lineno, text in _string_literals(path):
                hit = [c for c in text if c in UNSAFE]
                if not hit:
                    continue
                # 该字面量所在行（或紧邻上一行，处理续行）是否是输出点
                window = "\n".join(lines[max(0, lineno - 2):lineno + 1])
                if OUTPUT_SITE.search(window):
                    offenders.append(
                        "%s:%d 输出字符串里有 %s —— %r"
                        % (path.relative_to(ROOT), lineno,
                           "".join(sorted(set(hit))), text[:48]))
        self.assertEqual(
            offenders, [],
            "\n".join(["这些符号 GBK 编不出："] + offenders
                      + ["修法：print 用 [OK]/[X]/[!]，或包一层 _console.sym()；"
                         "图上的负号用 ASCII `-`。"
                         "→ — ± × 在 GBK 里有，可以继续用。"]))

    def test_sym_exemption_is_per_literal_not_per_file(self):
        """豁免必须精确到字面量。**同一个文件里漏包一个 print 也要能查出来。**

        这条是给上一条测试的判据做体检：如果哪天有人把豁免改成"文件里出现过
        sym 就整文件免检"，这条会失败。自检只覆盖它真正测过的那一维——
        判据本身也要被测。
        """
        import tempfile
        src = (
            "import _console\n"
            "def f():\n"
            "    print(_console.sym('包了 ✓ 的'))\n"
            "    print('没包 ✗ 的')\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.py"
            p.write_text(src, encoding="utf-8")
            got = {t for _, t in _string_literals(p)}
        self.assertNotIn("包了 ✓ 的", got, "sym() 的参数应当被豁免")
        self.assertIn("没包 ✗ 的", got, "同文件里没包 sym 的仍必须被查出来")

    def test_runnable_templates_survive_gbk_stdout(self):
        """把 stdout 换成 GBK 再 import 一遍模板，确认 import 期的 print 不崩。

        只覆盖 import 期。函数体里的 print 靠上一条静态检查——
        动态跑全部模板需要 sklearn/statsmodels 全装齐，不是本测试的范围。
        **写清楚这条只覆盖 import 期**，免得"测试通过"被当成"全都安全"。
        """
        import contextlib
        import importlib.util
        import io

        targets = [
            ROOT / "templates/shared/code_starter/simulation.py",
            ROOT / "templates/shared/code_starter/classification.py",
            ROOT / "templates/shared/code_starter/evaluation.py",
        ]
        for path in targets:
            if not path.exists():
                continue
            buf = io.TextIOWrapper(io.BytesIO(), encoding="gbk",
                                   errors="strict")
            spec = importlib.util.spec_from_file_location(
                "glyphtest_" + path.stem, path)
            module = importlib.util.module_from_spec(spec)
            try:
                with contextlib.redirect_stdout(buf):
                    spec.loader.exec_module(module)
            except UnicodeEncodeError as exc:
                self.fail("%s 在 GBK stdout 下 import 就崩了：%s"
                          % (path.name, exc))
            except ImportError:
                pass                     # 缺第三方依赖，与本测试无关


class FontGlyphTest(unittest.TestCase):
    """图上的文字，本机中文字体里得真有这些字形。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "figures"))
        import matplotlib
        matplotlib.use("Agg")
        import cumcm_style
        cls.cs = cumcm_style
        name = cumcm_style.available_cn_font()
        if name is None:
            raise unittest.SkipTest("本机没有中文字体")
        import matplotlib.font_manager as fm
        from matplotlib.ft2font import FT2Font
        cls.charmap = set(FT2Font(fm.findfont(name)).get_charmap())
        cls.font_name = name

    def test_minus_sign_missing_from_cn_font_as_expected(self):
        """判据自检：U+2212 确实不在中文字体里——所以图上不能用它。"""
        self.assertNotIn(0x2212, self.charmap,
                         "%s 居然有 U+2212，这条判据要重新评估" % self.font_name)
        self.assertIn(0x2192, self.charmap)      # → 有，可以用

    def test_gallery_and_starter_labels_render(self):
        """gallery 与 starter 的图上文字，逐字确认字体里有字形。"""
        missing: list[str] = []
        for rel in ("figures/gallery.py", "figures/starter.py",
                    "figures/cumcm_style.py"):
            path = ROOT / rel
            lines = path.read_text(encoding="utf-8").splitlines()
            for lineno, text in _string_literals(path):
                window = "\n".join(lines[max(0, lineno - 2):lineno + 1])
                if not re.search(r"label\s*=|title\s*=|set_title|set_xlabel|"
                                 r"set_ylabel|\.text\s*\(|annotate_value\s*\(|"
                                 r"add_units_note\s*\(|cbar_label\s*=", window):
                    continue
                for ch in text:
                    # 只查非 ASCII、非 LaTeX 数学区、非空白的可见字符
                    if ord(ch) < 0x80 or ch.isspace():
                        continue
                    if ord(ch) not in self.charmap:
                        missing.append("%s:%d U+%04X %r 在 %s 里没有字形"
                                       % (rel, lineno, ord(ch), ch,
                                          self.font_name))
        self.assertEqual(sorted(set(missing)), [],
                         "\n".join(["图上这些字符会画成方框："]
                                   + sorted(set(missing))))


class DoctorCnFontCheckTest(unittest.TestCase):
    """`doctor.py` 的 `cn-font` 项必须**正反两向都成立**。

    只测"有字体时通过"是不够的——那样测不出检查是不是恒真。
    自检只覆盖它真正测过的那一维：把字体列表清空，它必须 FAIL。
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        path = ROOT / "scripts" / "doctor.py"
        spec = importlib.util.spec_from_file_location("glyph_doctor", path)
        module = importlib.util.module_from_spec(spec)
        # **必须先注册进 sys.modules 再 exec**：doctor.py 里有 @dataclass，
        # dataclasses 会去 sys.modules 查模块的 __dict__，没注册就 AttributeError。
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.doctor = module

    def test_passes_when_font_available(self):
        sys.path.insert(0, str(ROOT / "figures"))
        import cumcm_style
        if cumcm_style.available_cn_font() is None:
            self.skipTest("本机没有中文字体")
        ok, detail = self.doctor._check_cn_font()
        self.assertTrue(ok, detail)
        self.assertIn("可用", detail)

    def test_fails_when_no_font(self):
        sys.path.insert(0, str(ROOT / "figures"))
        import cumcm_style
        original = cumcm_style.available_cn_font
        try:
            cumcm_style.available_cn_font = lambda: None
            ok, detail = self.doctor._check_cn_font()
        finally:
            cumcm_style.available_cn_font = original
        self.assertFalse(ok, "没有中文字体时 cn-font 必须 FAIL，否则这项检查恒真")
        self.assertIn("方框", detail)

    def test_registered_in_doctor_checks(self):
        names = {c.name for c in
                 self.doctor.run_checks(competition="cumcm", check_tools=False)}
        self.assertIn("cn-font", names)


if __name__ == "__main__":
    unittest.main()
