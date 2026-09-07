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

再加 `静默陷阱.md` §四那四条——它们的共同点是**不抛异常，只出错数**：

6. **混合类型列**：同一列一半 `int`、一半被 Excel 读成 `datetime` 或字符串。
   `int()` 抛异常还算好的，更坏的是 `pd.to_numeric(errors="coerce")`
   把编不出的那些**静默变成 NaN**，行数不变、分布悄悄改了。
7. **规范化后取值数变少**：大小写（孕周里混一个大写 `16W+1`）、首尾空白、
   全角数字。正则不加 `re.I` 就静默丢一条，`groupby` 会把同一类切成两组。
8. **派生量与自报量对不上**：2025C 的孕周列与"检测日期 − 末次月经"
   只有 38.4% 吻合到 0.15 周内。选哪一列当准要在论文里写理由。
9. **恒等式关系的变量同时入模**：BMI ≡ 体重/身高²，VIF 到 10⁴ 量级，
   回归系数不可解释。乘除关系取对数后是精确线性，所以 log 空间的 VIF 更灵。

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
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

RATIO_HINTS = ("率", "比", "占", "百分", "选择性", "share", "ratio", "pct",
               "percent", "proportion", "selectivity")
ID_HINTS = ("编号", "id", "序号", "代码", "名称", "样本", "孕妇", "个体", "编码")
CONST_TARGETS = (100.0, 1.0)
SUM_TOL = 1e-6          # 判"和恒为常数"的相对容差

# 列名像"时长"的量 → (换算成天的系数, 判吻合的容差)。
# 容差按该单位的实际精度给：孕周报到 0.1 周，所以 0.15；天报整数，所以 1。
# 2025C 用的就是 0.15 周这个口径（实测只有 38.4% 的行吻合）。
DURATION_UNITS = (
    ("孕周", 7.0, 0.15), ("周", 7.0, 0.15), ("week", 7.0, 0.15),
    ("年龄", 365.25, 0.5), ("龄", 365.25, 0.5), ("age", 365.25, 0.5),
    ("月", 30.4375, 0.5), ("month", 30.4375, 0.5),
    ("年", 365.25, 0.1), ("year", 365.25, 0.1),
    ("天数", 1.0, 1.0), ("天", 1.0, 1.0), ("日数", 1.0, 1.0),
    ("day", 1.0, 1.0), ("时长", 1.0, 1.0), ("间隔", 1.0, 1.0),
)
# 这些名字是时间点而不是时长，别当派生量的目标。
# "检测日期"含"日"，不排掉会被 DURATION_UNITS 误判。
TIMEPOINT_HINTS = ("日期", "时间", "date", "time", "datetime", "末次", "时刻")
VIF_ALERT = 100.0       # 1/(1-R²) > 100 等价于 R² > 0.99
MAX_VIF_COLS = 25       # 列太多时逐列最小二乘会变慢，且报出来也读不完


def _norm_steps(text: str) -> list[tuple[str, str]]:
    """依次施加三种规范化，返回 [(这一步的名字, 结果)]，用来归因是哪一步造成的合并。"""
    stripped = text.strip()
    return [("首尾空白", stripped),
            ("大小写", stripped.upper()),
            ("全角/兼容字符", unicodedata.normalize("NFKC", stripped.upper()))]


def _coarse_type(v) -> str:
    """把值归到粗类型。**不能直接用 type()**——numpy 的 int64 和 python 的 int
    是两个类，同一列混着出现是常态，报出来全是噪声。"""
    import numpy as np
    import pandas as pd

    if isinstance(v, bool) or isinstance(v, np.bool_):
        return "bool"
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "year") and hasattr(v, "month"):
        return "datetime"
    if isinstance(v, (int, float, np.integer, np.floating)):
        return "number"
    if isinstance(v, str):
        return "string"
    return type(v).__name__


_NUM_RE = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")
# 2025C 的孕周写成 "11w+6"（11 周 6 天），还混着大写 W。这类"带单位的复合写法"
# 既不是数也不是纯文本，to_numeric 会把整列变 NaN。
_WEEK_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[wW周]\s*(?:\+\s*(\d+(?:\.\d+)?))?\s*$")


def _parse_week(text: str) -> float | None:
    m = _WEEK_RE.match(str(text))
    if not m:
        return None
    return float(m.group(1)) + (float(m.group(2)) / 7.0 if m.group(2) else 0.0)


HEAD_BAND = 6           # "表头埋在前几行"里的"几"
EDGE_MIN_COLS = 3       # 至少这么多列同现，才认为是整表的形态而不是单列的事
MAX_SAME_KIND = 5       # 同一类发现最多逐条列这么多，超了折叠成一条


