# -*- coding: utf-8 -*-
"""按题型分类的图表范例。每张图既是模板，也是对样式模块的验证。

跑法（在本目录下）：
    python gallery.py                 # 全出
    python gallery.py 机理 数据       # 只出指定题型

每张图都会同时输出一份 `_gray.png` 灰度校样——**评委很可能打印黑白稿**，
而这套色板在灰度下有几对几乎同色，全靠线型/填充网格/标记区分。
出完图务必翻一遍灰度稿，那才是判卷人看到的东西。

数据来源：能用真题附件的就用真的（路径见各函数），用不到的才合成。
拿真数据画是有意的——范例同时验证了"这套样式在真实数据的量级与分布下也成立"。
"""

from __future__ import annotations

import os
import sys

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cumcm_style as cs  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gallery")

# 三张范例用真题附件画（拿真数据画是有意的——同时验证了这套样式在真实量级下成立）。
# 附件不随 skill 分发，所以路径从环境变量取，取不到就**跳过那三张**，
# 其余五张不依赖任何外部数据，任何人 clone 下来都能跑。
#     Windows:  set CUMCM_REPO=D:\Desktop\数学建模
#     bash:     export CUMCM_REPO=/path/to/数学建模
REPO = os.environ.get("CUMCM_REPO", "")


class MissingAttachment(RuntimeError):
    """附件不可得。调用方据此跳过，而不是让整个 gallery 崩掉。"""


def _attach(*parts) -> str:
    if not REPO:
        raise MissingAttachment(
            "未设置 CUMCM_REPO，跳过依赖真题附件的范例。"
            "设成资料库根目录（其下应有 1_赛题与数据/）即可。")
    p = os.path.join(REPO, "1_赛题与数据", *parts)
    if not os.path.isfile(p):
        raise MissingAttachment("找不到附件 %s" % p)
    return p


# ============================================================ 机理/几何/运动类
def fig_mechanism() -> list[dict]:
    """2023A 定日镜场：空间分布用顺序色，剖面用折线。

    机理类最常见的两张图就是「场分布」与「沿某一维的剖面」。
    分布图用**单一色相由浅到深**（连续量），绝不用彩虹——
    彩虹在灰度下完全乱序，而且正常视觉里也读不出大小关系。
    """
    import pandas as pd

    xy = pd.read_excel(_attach("2023", "A题", "附件.xlsx")).values.astype(float)
    r = np.hypot(xy[:, 0], xy[:, 1])
    # 用一个解析代理量代替真实效率，避免范例依赖演练产物
    eta = 0.62 - 0.00035 * r + 0.06 * (xy[:, 1] / (r + 1e-9))

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.2),
                             gridspec_kw={"width_ratios": [1, 1.15]})
    ax = axes[0]
    sc = ax.scatter(xy[:, 0], xy[:, 1], c=eta, s=4, cmap=cs.SEQ,
                    linewidths=0, zorder=3)
    ax.add_patch(plt.Circle((0, 0), 350, fill=False, ls="--",
                            color=cs.AXIS, lw=0.9))
    ax.plot(0, 0, marker="*", ms=11, color=cs.INK, zorder=4)
    cs.annotate_value(ax, 0, 0, "吸收塔", dy=9)
    ax.set_aspect("equal")
    ax.grid(False)
    cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("年平均光学效率 (无量纲)", fontsize=cs.BASE_FONT - 1)
    cb.outline.set_visible(False)
    cs.finish(ax, xlabel="x (m，正东)", ylabel="y (m，正北)",
              title="(a) 逐镜效率的空间分布", legend=False)

    ax = axes[1]
    north, south = xy[:, 1] > 0, xy[:, 1] <= 0
    bins = np.linspace(r.min(), r.max(), 14)
    ctr = 0.5 * (bins[1:] + bins[:-1])
    for i, (mask, name) in enumerate(((north, "塔北侧"), (south, "塔南侧"))):
        m = [eta[mask & (r >= a) & (r < b)].mean() for a, b in zip(bins, bins[1:])]
        ax.plot(ctr, m, label=name, **cs.series_kw(i, "line"))
    cs.annotate_value(ax, ctr[1], np.nanmax(eta[north][:50]) * 0 + 0.63,
                      "北侧更高：太阳在南，\n入射与出射夹角小", dy=-2)
    cs.finish(ax, xlabel="到吸收塔距离 (m)", ylabel="年平均光学效率 (无量纲)",
              title="(b) 沿距离的剖面：方位比距离更重要")
    cs.add_units_note(fig, "数据：2023A 附件（1745 面定日镜坐标）；效率为解析代理量，仅作范例")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "01_机理几何_场分布与剖面.png"))]


