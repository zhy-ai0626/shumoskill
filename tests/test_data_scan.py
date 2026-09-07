#!/usr/bin/env python3
"""`scan_attachments.py` 里静默陷阱 §四那四条检查的回归测试，以及图表 helper 的守卫。

为什么要有这个文件
------------------
`静默陷阱.md` 末节自己写着「自检清单要先枚举维度，再写判据」——十项自检全过
仍漏掉符号错，因为「$y$ 分量」那一格从来没被测过。这四条检查也一样：
每条都要有**命中**和**不该命中**两个方向的测试，否则「测试全过」只说明
它在被测过的方向上对。

所以下面每个检查都成对写：
- `test_*_fires`      构造出该命中的数据，确认报出来了
- `test_*_quiet`      构造出**形态相似但没问题**的数据，确认不误报

误报方向尤其要盯：这是体检脚本，一旦刷屏，人就不看了——
**输出太长和没有输出，在实际使用上是同一个结果**。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"mathmodel_test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scan = load_script("scan_attachments")


def kinds(findings: list[dict]) -> set[str]:
    return {f["kind"] for f in findings}


class MixedDtypeTest(unittest.TestCase):
    def test_fires_on_int_plus_string(self):
        df = pd.DataFrame({"量": [1, 2, "缺测", 4, 5, 6]})
        found = scan.find_mixed_dtype(df)
        self.assertIn("mixed_dtype", kinds(found))
        self.assertIn("量", found[0]["msg"])

    def test_fires_on_excel_int_date_plus_datetime(self):
        """2025C 的「检测日期」：686 行是整数 20230429、396 行是真 datetime。"""
        df = pd.DataFrame({"检测日期": [20230429, 20230531,
                                        pd.Timestamp("2023-07-01"),
                                        pd.Timestamp("2023-07-02"), 20230803]})
        self.assertIn("mixed_dtype", kinds(scan.find_mixed_dtype(df)))

    def test_fires_on_week_compound_notation(self):
        df = pd.DataFrame({"检测孕周": ["11w+6", "15w+6", "20w+1", "13w", "16W+1"]})
        found = scan.find_mixed_dtype(df)
        self.assertIn("mixed_dtype", kinds(found))
        self.assertIn("11w+6", found[0]["msg"])

    def test_quiet_on_homogeneous_columns(self):
        df = pd.DataFrame({"数": [1.0, 2.0, 3.0, 4.0],
                           "文本": ["甲", "乙", "丙", "丁"],
                           "日期": pd.to_datetime(["2024-01-01", "2024-01-02",
                                                   "2024-01-03", "2024-01-04"])})
        self.assertEqual(scan.find_mixed_dtype(df), [])

    def test_collapses_when_many_columns_hit(self):
        """25 列同时命中要折叠成一条，不能逐条刷屏（2021 的填写模板就是这形态）。"""
        data = {f"c{i}": [1, 2, "注", 4, 5, 6, 7] for i in range(25)}
        found = scan.find_mixed_dtype(pd.DataFrame(data))
        self.assertEqual(len(found), 1)
        self.assertIn("25 列命中", found[0]["msg"])
        self.assertEqual(len(found[0]["columns"]), 25)


class EdgeRowTest(unittest.TestCase):
    def test_buried_header_reported_once(self):
        """真表头埋在第 3 行，前面是说明文字 —— 报一条，不是报 4 条。"""
        df = pd.DataFrame({
            "注意：": ["1.请勿修改", "2.只填蓝色区", "供应商编号", 1, 2, 3, 4],
            "Unnamed: 1": [None, None, "订货量", 10, 20, 30, 40],
            "Unnamed: 2": [None, None, "单价", 1.5, 2.5, 3.5, 4.5],
            "Unnamed: 3": [None, None, "损耗率", 0.1, 0.2, 0.3, 0.4],
        })
        found = scan.find_mixed_dtype(df)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], "edge_row_text")
        self.assertIn("表格头部", found[0]["msg"])

    def test_footnote_row_reported_once(self):
        df = pd.DataFrame({
            "a": [1, 2, 3, 4, 5, "注：数据来源统计局"],
            "b": [1.0, 2.0, 3.0, 4.0, 5.0, "合计"],
            "c": [7, 8, 9, 10, 11, "—"],
        })
        found = scan.find_mixed_dtype(df)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], "edge_row_text")
        self.assertIn("末 1~2 行", found[0]["msg"])

    def test_quiet_when_text_spread_through_table(self):
        """文本散落在中间，不是边缘行形态 —— 该走逐列 mixed_dtype，不该报 edge_row。"""
        df = pd.DataFrame({"a": [1, "x", 3, "y", 5, 6, "z", 8]})
        self.assertNotIn("edge_row_text", kinds(scan.find_mixed_dtype(df)))


class CaseCollisionTest(unittest.TestCase):
    def test_fires_on_case_difference(self):
        """2025C 实测：孕周列里混了一个大写的 `16W+1`。"""
        df = pd.DataFrame({"孕周": ["16w+1", "16W+1", "17w+2", "18w+3"]})
        found = scan.find_case_collision(df)
        self.assertIn("case_collision", kinds(found))
        self.assertIn("大小写", found[0]["msg"])

    def test_fires_on_trailing_space(self):
        """2024C 实测：作物名称里有一个 `'生菜 '` 带尾随空格。"""
        df = pd.DataFrame({"作物名称": ["生菜", "生菜 ", "白菜", "萝卜"]})
        found = scan.find_case_collision(df)
        self.assertIn("case_collision", kinds(found))
        self.assertIn("首尾空白", found[0]["msg"])
        self.assertIn("生菜", found[0]["msg"])

    def test_fires_on_fullwidth_digits(self):
        df = pd.DataFrame({"编号": ["A1", "Ａ１", "A2", "A3"]})
        found = scan.find_case_collision(df)
        self.assertIn("case_collision", kinds(found))
        self.assertIn("全角", found[0]["msg"])

    def test_quiet_on_clean_categories(self):
        df = pd.DataFrame({"类别": ["甲", "乙", "丙", "丁", "戊"]})
        self.assertEqual(scan.find_case_collision(df), [])

    def test_quiet_on_numeric_column(self):
        df = pd.DataFrame({"x": [1, 2, 3, 4]})
        self.assertEqual(scan.find_case_collision(df), [])


class TimestampCoercionTest(unittest.TestCase):
    """`_to_timestamp` 是 derived_mismatch 能不能跑起来的前提。

    整列 `pd.to_datetime` 对整数 20230429 会按"距 epoch 多少纳秒"解释，
    结果落在 1970 年——**不报错**。这几条就是盯住这个。
    """

    def test_yyyymmdd_int(self):
        self.assertEqual(scan._to_timestamp(20230429), pd.Timestamp("2023-04-29"))

    def test_excel_serial(self):
        self.assertEqual(scan._to_timestamp(45000), pd.Timestamp("2023-03-15"))

    def test_iso_string_and_datetime(self):
        self.assertEqual(scan._to_timestamp("2022-12-19"),
                         pd.Timestamp("2022-12-19"))
        self.assertEqual(scan._to_timestamp(pd.Timestamp("2020-01-01")),
                         pd.Timestamp("2020-01-01"))

    def test_junk_becomes_nat(self):
        for bad in ("不详", None, float("nan"), 3.7, 12):
            self.assertTrue(pd.isna(scan._to_timestamp(bad)), bad)

    def test_does_not_read_yyyymmdd_as_epoch_nanoseconds(self):
        self.assertEqual(scan._to_timestamp(20230429).year, 2023)


class DerivedMismatchTest(unittest.TestCase):
    @staticmethod
    def _frame(offset_days: np.ndarray) -> pd.DataFrame:
        n = len(offset_days)
        lmp = pd.to_datetime("2023-01-01") + pd.to_timedelta(
            np.arange(n) % 30, unit="D")
        # 自报孕周基于真实差值；offset_days 是"自报与派生的偏差"
        test_date = lmp + pd.to_timedelta(np.arange(n) % 40 + 80, unit="D")
        derived_weeks = (test_date - lmp).days / 7.0
        stated = derived_weeks + offset_days / 7.0
        return pd.DataFrame({
            "末次月经": lmp,
            "检测日期": test_date,
            "检测孕周": stated,
        })

    def test_fires_when_columns_disagree(self):
        rng = np.random.default_rng(7)
        df = self._frame(rng.normal(0, 4.0, 200))          # 偏差约 ±4 天
        found = scan.find_derived_mismatch(df)
        self.assertIn("derived_mismatch", kinds(found))
        self.assertIn("检测孕周", found[0]["msg"])

    def test_quiet_when_columns_agree(self):
        df = self._frame(np.zeros(200))                    # 完全自洽
        self.assertEqual(scan.find_derived_mismatch(df), [])

    def test_quiet_when_unrelated(self):
        """一个和日期差无关的数值列，不该被当成派生量。"""
        rng = np.random.default_rng(11)
        df = self._frame(np.zeros(120))
        df["检测孕周"] = rng.normal(20, 5, 120)             # 换成纯噪声
        self.assertEqual(scan.find_derived_mismatch(df), [])

    def test_works_on_mixed_type_date_columns(self):
        """**这条是关键**：日期列是混合类型时 dtype 是 object，
        只认 datetime64 会让这项检查静默不跑——两个坑互相遮蔽。"""
        rng = np.random.default_rng(3)
        df = self._frame(rng.normal(0, 4.0, 150))
        # 把一半的日期退化成 Excel 整数写法、末次月经退化成字符串
        df["检测日期"] = [int(d.strftime("%Y%m%d")) if i % 2 else d
                          for i, d in enumerate(df["检测日期"])]
        df["末次月经"] = [d.strftime("%Y-%m-%d") if i % 3 else d
                          for i, d in enumerate(df["末次月经"])]
        self.assertEqual(df["检测日期"].dtype, object)      # 前提成立
        self.assertIn("derived_mismatch",
                      kinds(scan.find_derived_mismatch(df)))

    def test_parses_week_compound_notation(self):
        rng = np.random.default_rng(5)
        df = self._frame(rng.normal(0, 4.0, 150))
        df["检测孕周"] = ["%dw+%d" % (int(v), round((v % 1) * 7))
                          for v in df["检测孕周"]]
        self.assertIn("derived_mismatch",
                      kinds(scan.find_derived_mismatch(df)))


class IdentityCollinearTest(unittest.TestCase):
    def test_fires_on_bmi_identity(self):
        """BMI ≡ 体重/身高²。静默陷阱 §四实测 VIF 到 10⁴ 量级。"""
        rng = np.random.default_rng(1)
        n = 300
        h = rng.normal(1.62, 0.06, n)
        w = rng.normal(70, 10, n)
        df = pd.DataFrame({"身高": h, "体重": w, "BMI": w / h ** 2,
                           "年龄": rng.integers(22, 45, n)})
        found = scan.find_identity_collinear(df)
        self.assertIn("identity_collinear", kinds(found))
        hit = " ".join(found[0]["columns"])
        self.assertTrue(any(c in hit for c in ("BMI", "体重", "身高")), hit)

    def test_quiet_on_independent_columns(self):
        rng = np.random.default_rng(2)
        df = pd.DataFrame(rng.normal(size=(300, 5)),
                          columns=[f"x{i}" for i in range(5)])
        self.assertEqual(scan.find_identity_collinear(df), [])

    def test_skips_wide_matrices(self):
        """2021「近5年402家供应商」是 242 列的企业×月份矩阵：
        列本身就是同一个量的不同时点，高相关是形态而不是恒等式。"""
        rng = np.random.default_rng(4)
        base = rng.normal(size=(80, 1))
        wide = pd.DataFrame(base + rng.normal(0, 0.01, size=(80, 60)),
                            columns=[f"W{i:03d}" for i in range(60)])
        self.assertEqual(scan.find_identity_collinear(wide), [])

    def test_excludes_compositional_columns(self):
        """定和约束本身会让 VIF 爆到 1e15，那是 compositional 的第二种表现，
        再报一遍只会稀释信号（2021B 六列选择性之和恒为 100）。"""
        rng = np.random.default_rng(6)
        n = 200
        raw = rng.random((n, 4))
        comp = pd.DataFrame(raw / raw.sum(axis=1, keepdims=True) * 100.0,
                            columns=["s1", "s2", "s3", "s4"])
        comp["温度"] = rng.normal(300, 20, n)
        self.assertIn("identity_collinear",
                      kinds(scan.find_identity_collinear(comp)))
        self.assertEqual(
            scan.find_identity_collinear(
                comp, exclude={"s1", "s2", "s3", "s4"}), [])

    def test_ignores_unnamed_columns(self):
        rng = np.random.default_rng(8)
        n = 200
        x = rng.normal(size=n)
        df = pd.DataFrame({"Unnamed: 1": x, "Unnamed: 2": x * 2 + 1e-9,
                           "Unnamed: 3": rng.normal(size=n)})
        self.assertEqual(scan.find_identity_collinear(df), [])

    def test_log_space_catches_multiplicative_identity(self):
        """乘除关系在原始空间可能不炸，取对数后是精确线性。"""
        rng = np.random.default_rng(9)
        n = 400
        a = np.exp(rng.normal(0, 1.0, n))
        b = np.exp(rng.normal(0, 1.0, n))
        df = pd.DataFrame({"a": a, "b": b, "积": a * b,
                           "无关": np.exp(rng.normal(0, 1.0, n))})
        found = scan.find_identity_collinear(df)
        self.assertIn("identity_collinear", kinds(found))


class CheckErrorSurfacingTest(unittest.TestCase):
    """体检项自己崩掉时必须报出来。

    静默跳过一项检查，和这项检查通过，在输出上长得一模一样——
    这正是 `静默陷阱.md` 那条「自检只覆盖它真正测过的那一维」的机制。
    """

    def test_broken_finder_reports_check_error(self):
        original = scan.find_case_collision
        try:
            def boom(_df):
                raise RuntimeError("故意炸")
            scan.find_case_collision = boom
            out = scan.scan_frame("t", pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0]}))
        finally:
            scan.find_case_collision = original
        errs = [f for f in out["findings"] if f["kind"] == "check_error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("find_case_collision", errs[0]["msg"])
        self.assertIn("故意炸", errs[0]["msg"])


class ScanFrameIntegrationTest(unittest.TestCase):
    def test_all_four_checks_reachable_from_scan_frame(self):
        rng = np.random.default_rng(13)
        n = 150
        h = rng.normal(1.62, 0.06, n)
        w = rng.normal(70, 10, n)
        lmp = pd.to_datetime("2023-01-01") + pd.to_timedelta(
            np.arange(n) % 30, unit="D")
        test_date = lmp + pd.to_timedelta(np.arange(n) % 40 + 80, unit="D")
        stated = (test_date - lmp).days / 7.0 + rng.normal(0, 0.6, n)
        df = pd.DataFrame({
            "身高": h, "体重": w, "BMI": w / h ** 2,
            "末次月经": lmp, "检测日期": test_date, "检测孕周": stated,
            "分组": ["A" if i else "a" for i in rng.integers(0, 2, n)],
            "混合": [i if i % 5 else "缺测" for i in range(n)],
        })
        got = kinds(scan.scan_frame("sheet", df)["findings"])
        for want in ("identity_collinear", "derived_mismatch",
                     "case_collision", "mixed_dtype"):
            self.assertIn(want, got)

    def test_exit_code_is_zero_even_with_findings(self):
        """这是体检不是门。有发现也必须退 0，否则会被当成流程失败。"""
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "附件.csv"
            pd.DataFrame({"名称": ["甲", "甲 ", "乙"],
                          "值": [1, 2, 3]}).to_csv(p, index=False,
                                                   encoding="utf-8-sig")
            import contextlib
            import io as _io
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = scan.main([str(p), "--json"])
            self.assertEqual(rc, 0)
            report = json.loads(buf.getvalue())
            self.assertIn("case_collision",
                          {f["kind"] for r in report
                           for f in r.get("findings", [])})


if __name__ == "__main__":
    unittest.main()