def _edge_row_pattern(df) -> dict | None:
    """多列同时"文本只出现在表格头部/尾部" → 表头埋行 或 末行注释。

    实测这是 2021 与 2024 附件里最常见的形态。2021「附件A 订购方案数据结果」
    是个填写模板：前 4 行是"注意：请不要修改表格中已有的任何信息"之类的说明，
    真表头在第 5 行——25 列全部命中 mixed_dtype，把真正的发现整页顶下去。
    所以**归成一条**，并说清该怎么读这个文件。
    """
    n = len(df)
    if n < 4:
        return None
    head_cols, tail_cols = [], []
    for col in df.columns:
        s = df[col]
        if s.dtype.kind in "ifcb" or str(s.dtype).startswith("datetime"):
            continue
        arr = s.to_numpy()
        str_pos = [i for i, v in enumerate(arr) if isinstance(v, str)]
        num_pos = [i for i, v in enumerate(arr) if _coarse_type(v) == "number"]
        if not str_pos or not num_pos:
            continue
        # 文本全在前 HEAD_BAND 行、且数值都在文本之后 → 表头埋行
        if max(str_pos) < min(HEAD_BAND, n - 1) and min(num_pos) > max(str_pos):
            head_cols.append(str(col))
        elif min(str_pos) >= n - 2:
            tail_cols.append(str(col))
    for cols, where, action in (
            (head_cols, "表格头部（前 %d 行内）" % HEAD_BAND,
             "**真表头很可能埋在前几行的某一行**，前面几行是说明文字，"
             "pandas 把它们当成了列名（于是出现一堆 `Unnamed: N`）。"
             "先 `pd.read_excel(..., header=None).head(10)` 看清哪一行是表头，"
             "再用 `header=<行号>` 重读。照当前读法直接建模，"
             "说明文字会被 `to_numeric` 静默变成 NaN，而且列名全错。"),
            (tail_cols, "末 1~2 行",
             "**多半是末行注释/合计行**（如「注：...」「合计」）。"
             "它会被当成一条数据参与统计——行数对不上、均值被拉偏，都不报错。"
             "读的时候 `skipfooter=` 掉，或读完显式 drop 并记下行号。")):
        if len(cols) >= EDGE_MIN_COLS:
            return {"kind": "edge_row_text",
                    "msg": "%d 列的文本值集中在%s：%s%s"
                           % (len(cols), where, cols[:8],
                              " 等" if len(cols) > 8 else ""),
                    "action": action, "columns": cols}
    return None


def _collapse(findings: list[dict], kind: str) -> list[dict]:
    """同一类发现太多就折叠成一条。

    兜底，不是主逻辑。逐条列 25 条一模一样的发现，等于把真正要看的东西
    埋掉——**输出太长和没有输出，在实际使用上是同一个结果**。
    """
    same = [f for f in findings if f["kind"] == kind]
    if len(same) <= MAX_SAME_KIND:
        return findings
    rest = [f for f in findings if f["kind"] != kind]
    cols = [c for f in same for c in f["columns"]]
    return rest + [{
        "kind": kind,
        "msg": "%d 列命中 %s（只列前 %d 个：%s）"
               % (len(same), kind, MAX_SAME_KIND, cols[:MAX_SAME_KIND]),
        "action": "这么多列同时命中，通常是**整表的读法有问题**"
                  "（表头行、合并单元格、多级表头），而不是各列各有各的毛病。"
                  "先把表读对，再重扫。逐列详情用 --json 看。",
        "columns": cols}]