# ============================================================ 工程反演/测量类
def fig_inverse() -> list[dict]:
    """反演类的标准两联图：观测+拟合叠加，下面**必须**跟残差。

    只画"拟合得很好"是没有说服力的——残差图才看得出系统性偏差。
    2025B 演练里正是残差里的系统性结构暴露了观测量取错（群量 vs 原量）。
    """
    rng = np.random.default_rng(20260904)
    nu = np.linspace(500, 1500, 900)
    d_true, n0, disp = 7.45, 2.55, 4.0e-6
    n = n0 + disp * nu ** 2
    sig = 0.5 + 0.42 * np.cos(4 * np.pi * n * d_true * nu * 1e-4)
    obs = sig + rng.normal(0, 0.012, nu.size)
    fit = 0.5 + 0.42 * np.cos(4 * np.pi * (n0 + 3.4e-6 * nu ** 2)
                              * 7.44 * nu * 1e-4)

    fig, (ax, axr) = plt.subplots(
        2, 1, figsize=(9.6, 4.6), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
    ax.plot(nu, obs, label="实测反射率",
            **cs.series_kw(0, "line", n_points=nu.size, alpha=0.9))
    ax.plot(nu, fit, label="模型拟合", **cs.series_kw(1, "line", n_points=nu.size))
    k = int(np.argmax(obs))
    cs.annotate_value(ax, nu[k], obs[k], "首个极大 %.0f cm$^{-1}$" % nu[k], dy=7)
    cs.finish(ax, xlabel=" ", ylabel="反射率 (无量纲)",
              title="(a) 观测与拟合")
    ax.set_xlabel("")

    res = obs - fit
    axr.axhline(0, color=cs.AXIS, lw=0.9, zorder=1)
    axr.plot(nu, res, label="残差", color=cs.COLORS[7], lw=1.0, zorder=3)
    axr.fill_between(nu, res, 0, color=cs.COLORS[7], alpha=0.18, lw=0)
    cs.finish(axr, xlabel="波数 (cm$^{-1}$)", ylabel="残差",
              title="(b) 残差：低波数段有系统性结构 → 色散模型不足",
              legend=False)
    cs.add_units_note(fig, "范例数据为合成；结构照 2025B 型（多光束干涉 + 色散）")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "02_工程反演_拟合与残差.png"))]


