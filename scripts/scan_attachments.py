#!/usr/bin/env python3
"""附件结构体检：把 Stage 1/2 判题型时"该去看的东西"变成机器扫出来的事实。

为什么需要这个脚本
------------------
`题型与算法对照.md` 第一节的题型判据里，有几条依赖**附件的结构性事实**：
「各分量之和为常数 → 成分数据类（方法全变）」「同一对象多条记录 → 观测不独立」。
这些事实都写在文档里，但**没人保证真去看**——而看漏的代价是整条方法主线错。

2021B 实测：附件 1 的六个"选择性"列之和**恒等于 100.0000**（114 行无一例外），
是成分数据；同时"催化剂组合编号"列因为 Excel 合并单元格，每 5 行才有一个值、
其余是 NaN——直接 groupby 会把 114 行切成 21 组以外的错误分组。
这两件事读题面都看不出来，读一眼数据也未必看得出来，但扫一遍就都在。

扫什么
------
1. **成分结构**：哪几列的和恒为常数（100 / 1 / 其它）。命中就要上 CLR，
   Pearson 相关在成分数据上有偏负倾向、结论是假的。
2. **合并单元格残留**：某列大段 NaN 且非空值稀疏且规则 → 多半是合并单元格，
   需要 ffill 才能当分组键。
3. **重复测量**：候选 ID 列有重复值 → 同一对象多条记录，观测不独立，
   不能当独立样本做回归。
4. **比例型列**：取值落在 [0,1] 或 [0,100] 且列名含 率/比/占/selectivity 等。
5. 缺失率、常数列、疑似日期列。

用法
----
    python scripts/scan_attachments.py <附件目录或文件> [...]
    python scripts/scan_attachments.py 附件1.xlsx --json

退出码：0 = 扫完（**有发现也是 0**，这是体检不是门）；2 = 没跑成。
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

RATIO_HINTS = ("率", "比", "占", "百分", "选择性", "share", "ratio", "pct",
               "percent", "proportion", "selectivity")
ID_HINTS = ("编号", "id", "序号", "代码", "名称", "样本", "孕妇", "个体", "编码")
CONST_TARGETS = (100.0, 1.0)
SUM_TOL = 1e-6          # 判"和恒为常数"的相对容差


def _load(path: Path) -> dict[str, "pd.DataFrame"]:
    import pandas as pd

    if path.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
        book = pd.ExcelFile(path)
        return {name: book.parse(name) for name in book.sheet_names}
    if path.suffix.lower() in (".csv", ".txt"):
        for enc in ("utf-8", "gbk", "utf-8-sig"):
            try:
                return {path.stem: pd.read_csv(path, encoding=enc)}
            except UnicodeDecodeError:
                continue
        return {path.stem: pd.read_csv(path, encoding="utf-8", errors="replace")}
    return {}


def find_compositional(df) -> list[dict]:
    """找出"和恒为常数"的列组。

    先试全部数值列，不成再试列名带比例线索的子集，最后试贪心去掉离群列。
    不做全组合枚举——列数一多就爆炸，而真实的成分组几乎总是"名字像的那一批"。
    """
    import numpy as np
    import pandas as pd

    num = df.select_dtypes("number")
    num = num.loc[:, num.notna().sum() > 0]
    if num.shape[1] < 2 or len(num) == 0:
        return []

    def check(cols) -> dict | None:
        sub = num[list(cols)].dropna()
        if len(sub) < 3 or sub.shape[1] < 2:
            return None
        s = sub.sum(axis=1)
        if s.abs().max() == 0:
            return None
        spread = float(s.max() - s.min())
        scale = float(abs(s.mean())) or 1.0
        if spread / scale > SUM_TOL:
            return None
        const = float(s.mean())
        return {"columns": list(cols), "constant_sum": round(const, 6),
                "rows_checked": int(len(sub)),
                "matches_100_or_1": any(abs(const - t) < 1e-3 for t in CONST_TARGETS)}

    def check_approx(cols) -> dict | None:
        """近似成分：和不恒定但集中在 100 或 1 附近。

        真实的成分数据几乎都是这个形态——2022C 的化学成分和是 71.89~100，
        题面自己写着"累加和介于 85%~105% 之间的数据为有效数据"。
        只认严格恒定会把**最典型的成分数据题**漏掉（实测 2022C 报 0 处发现）。
        """
        sub = num[list(cols)]
        if sub.shape[1] < 3:
            return None
        s = sub.fillna(0).sum(axis=1)
        s = s[s > 0]
        if len(s) < 5:
            return None
        med = float(s.median())
        target = min(CONST_TARGETS, key=lambda t: abs(med - t))
        if abs(med - target) / target > 0.10:
            return None
        within = float((abs(s - target) / target <= 0.15).mean())
        if within < 0.6:
            return None
        return {"columns": list(cols), "median_sum": round(med, 4),
                "target": target, "within_15pct": round(within, 3),
                "range": [round(float(s.min()), 3), round(float(s.max()), 3)],
                "rows_checked": int(len(s))}

    hit = check(num.columns)
    if hit:
        return [hit]

    ratio_cols = [c for c in num.columns
                  if any(h in str(c).lower() for h in RATIO_HINTS)]
    if len(ratio_cols) >= 2:
        hit = check(ratio_cols)
        if hit:
            return [hit]
        # 贪心：逐个去掉"最不合群"的列，最多去掉一半
        cols = list(ratio_cols)
        for _ in range(len(ratio_cols) // 2):
            sub = num[cols].dropna()
            if len(sub) < 3 or len(cols) < 3:
                break
            target = sub.sum(axis=1).mean()
            # 去掉哪一列后，和的离散度下降最多
            best, best_spread = None, None
            for c in cols:
                rest = [x for x in cols if x != c]
                s = num[rest].dropna().sum(axis=1)
                if len(s) < 3:
                    continue
                sp = float(s.max() - s.min())
                if best_spread is None or sp < best_spread:
                    best, best_spread = c, sp
            if best is None:
                break
            cols = [x for x in cols if x != best]
            hit = check(cols)
            if hit:
                hit["note"] = "去掉 %s 后成立" % best
                return [hit]

    # 严格判据不成立时，再看近似成分。先试列名像成分的那批，再试全部数值列。
    for cand in ([c for c in num.columns
                  if any(h in str(c).lower() for h in RATIO_HINTS)],
                 list(num.columns)):
        if len(cand) < 3:
            continue
        approx = check_approx(cand)
        if approx:
            approx["approx"] = True
            return [approx]
    return []


def scan_frame(name: str, df) -> dict:
    import numpy as np
    import pandas as pd

    out: dict = {"sheet": name, "shape": list(df.shape),
                 "columns": [str(c) for c in df.columns], "findings": []}
    if len(df) == 0:
        out["findings"].append({"kind": "empty", "msg": "空表"})
        return out

    for comp in find_compositional(df):
        if comp.get("approx"):
            out["findings"].append({
                "kind": "compositional_approx",
                "msg": "这 %d 列之和集中在 %g 附近（中位 %.3f，%.0f%% 的行落在 ±15%% 内，"
                       "实际范围 %s，查了 %d 行）：%s"
                       % (len(comp["columns"]), comp["target"], comp["median_sum"],
                          comp["within_15pct"] * 100, comp["range"],
                          comp["rows_checked"], comp["columns"]),
                "action": "**近似成分数据**。和不恒定通常是测量误差 + 无效样本——"
                          "题面多半给了有效性区间（如 2022C 的『累加和介于 85%~105%』）。"
                          "先按题面阈值筛有效数据、再归一化到定和、再 CLR，然后才做统计。"
                          "题型要加 compositional 修饰。",
                "columns": comp["columns"]})
            continue
        out["findings"].append({
            "kind": "compositional",
            "msg": "这 %d 列之和恒为 %.4f（查了 %d 行）：%s%s"
                   % (len(comp["columns"]), comp["constant_sum"],
                      comp["rows_checked"], comp["columns"],
                      "；" + comp["note"] if comp.get("note") else ""),
            "action": "**成分数据**。必须先归一化 + 中心对数比变换(CLR) 再做统计；"
                      "直接算 Pearson 相关有偏负倾向，结论是假的。"
                      "题型要加 compositional 修饰（即使主线不是成分数据类）。",
            "columns": comp["columns"]})

    for col in df.columns:
        s = df[col]
        na = float(s.isna().mean())
        # 合并单元格残留：大段 NaN，且非空值成"块首"分布。
        # **不要求间隔严格相等**——2021B 的编号列 A 组每 5 行一个、B 组不同，
        # 一旦要求等间隔就漏报，而漏报的代价是 groupby 只剩 21 行（每组 1 行）。
        if 0.4 < na < 1.0:
            idx = np.flatnonzero(s.notna().to_numpy())
            if len(idx) >= 3:
                gaps = np.diff(idx)
                uniform = len(set(gaps.tolist())) == 1
                # 首个非空在表头附近 + 相邻非空间隔普遍 >1 → 像块首标记
                if idx[0] <= 1 and float((gaps > 1).mean()) > 0.8:
                    out["findings"].append({
                        "kind": "merged_cells",
                        "msg": "列 %r 缺失 %.0f%%，%d 个非空值呈块首分布（间隔 %s）"
                               % (str(col), na * 100, len(idx),
                                  "恒为 %d" % gaps[0] if uniform
                                  else "%d~%d 不等" % (gaps.min(), gaps.max())),
                        "action": "多半是 Excel 合并单元格。当分组键前必须 "
                                  "`df[col] = df[col].ffill()`——不 ffill 直接 groupby，"
                                  "每组只会剩 1 行，而且不报错。",
                        "columns": [str(col)]})
        if na == 1.0:
            out["findings"].append({"kind": "all_nan",
                                    "msg": "列 %r 全为空" % str(col),
                                    "action": "确认是否读错表头行。",
                                    "columns": [str(col)]})
        elif s.nunique(dropna=True) == 1:
            looks_label = any(h in str(col) for h in
                              ("是否", "健康", "标签", "类别", "分类", "异常",
                               "label", "class", "target", "y"))
            act = "常数列，通常不该进模型。"
            if looks_label:
                # 2025C 实测：女胎表『胎儿是否健康』605 行全是"是"，
                # 真标签在『染色体的非整倍体』列（538 空=正常，67 有值=异常）。
                # 拿前者当标签会得到零正例的退化模型，**而且不报错**。
                sparse = [str(c) for c in df.columns
                          if c != col and 0.5 < df[c].isna().mean() < 1.0
                          and df[c].nunique(dropna=True) <= 12]
                act = ("这列名字像标签却只有一个取值——**真标签多半在别处**。"
                       "拿它做监督学习会得到零正例的退化模型，而且不报错。")
                if sparse:
                    act += "本表里这些稀疏分类列更像真标签：%s" % sparse[:5]
            out["findings"].append({"kind": "constant",
                                    "msg": "列 %r 只有一个取值 %r"
                                           % (str(col), s.dropna().iloc[0]),
                                    "action": act,
                                    "columns": [str(col)]})

    # 重复测量：候选 ID 列有重复
    for col in df.columns:
        if not any(h in str(col).lower() for h in ID_HINTS):
            continue
        s = df[col].ffill() if df[col].isna().mean() > 0.3 else df[col]
        s = s.dropna()
        if len(s) == 0:
            continue
        # 光靠列名会误伤：2025C 的『孕妇BMI』含"孕妇"却是连续测量值，不是 ID。
        # 真 ID 会被大量重复（267 个孕妇 / 1082 行 → 0.25），
        # 连续变量的不同取值占比高（783/1082 → 0.72）。以 0.5 为界。
        if s.nunique() / len(s) > 0.5:
            continue
        dup = len(s) - s.nunique()
        if dup > 0:
            out["findings"].append({
                "kind": "repeated_measures",
                "msg": "列 %r 有重复值：%d 行 / %d 个不同取值"
                       % (str(col), len(s), s.nunique()),
                "action": "**同一对象多条记录 → 观测不独立**。回归要用混合效应模型"
                          "或 GEE，不能当独立样本；报 R² 要说清是边际还是条件。",
                "columns": [str(col)]})

    return out


def main(argv: list[str] | None = None) -> int:
    _console.init()
    ap = argparse.ArgumentParser(description="附件结构体检（Stage 1/2 判题型用）")
    ap.add_argument("paths", nargs="+", help="附件文件或目录")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        import pandas  # noqa: F401
    except ImportError:
        print("需要 pandas：python -m pip install pandas openpyxl", file=sys.stderr)
        return 2

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            for suf in ("*.xlsx", "*.xls", "*.xlsm", "*.csv"):
                files.extend(sorted(p.rglob(suf)))
        elif p.is_file():
            files.append(p)
        else:
            print("找不到 %s" % raw, file=sys.stderr)
            return 2
    if not files:
        print("没有可扫描的附件", file=sys.stderr)
        return 2

    report = []
    for f in files:
        try:
            frames = _load(f)
        except Exception as exc:                      # noqa: BLE001
            report.append({"file": str(f), "error": str(exc)})
            continue
        for name, df in frames.items():
            report.append({"file": f.name, **scan_frame(name, df)})

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    n_find = 0
    for r in report:
        if "error" in r:
            print(_console.sym("✗ %s 读不了：%s" % (r["file"], r["error"])))
            continue
        print(_console.sym("\n=== %s / %s  %d 行 × %d 列 ==="
                           % (r["file"], r["sheet"], *r["shape"])))
        if not r["findings"]:
            print("  未发现结构性特征。")
            continue
        for it in r["findings"]:
            n_find += 1
            print(_console.sym("  ⚠ [%s] %s" % (it["kind"], it["msg"])))
            if it.get("action"):
                print("      → " + it["action"])
    print("\n共 %d 处结构性发现。这是体检不是门——但 compositional 与 "
          "repeated_measures 两类会改变方法主线，必须在 Stage 1/2 处理。" % n_find)
    return 0


if __name__ == "__main__":
    sys.exit(main())