def find_mixed_dtype(df) -> list[dict]:
    """混合类型列，以及"大部分能转成数、少数不能"的列。"""
    edge = _edge_row_pattern(df)
    if edge is not None:
        return [edge]                                  # 归成一条，不逐列刷

    out: list[dict] = []
    for col in df.columns:
        s = df[col]
        if s.dtype.kind in "ifcb" or str(s.dtype).startswith("datetime"):
            continue                                   # 已经是同质列
        vals = s.dropna()
        if len(vals) == 0:
            continue
        kinds: dict[str, int] = {}
        for v in vals:
            kinds[_coarse_type(v)] = kinds.get(_coarse_type(v), 0) + 1
        if len(kinds) > 1:
            out.append({
                "kind": "mixed_dtype",
                "msg": "列 %r 混了 %d 种类型：%s"
                       % (str(col), len(kinds),
                          "、".join("%s×%d" % kv for kv in
                                    sorted(kinds.items(), key=lambda kv: -kv[1]))),
                "action": "**别用 `pd.to_numeric(errors=\"coerce\")` 一把梭**——"
                          "它会把转不了的那些静默变成 NaN，行数不变、分布悄悄改了。"
                          "先 `df[c].map(type).value_counts()` 看清是什么混进来的，"
                          "再分支处理，并在数据口径里写明各分支的行数。",
                "columns": [str(col)]})
            continue
        if kinds.get("string"):
            texts = [str(v).strip() for v in vals]
            n_num = sum(1 for t in texts if _NUM_RE.match(t))
            n_week = sum(1 for t in texts if _parse_week(t) is not None)
            if 0 < n_num < len(texts) and n_num / len(texts) >= 0.5:
                bad = [t for t in texts if not _NUM_RE.match(t)][:5]
                out.append({
                    "kind": "mixed_dtype",
                    "msg": "列 %r 是文本列，%d/%d 个值能当数读，剩下 %d 个不能（例：%s）"
                           % (str(col), n_num, len(texts), len(texts) - n_num, bad),
                    "action": "`to_numeric(errors=\"coerce\")` 会把那 %d 个静默变 NaN。"
                              "先看清它们是什么——单位后缀？复合写法？缺测标记？"
                              "每一类的处理都要写进数据口径。" % (len(texts) - n_num),
                    "columns": [str(col)]})
            elif n_week and n_week / len(texts) >= 0.5:
                out.append({
                    "kind": "mixed_dtype",
                    "msg": "列 %r 有 %d/%d 个值是 `11w+6` 这类「周+天」复合写法"
                           % (str(col), n_week, len(texts)),
                    "action": "整列直接 `to_numeric` 会全变 NaN（不报错）。"
                              "要显式解析成 周 + 天/7，并注意大小写 W/w 都要认。",
                    "columns": [str(col)]})
    return _collapse(out, "mixed_dtype")


def find_case_collision(df) -> list[dict]:
    """规范化之后取值数变少 → 同一个类别被写成了两种样子。"""
    out: list[dict] = []
    for col in df.columns:
        vals = df[col].dropna()
        if len(vals) == 0 or not all(isinstance(v, str) for v in vals):
            continue
        raw = set(vals)
        if len(raw) < 2 or len(raw) > 5000:
            continue
        # `_norm_steps` 是**累积**施加的（strip → strip+upper → +NFKC），
        # 所以逐步比上一步的取值数，就能归因是哪一种不一致造成的合并。
        prev = raw
        for idx, (name, _) in enumerate(_norm_steps("x")):
            folded = {_norm_steps(v)[idx][1] for v in raw}
            if len(folded) < len(prev):
                # 找出被合并到一起的那几组，给人看具体是哪些值
                groups: dict[str, list[str]] = {}
                for v in raw:
                    groups.setdefault(_norm_steps(v)[idx][1], []).append(v)
                merged = [sorted(g) for g in groups.values() if len(g) > 1]
                out.append({
                    "kind": "case_collision",
                    "msg": "列 %r 按「%s」规范化后取值从 %d 降到 %d，被合并的组：%s"
                           % (str(col), name, len(prev), len(folded),
                              merged[:4]),
                    "action": "同一个类别写成了两种样子。**正则要加 `re.I`，"
                              "分组前要先 `.str.strip()` / `.str.upper()` / "
                              "`unicodedata.normalize(\"NFKC\", ...)`**——"
                              "不规范化就 groupby，同一类被切成两组，而且不报错。",
                    "columns": [str(col)]})
                break
            prev = folded
    return out