# ============================================================ 数据/统计类
def fig_data_stats() -> list[dict]:
    """2025C：分组趋势 + 个体轨迹。

    **同一对象多条记录 → 观测不独立**，画图时就要让读者看见这件事：
    细灰线是个体轨迹，粗线是分组均值。只画散点会让人误以为样本独立。
    """
    import pandas as pd

    d = pd.read_excel(_attach("2025", "C题", "附件.xlsx"),
                      sheet_name="男胎检测数据")
    col_w, col_b, col_y = "检测孕周", "孕妇BMI", "Y染色体浓度"
    ycol = col_y if col_y in d.columns else \
        [c for c in d.columns if "Y" in str(c) and "浓度" in str(c)][0]

    def parse_week(v):
        s = str(v)
        if "w" in s:
            a, _, b = s.partition("w")
            try:
                return float(a) + (float(b.strip("+") or 0) / 7 if b.strip("+") else 0)
            except ValueError:
                return np.nan
        try:
            return float(s)
        except ValueError:
            return np.nan

    d = d[[c for c in ("孕妇代码", col_w, col_b, ycol) if c in d.columns]].dropna()
    d["w"] = d[col_w].map(parse_week)
    d = d.dropna(subset=["w"])
    d["y"] = pd.to_numeric(d[ycol], errors="coerce")
    d = d.dropna(subset=["y"])
    if d["y"].max() <= 1.0:
        d["y"] *= 100.0

    edges = [0, 28, 32, 36, 100]
    names = ["BMI<28", "28–32", "32–36", "≥36"]
    d["g"] = pd.cut(d[col_b], edges, labels=names, right=False)

    fig, ax = plt.subplots(figsize=cs.SIZE_1COL)
    for _, sub in d.groupby("孕妇代码"):
        if len(sub) >= 2:
            ax.plot(sub["w"], sub["y"], color=cs.MUTED, lw=0.4,
                    alpha=0.35, zorder=1)
    grid = np.linspace(d["w"].min(), d["w"].max(), 12)
    for i, name in enumerate(names):
        sub = d[d["g"] == name]
        if len(sub) < 10:
            continue
        m = [sub.loc[(sub["w"] >= a) & (sub["w"] < b), "y"].mean()
             for a, b in zip(grid, grid[1:])]
        ax.plot(0.5 * (grid[1:] + grid[:-1]), m,
                label="%s (n=%d)" % (name, sub["孕妇代码"].nunique()),
                **cs.series_kw(i, "line"))
    ax.axhline(4.0, color=cs.STATUS["critical"], lw=1.1, ls=(0, (4, 2)), zorder=2)
    cs.annotate_value(ax, grid[-3], 4.0, "达标线 4%", dy=5,
                      color=cs.STATUS["critical"])
    cs.finish(ax, xlabel="检测孕周 (周)", ylabel="Y 染色体浓度 (%)",
              title="灰细线为个体轨迹——同一孕妇多次检测，观测不独立")
    cs.add_units_note(fig, "数据：2025C 附件 男胎检测数据（%d 次检测 / %d 位孕妇）"
                      % (len(d), d["孕妇代码"].nunique()))
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "03_数据统计_分组趋势与个体轨迹.png"))]


# ============================================================ 统计决策类
def fig_decision() -> list[dict]:
    """决策类：枚举结果的期望值排序 + 决策翻转边界。

    交付的**不是重算一遍数字，是决策翻转边界**——参数动到哪里最优解会换。
    左图用条形（带填充网格，灰度可分），右图用两条线夹出翻转点。
    """
    combos = ["不检测\n不拆解", "检零件\n不拆解", "检成品\n不拆解",
              "全检\n不拆解", "检成品\n拆解", "全检\n拆解"]
    profit = np.array([32.5, 35.8, 41.2, 39.0, 45.6, 43.1])
    best = int(np.argmax(profit))

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9))
    ax = axes[0]
    for i, (c, p) in enumerate(zip(combos, profit)):
        kw = cs.series_kw(0 if i != best else 2, "bar")
        ax.bar(i, p, width=0.68, **kw)
    cs.annotate_value(ax, best, profit[best], "最优 %.1f" % profit[best], dy=4)
    ax.set_xticks(range(len(combos)))
    ax.set_xticklabels(combos, fontsize=cs.BASE_FONT - 2)
    cs.finish(ax, xlabel="决策组合（共 %d 种，枚举即精确解）" % len(combos),
              ylabel="期望利润 (元/件)", title="(a) 全枚举结果", legend=False)

    ax = axes[1]
    p = np.linspace(0.02, 0.25, 120)
    keep = 46 - 120 * p
    dismantle = 41 - 40 * p
    ax.plot(p, keep, label="方案甲：不拆解", **cs.series_kw(0, "line", n_points=p.size))
    ax.plot(p, dismantle, label="方案乙：拆解重装",
            **cs.series_kw(1, "line", n_points=p.size))
    cross = p[int(np.argmin(np.abs(keep - dismantle)))]
    ax.axvline(cross, color=cs.INK_2, lw=0.9, ls=(0, (2, 2)), zorder=2)
    cs.annotate_value(ax, cross, keep.min(), "翻转点 p=%.3f" % cross, dy=6)
    cs.finish(ax, xlabel="零配件次品率 p (无量纲)", ylabel="期望利润 (元/件)",
              title="(b) 决策翻转边界")
    cs.add_units_note(fig, "范例数据为合成；结构照 2024B 型（给参数表、无数据附件）")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "04_统计决策_枚举与翻转边界.png"))]


# ============================================================ 成分数据类
def fig_compositional() -> list[dict]:
    """2022C：成分堆叠 + CLR 后的判别。

    成分数据活在单纯形上。**堆叠条要用填充网格**（灰度下才分得开），
    而统计分析必须在 CLR 变换之后做——直接算 Pearson 相关有偏负倾向。
    """
    import pandas as pd

    p = _attach("2022", "C题", "附件.xlsx")
    comp = pd.read_excel(p, sheet_name="表单2")
    meta = pd.read_excel(p, sheet_name="表单1")
    oxides = [c for c in comp.columns if "(" in str(c)]
    X = comp[oxides].fillna(0.0).to_numpy(float)
    total = X.sum(axis=1)
    valid = (total >= 85) & (total <= 105)          # 题面给的有效性区间
    X = X[valid] / total[valid, None] * 100.0

    comp["_id"] = comp["文物采样点"].astype(str).str.extract(r"(\d+)")[0]
    meta["_id"] = meta["文物编号"].astype(str)
    typ = comp.loc[valid].merge(meta[["_id", "类型"]], on="_id", how="left")["类型"]
    typ = typ.fillna("未知").to_numpy()

    # ⚠ 形式选择：**不要给 67 个样本各画一根堆叠条**。
    # 第一版就是那么画的，实测条宽只剩 1px、填充网格完全看不见，
    # 灰度稿糊成一片——而且 67 根条也回答不了任何问题。
    # 数据的任务是"成分随类型怎么变"，所以按类型聚合成少数几根**宽**条：
    # 条一宽，填充网格才起作用，这是灰度可读的前提。
    groups = [g for g in ("高钾", "铅钡") if (typ == g).sum() >= 3]
    top = np.argsort(-X.mean(axis=0))[:5]

    fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.2),
                             gridspec_kw={"width_ratios": [1, 1.1]})
    ax = axes[0]
    bottom = np.zeros(len(groups))
    xs = np.arange(len(groups))
    for k, j in enumerate(top):
        v = np.array([X[typ == g, j].mean() for g in groups])
        ax.bar(xs, v, bottom=bottom, width=0.52,
               label=str(oxides[j]).split("(")[0], **cs.series_kw(k, "bar"))
        for x, (b, h) in enumerate(zip(bottom, v)):
            if h >= 6:                      # 只在放得下的段里直接标数
                ax.text(x, b + h / 2, "%.0f" % h, ha="center", va="center",
                        fontsize=cs.BASE_FONT - 2, color=cs.SURFACE)
        bottom += v
    ax.bar(xs, 100 - bottom, bottom=bottom, width=0.52, label="其他",
           facecolor="#d8d7d1", edgecolor=cs.SURFACE, linewidth=0.0)
    ax.set_ylim(0, 118)                      # 给图例留出条形之上的空间
    ax.set_xticks(xs)
    ax.set_xticklabels(["%s\n(n=%d)" % (g, int((typ == g).sum())) for g in groups])
    ax.grid(True, axis="y")
    cs.finish(ax, xlabel="玻璃类型", ylabel="归一化后平均含量 (%)",
              title="(a) 按类型的平均成分：各分量之和恒为 100",
              legend_loc="upper center")

    ax = axes[1]
    eps = 0.01
    Z = np.log(np.clip(X, eps, None))
    Z = Z - Z.mean(axis=1, keepdims=True)           # CLR
    Z = Z - Z.mean(axis=0, keepdims=True)
    U, S, Vt = np.linalg.svd(Z, full_matrices=False)
    pc = U[:, :2] * S[:2]
    for i, name in enumerate([t for t in ("高钾", "铅钡") if t in set(typ)]):
        m = typ == name
        ax.plot(pc[m, 0], pc[m, 1], label=name, ms=6,
                **cs.series_kw(i, "scatter", n_series=2))
    ax.grid(True, axis="both")
    var = S ** 2 / (S ** 2).sum()
    cs.finish(ax, xlabel="CLR-PC1 (%.0f%% 方差)" % (var[0] * 100),
              ylabel="CLR-PC2 (%.0f%% 方差)" % (var[1] * 100),
              title="(b) CLR 变换后两类自然分开")
    cs.add_units_note(fig, "数据：2022C 附件 表单2；已按题面『累加和 85%~105%』筛有效样本并归一化")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "05_成分数据_堆叠与CLR判别.png"))]