def _to_timestamp(v):
    """把一个格子转成 Timestamp，转不了返回 NaT。

    **不能直接 `pd.to_datetime(series)`。** 2025C 的「检测日期」有 686 行是
    整数 `20230429`、396 行是真 datetime；「末次月经」是 674 行 datetime +
    396 行字符串。整列 dtype 因此是 object，`to_datetime` 对整数会按
    "距 epoch 多少纳秒"解释，把 20230429 变成 1970 年——**不报错**。
    """
    import numpy as np
    import pandas as pd

    if v is None:
        return pd.NaT
    if isinstance(v, pd.Timestamp):
        return v
    if isinstance(v, float) and not np.isfinite(v):
        return pd.NaT
    if hasattr(v, "year") and hasattr(v, "month"):          # datetime / date
        return pd.Timestamp(v)
    if isinstance(v, (int, np.integer)) or (
            isinstance(v, (float, np.floating)) and float(v).is_integer()):
        iv = int(v)
        if 19000101 <= iv <= 21001231:                      # yyyymmdd
            try:
                return pd.Timestamp(
                    "%04d-%02d-%02d" % (iv // 10000, iv // 100 % 100, iv % 100))
            except ValueError:
                return pd.NaT
        if 20000 <= iv <= 80000:                            # Excel 序列号
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=iv)
        return pd.NaT
    if isinstance(v, str):
        try:
            return pd.Timestamp(v)
        except (ValueError, TypeError):
            return pd.NaT
    return pd.NaT


def _date_columns(df) -> dict[str, "pd.Series"]:
    """找出能当日期用的列，返回 {列名: 已转成 datetime 的 series}。

    判据是**名字像时间点** + 至少 80% 能解析；没有名字线索时要求 98% 能解析。
    只认 `dtype == datetime64` 会漏掉最要紧的那种情况——混合类型列的 dtype
    是 object，而混合类型恰恰是本脚本要报的坑之一，两个坑会互相遮蔽。
    """
    import pandas as pd

    out: dict[str, pd.Series] = {}
    for col in df.columns:
        s = df[col]
        if str(s.dtype).startswith("datetime"):
            out[str(col)] = s
            continue
        if s.dtype.kind in "fcb":                           # 浮点/复数/布尔不是日期
            continue
        raw = s.dropna()
        if len(raw) < 5:
            continue
        ts = s.map(_to_timestamp)
        frac = float(ts.notna().sum()) / len(raw)
        named = any(h in str(col).lower() for h in TIMEPOINT_HINTS)
        if ts.dropna().nunique() < 5:
            continue
        if frac >= (0.80 if named else 0.98):
            out[str(col)] = ts
    return out


def find_derived_mismatch(df) -> list[dict]:
    """自报的「时长」列与两个日期列之差对不上。

    2025C 实测：孕周列与「检测日期 − 末次月经」只有 38.4% 的行吻合到 0.15 周内。
    两列都在附件里、都能用，**选哪一列当准会改变结果**，所以必须在论文里写理由。
    """
    import numpy as np
    import pandas as pd

    date_map = _date_columns(df)
    dates = list(date_map)
    if len(dates) < 2:
        return []

    out: list[dict] = []
    for col in df.columns:
        name = str(col).lower()
        if any(h in name for h in TIMEPOINT_HINTS):
            continue
        unit = next(((u, k, tol) for u, k, tol in DURATION_UNITS
                     if u.lower() in name), None)
        if unit is None:
            continue
        _, per_day, tol = unit

        stated = pd.to_numeric(df[col], errors="coerce")
        if stated.notna().sum() < 5:                    # 可能是 `11w+6` 这种写法
            stated = df[col].map(lambda v: _parse_week(v)
                                 if isinstance(v, str) else np.nan)
            stated = pd.to_numeric(stated, errors="coerce")
        if stated.notna().sum() < 5:
            continue

        for d1, d2 in itertools.permutations(dates, 2):
            delta = ((date_map[d2] - date_map[d1]).dt.total_seconds()
                     / 86400.0 / per_day)
            m = stated.notna() & delta.notna()
            if m.sum() < 5 or delta[m].std(ddof=0) == 0:
                continue
            if float(delta[m].median()) < 0:
                continue                                # 方向反了，换一对
            agree = float((abs(delta[m] - stated[m]) <= tol).mean())
            if agree >= 0.95:
                continue                                # 对得上，没问题
            corr = float(np.corrcoef(delta[m], stated[m])[0, 1])
            if not np.isfinite(corr) or corr < 0.5:
                continue                                # 本来就不是这个派生量
            out.append({
                "kind": "derived_mismatch",
                "msg": "列 %r 与「%s − %s」相关 %.2f（显然是同一个量），"
                       "但只有 %.1f%% 的行吻合到 ±%g（查了 %d 行，中位差 %.2f）"
                       % (str(col), str(d2), str(d1), corr, agree * 100, tol,
                          int(m.sum()), float((delta[m] - stated[m]).median())),
                "action": "**两列本该自洽却对不上。选哪一列当准会改变结果，"
                          "所以必须在论文里写明理由**（谁的采集环节更可靠、"
                          "题面有没有指定口径）。别默默用其中一个，也别取平均——"
                          "取平均等于假设两边的误差同分布，这个假设你证不了。",
                "columns": [str(col), str(d1), str(d2)]})
            break
    return out


def find_identity_collinear(df, exclude: set[str] | None = None) -> list[dict]:
    """恒等式关系的变量同时入模 → VIF 爆掉，系数不可解释。

    线性空间和 log 空间各算一遍：BMI ≡ 体重/身高² 是乘除关系，
    **取对数之后才是精确线性**（log BMI = log w − 2 log h），log 空间的 VIF 更灵。

    `exclude`：已经被 `compositional` 报过的列组。定和约束本身就会让 VIF 爆到
    1e15，那是**同一件事的第二种表现**，再报一遍只会稀释信号。
    """
    import numpy as np

    num = df.select_dtypes("number")
    num = num.loc[:, num.nunique(dropna=True) > 1]
    # `Unnamed: N` 是 pandas 给无名列的占位名，不是变量。它们几乎总来自表头错行
    # 或宽表转置，报出来读者也对不上是哪个量。
    num = num.loc[:, [c for c in num.columns
                      if not str(c).startswith("Unnamed:")]]
    if exclude:
        num = num.loc[:, [c for c in num.columns if str(c) not in exclude]]
    if num.shape[1] < 3:
        return []
    # **宽矩阵不做这个检查。** 2021「近5年402家供应商」是 242 列的
    # 企业×月份矩阵、2023 附件是 203 列——列本身就是同一个量的不同时点，
    # 彼此高度相关是数据的形态而不是恒等式。截前 25 列算 VIF 报出来全是噪声。
    if num.shape[1] > MAX_VIF_COLS:
        return []

    def vifs(M: "np.ndarray", cols: list[str]) -> list[tuple[str, float]]:
        n, p = M.shape
        if n < 2 * p + 2:
            return []
        hits = []
        for j in range(p):
            y = M[:, j]
            X = np.delete(M, j, axis=1)
            X = np.column_stack([np.ones(n), X])
            try:
                beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            except np.linalg.LinAlgError:
                continue
            resid = y - X @ beta
            ss_tot = float(((y - y.mean()) ** 2).sum())
            if ss_tot <= 0:
                continue
            r2 = 1.0 - float((resid ** 2).sum()) / ss_tot
            r2 = min(max(r2, 0.0), 1.0 - 1e-15)
            v = 1.0 / (1.0 - r2)
            if v > VIF_ALERT:
                hits.append((cols[j], v))
        return sorted(hits, key=lambda kv: -kv[1])

    sub = num.dropna()
    if len(sub) < 8:
        return []
    cols = [str(c) for c in sub.columns]
    out: list[dict] = []

    for space, M in (("原始", sub.to_numpy(dtype=float)),
                     ("log", np.log(sub.to_numpy(dtype=float))
                      if bool((sub > 0).all().all()) else None)):
        if M is None or not np.isfinite(M).all():
            continue
        hits = vifs(M, cols)
        if not hits:
            continue
        out.append({
            "kind": "identity_collinear",
            "msg": "%s空间里这些列的 VIF 超过 %g：%s（查了 %d 行、%d 列）"
                   % (space, VIF_ALERT,
                      "、".join("%s=%.3g" % kv for kv in hits[:6]),
                      len(sub), len(cols)),
            "action": ("**多半存在恒等式关系**（如 BMI ≡ 体重/身高²）。"
                       "同时入模会让回归系数不可解释——符号可以整个翻过来，"
                       "而且不报错。留一个、或改用比值/残差这类正交化的构造，"
                       "并在论文里说明取舍。"
                       + ("log 空间才炸说明是**乘除**关系，不是加减关系。"
                          if space == "log" else "")),
            "columns": [c for c, _ in hits]})
        if space == "原始" and hits:
            break                                       # 已经报了，log 不用重复
    return out


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

    comp_cols: set[str] = set()
    for comp in find_compositional(df):
        comp_cols.update(str(c) for c in comp["columns"])
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

    # 静默陷阱 §四那四条。单独放在最后，是因为它们**不改方法主线，改数字**——
    # 上面几类看漏了整条路线错，这几类看漏了路线对而结果错，后者更难自己发现。
    # 用 (名字, 调用) 而不是裸函数：出错时要报得出是哪一项，
    # 而 lambda / partial 的 __name__ 是 '<lambda>'，等于没报。
    for fname, finder in (
            ("find_mixed_dtype", find_mixed_dtype),
            ("find_case_collision", find_case_collision),
            ("find_derived_mismatch", find_derived_mismatch),
            ("find_identity_collinear",
             lambda d: find_identity_collinear(d, exclude=comp_cols))):
        try:
            out["findings"].extend(finder(df))
        except Exception as exc:                       # noqa: BLE001
            # 体检项自己崩掉不该让整张表扫不出来。**但要说出来**——
            # 静默跳过一项检查，和这项检查通过，在输出上长得一模一样。
            out["findings"].append({
                "kind": "check_error",
                "msg": "检查 %s 自身出错：%s: %s"
                       % (fname, type(exc).__name__, exc),
                "action": "**这一项没测到**，不等于没问题。手工过一遍 "
                          "静默陷阱.md §四 对应那条。",
                "columns": []})

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