# ============================================================ 通用：灵敏度
def fig_sensitivity() -> list[dict]:
    """龙卷风图：一眼看出"结论对哪个参数最敏感"。

    Stage 6 的标准交付。用发散色（有正负、中点是灰），
    并**按影响幅度排序**——不排序的龙卷风图等于没画。
    """
    params = ["太阳锥角半角", "镜面反射率", "安装高度", "大气透射系数",
              "集热器半径", "网格采样密度"]
    low = np.array([-11.5, -4.2, -1.6, -3.1, -6.8, -0.4])
    high = np.array([4.2, 4.0, 1.1, 3.0, 5.9, 0.5])
    order = np.argsort(np.abs(high - low))
    y = np.arange(len(params))

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.barh(y, low[order], color=cs.COLORS[0], hatch="//",
            edgecolor=cs.COLORS[0], linewidth=0.0, label="参数取下界")
    ax.barh(y, high[order], color=cs.COLORS[7], hatch="\\\\",
            edgecolor=cs.COLORS[7], linewidth=0.0, label="参数取上界")
    ax.axvline(0, color=cs.AXIS, lw=1.0, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels([params[i] for i in order])
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    cs.annotate_value(ax, low[order][-1], y[-1], "%.1f%%" % low[order][-1],
                      dx=-16, dy=-3)
    cs.finish(ax, xlabel="总功率相对基线的变化 (%)", ylabel="扰动参数",
              title="按影响幅度排序：可行性只由第一项决定")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "06_通用_灵敏度龙卷风图.png"))]


# ============================================================ 通用：方案对比
def fig_tradeoff() -> list[dict]:
    """约束-目标权衡图：把"为什么选这个方案"一张图说清。

    带**约束线**的散点/折线是设计类题目的核心图——
    它同时表达了可行域、目标方向和最优点的位置。
    """
    w = np.array([5.75, 5.82, 5.90, 6.05, 6.20, 6.45, 6.75, 7.00])
    power = np.array([59.70, 59.93, 60.01, 60.79, 61.02, 60.14, 60.11, 59.82])
    unit = np.array([0.5110, 0.5075, 0.5038, 0.4961, 0.4889, 0.4633, 0.4451, 0.4302])
    ok = power >= 60.0

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.8))
    ax.plot(w, power, label="年平均输出热功率", **cs.series_kw(0, "line"))
    ax.axhline(60, color=cs.STATUS["critical"], lw=1.1, ls=(0, (4, 2)), zorder=2)
    cs.annotate_value(ax, w[-2], 60, "额定 60 MW", dy=5,
                      color=cs.STATUS["critical"])
    ax.plot(w[ok][0], power[ok][0], marker="*", ms=13, color=cs.INK, zorder=5,
            linestyle="none", label="终选：恰好达标的最小镜宽")
    cs.finish(ax, xlabel="定日镜宽度 = 高度 (m)", ylabel="年平均输出热功率 (MW)",
              title="(a) 约束：总功率先升后降")

    ax2.plot(w, unit, label="单位面积输出热功率", **cs.series_kw(2, "line"))
    ax2.plot(w[ok][0], unit[ok][0], marker="*", ms=13, color=cs.INK, zorder=5,
             linestyle="none", label="终选")
    ax2.fill_between(w, unit, unit.min(), where=~ok, color=cs.MUTED,
                     alpha=0.16, lw=0)
    cs.annotate_value(ax2, w[1], unit[1], "灰区：达不到额定功率", dy=-16)
    cs.finish(ax2, xlabel="定日镜宽度 = 高度 (m)",
              ylabel="单位面积年平均输出热功率 (kW/m$^2$)",
              title="(b) 目标：单调下降 → 取可行域左端点")
    cs.add_units_note(fig, "数据：2023A 端到端演练（耦合口径，完整 60 时点）"
                           "。两个量分成两图，不用双纵轴")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "07_通用_约束与目标权衡.png"))]


# ============================================================ 几何/物理示意图
def fig_schematic() -> list[dict]:
    """**优秀论文里最大的一类**（44 篇官方展示中 61% 有，平均 4.9 张，最多 24 张；
    A 题图题里占 35%），而它恰恰不是"画数据"，是"把几何关系说清楚"。

    从真论文里学到的四条画法，全部体现在这张图里：

    1. **分层色带**分区域（2025B 的薄膜图：空气/外延层/衬底三色），
       浅色打底、不抢线条；
    2. **关键量用红色强调**，其余一律黑线——红色是"看这里"，不是配色；
    3. **角度画成弧 + 希腊字母**，长度画成双箭头 + 变量名，不要只写文字；
    4. **虚线是辅助线**（法线、投影、参考面），实线是实体。

    另有一条 B 题里反复出现的做法：**同一张底图重复使用，每次只强调一个新量**。
    读者不用重新理解构型，注意力全在新增的那个量上。
    """
    from matplotlib.patches import Arc

    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.set_aspect("equal"); ax.axis("off")

    # 1. 分层色带。**注意上下顺序**：matplotlib 的 y 向上，光从上方的空气入射，
    #    所以空气必须是 y 最大的那一层。第一版写反了，图上光从衬底里射出来。
    for y0, y1, c, name in ((5.0, 8.0, "#fdf3d8", "空气  $n_0$"),
                            (3.2, 5.0, "#e3eefb", "外延层  $n_1(\lambda)$"),
                            (0.4, 3.2, "#e6f3ec", "衬底  $n_2$")):
        ax.add_patch(plt.Rectangle((0.6, y0), 8.8, y1 - y0, facecolor=c,
                                   edgecolor="none", zorder=0))
        ax.text(0.85, (y0 + y1) / 2, name, fontsize=cs.BASE_FONT - 1,
                va="center", color=cs.INK_2, zorder=4)
    for y in (5.0, 3.2):
        ax.plot([0.6, 9.4], [y, y], color=cs.INK, lw=1.1, zorder=2)

    # 2. 虚线 = 辅助线（法线）
    ax.plot([5.0, 5.0], [3.4, 6.9], ls=(0, (3, 3)), color=cs.INK_2, lw=0.9, zorder=3)
    ax.text(5.12, 6.75, "法线", fontsize=cs.BASE_FONT - 2, color=cs.INK_2)

    # 3. 黑线 = 一般光路；红线 = 本图要讲的那条
    def arrow(p, q, color, ls="-", lw=1.6):
        ax.annotate("", xy=q, xytext=p,
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                    linestyle=ls, shrinkA=0, shrinkB=0))
    R = cs.STATUS["critical"]
    arrow((2.6, 7.1), (5.0, 5.0), cs.INK)          # 入射
    arrow((5.0, 5.0), (7.4, 7.1), cs.INK)          # 直接反射
    arrow((5.0, 5.0), (6.05, 3.2), R, lw=1.8)      # 折射进入外延层
    arrow((6.05, 3.2), (7.1, 5.0), R, lw=1.8)      # 底界面反射
    arrow((7.1, 5.0), (8.9, 6.6), R, ls=(0, (4, 2)), lw=1.8)   # 出射

    # 4. 角画成弧 + 希腊字母。弧的起止角要算清楚，别扫过整圈。
    ax.add_patch(Arc((5.0, 5.0), 2.0, 2.0, theta1=90, theta2=139,
                     color=cs.INK, lw=1.0))
    ax.text(4.28, 6.05, r"$\theta_0$", fontsize=cs.BASE_FONT + 1)
    ax.add_patch(Arc((5.0, 5.0), 1.6, 1.6, theta1=270, theta2=300,
                     color=R, lw=1.0))
    ax.text(5.22, 4.15, r"$\theta_1$", fontsize=cs.BASE_FONT + 1, color=R)

    # 5. 长度画成双箭头 + 变量名。目标量用红色。
    ax.annotate("", xy=(8.9, 3.2), xytext=(8.9, 5.0),
                arrowprops=dict(arrowstyle="<|-|>", color=R, lw=1.4))
    ax.text(9.05, 4.1, "$d$", fontsize=cs.BASE_FONT + 2, color=R, va="center")

    ax.text(2.5, 7.25, "入射", fontsize=cs.BASE_FONT - 1, color=cs.INK_2)
    ax.text(7.3, 7.25, "直接反射", fontsize=cs.BASE_FONT - 1, color=cs.INK_2)
    ax.text(8.2, 6.75, "二次反射", fontsize=cs.BASE_FONT - 1, color=R)
    ax.set_title("红色 = 本图要讲的量（外延层厚度 $d$ 与其光程）；"
                 "虚线 = 辅助线；弧 = 角",
                 loc="left", pad=10, fontsize=cs.BASE_FONT)
    cs.add_units_note(fig, "画法取自 44 篇官方展示论文里最大的一类图（示意/几何，61% 的论文有）")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "08_几何示意图_分层与标注.png"))]



BUILDERS = {
    "机理": fig_mechanism,
    "反演": fig_inverse,
    "数据": fig_data_stats,
    "决策": fig_decision,
    "成分": fig_compositional,
    "灵敏度": fig_sensitivity,
    "权衡": fig_tradeoff,
    "示意图": fig_schematic,
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    font = cs.use()
    print("中文字体：%s" % font)
    os.makedirs(OUT, exist_ok=True)
    want = sys.argv[1:] or list(BUILDERS)
    made, skipped = [], []
    for key in want:
        if key not in BUILDERS:
            print("跳过未知题型 %r（可选：%s）" % (key, "/".join(BUILDERS)))
            continue
        try:
            for info in BUILDERS[key]():
                made.append(info)
                print("  ✓ %s  %.1f×%.1f in  灰度校样 %s"
                      % (os.path.basename(info["path"]), *info["size_inch"],
                         "有" if info["gray"] else "无(缺 Pillow)"))
        except MissingAttachment as exc:
            skipped.append(key)
            print("  – %s 跳过：%s" % (key, exc))
        except Exception as exc:                       # noqa: BLE001
            print("  ✗ %s 失败：%s: %s" % (key, type(exc).__name__, exc))
    print("\n共 %d 张，输出在 %s" % (len(made), OUT))
    if skipped:
        print("跳过 %d 张（%s）：这几张用真题附件画，设 CUMCM_REPO 指向资料库根目录后重跑。"
              % (len(skipped), "/".join(skipped)))
    print("翻一遍 _gray.png 可以看打印稿的样子（成本近零的保险，不是硬门槛）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
