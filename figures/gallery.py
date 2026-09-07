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

# 输出编码交给 scripts/_console.py，不要在 main() 里无条件
# `sys.stdout.reconfigure(encoding="utf-8")`——那样会把 cp936 交互控制台里的
# 中文打成乱码。_console.init() 只在非 tty（管道/mintty）时才切 UTF-8，
# 并把 ✓/✗ 降级成 ASCII 兜底。详见该文件的模块 docstring。
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
try:
    import _console  # noqa: E402
except ImportError:                                    # figures/ 被单独拷出去用
    class _console:                                    # noqa: N801
        @staticmethod
        def init() -> None:
            pass

        @staticmethod
        def sym(text: str) -> str:
            return text

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

    # **hspace 不能放进 gridspec_kw**：后面的 `tight_layout()` 会重算并把它丢掉，
    # matplotlib 3.11 只给一句 "Axes that are not compatible with tight_layout"
    # 的 UserWarning，图照出——两个面板之间的紧贴间距静默失效。
    # 正确顺序是 tight_layout() 之后再 subplots_adjust()（见函数末尾）。
    fig, (ax, axr) = plt.subplots(
        2, 1, figsize=(9.6, 4.6), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]})
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
    fig.subplots_adjust(hspace=0.10)      # 残差面板紧贴主图，共用一条 x 轴
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
    # **必须走 series_kw，不要手写 color/hatch/edgecolor。**
    # 这里原来写的是 `color=COLORS[0], hatch="//", edgecolor=COLORS[0]`——
    # matplotlib 的 hatch 线正是用 edgecolor 画的，设成和填充同色等于用填充色
    # 在填充上画线：彩色稿勉强看得出，**灰度稿里上下界两根条完全同色、
    # 网格一根都看不见**，第二通道整个失效（`linewidth=0.0` 又雪上加霜）。
    # README「开发过程中被实测纠正的三处」第一条讲的就是它，
    # 但那次只修进了 series_kw，这张图绕过了 series_kw 所以一直还是坏的。
    ax.barh(y, low[order], label="参数取下界",
            **cs.series_kw(0, "bar", height=0.62))
    ax.barh(y, high[order], label="参数取上界",
            **cs.series_kw(7, "bar", height=0.62))
    ax.axvline(0, color=cs.AXIS, lw=1.0, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels([params[i] for i in order])
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    # 标注往**图内**偏（dx 为正）。原来是 dx=-16，把文字推到了 y 轴外面，
    # 和刻度标签叠成"太阳锥角半角-11.5%"。
    cs.annotate_value(ax, low[order][-1], y[-1], "%.1f%%" % low[order][-1],
                      dx=22, dy=-3)
    ax.margins(x=0.06)
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
    # 含 LaTeX 的字符串一律加 r 前缀：`"$n_1(\lambda)$"` 里的 `\l` 是无效转义，
    # Python 3.12 只报 SyntaxWarning（图照出），3.15 起会变 SyntaxError。
    for y0, y1, c, name in ((5.0, 8.0, "#fdf3d8", r"空气  $n_0$"),
                            (3.2, 5.0, "#e3eefb", r"外延层  $n_1(\lambda)$"),
                            (0.4, 3.2, "#e6f3ec", r"衬底  $n_2$")):
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



# ============================================================ 通用：技术路线流程图
def fig_flow() -> list[dict]:
    """总体技术路线图。**52% 的一等奖论文有流程图，平均 2.3 张**
    （44 篇官方展示实测），通常是"总体一张 + 每问一张"，而
    `paper_skeleton.md` 的 `## 2.1 总体技术路线` 就是给它留的位置。

    这张是"总体一张"的画法。四条规矩都体现在代码里：

    1. **层级靠位置和箭头表达，不靠颜色**。颜色只标角色（输入/步骤/建模/
       校验/输出），灰度稿里塌成同一片浅灰也读得懂——因为结构没依赖颜色。
    2. **箭头连边中点，不连中心**（`b.s` → `b2.n`）。连中心的箭头会扎进框里
       压住文字，这是手搓流程图最常见的翻车点。
    3. **反馈边画虚线**，和主流程一眼分开。有回检环的论文，评委看得出你真回检了。
    4. **框里写"做什么"，不写"用什么"**。"跨问一致性回检"比"一致性模块"有信息。
    """
    fig, ax = cs.flow_canvas(figsize=(7.2, 5.6))

    # 上面两个框故意跨在 Q1/Q2 上方（x=2..50），好让主干箭头**正对 Q1 的中线**
    # 竖直落下。上面居中、下面靠左的话，主干第一根箭头就是一条斜线，
    # 读者第一眼要判断它到底指向哪个 Q。
    b_in = cs.flow_box(ax, 2, 85.5, 48, 8.5, "题面 + 附件数据", tint="input")
    b_sc = cs.flow_box(ax, 2, 71, 48, 10.5,
                       "附件结构体检 → 判题型\n成分? 重复测量? 数据口径?",
                       tint="step")
    b_q1 = cs.flow_box(ax, 2, 52, 28, 11,
                       "Q1 基准模型\n最简情形先跑通", tint="model")
    b_q2 = cs.flow_box(ax, 36, 52, 28, 11,
                       "Q2 加不确定性\n随机 / 鲁棒", tint="model")
    b_q3 = cs.flow_box(ax, 70, 52, 28, 11,
                       "Q3 加耦合\n变量间相关性", tint="model")
    b_ck = cs.flow_box(ax, 22, 33, 56, 10.5,
                       "跨问一致性回检\n把「上界/不可行」类断言用最终解代回",
                       tint="check")
    b_se = cs.flow_box(ax, 22, 19, 56, 9, "灵敏度 + 鲁棒性（按影响排序）",
                       tint="step")
    b_out = cs.flow_box(ax, 22, 4, 56, 9, "结论、决策建议与交付文件",
                        tint="output")

    cs.flow_arrow(ax, b_in.bottom(0.29), b_sc.top(0.29))
    cs.flow_arrow(ax, b_sc.bottom(0.29), b_q1.n)
    # 这两根只有 6 个单位长，文字必须抬到箭头上方——压在上面白底会把线盖没
    cs.flow_arrow(ax, b_q1.e, b_q2.w_, text="解沿用", text_dy=3.4)
    cs.flow_arrow(ax, b_q2.e, b_q3.w_, text="解沿用", text_dy=3.4)
    # 三条汇聚线落在回检框上边的不同分数位，箭头尖不会叠成一团
    for b, f in ((b_q1, 0.10), (b_q2, 0.50), (b_q3, 0.90)):
        cs.flow_arrow(ax, b.s, b_ck.top(f))
    cs.flow_arrow(ax, b_ck.s, b_se.n)
    cs.flow_arrow(ax, b_se.s, b_out.n)
    # 反馈环：回检不过就回到建模。虚线 + 直角折线（先向左、再向上），
    # 走在主干外侧，一条线都不跨。
    cs.flow_arrow(ax, b_ck.w_, b_q1.bottom(0.2), angle=(180, 90), dashed=True)
    ax.text(9.2, 44.6, "不一致 → 回到建模", ha="left", va="center",
            fontsize=cs.BASE_FONT - 2, color=cs.INK_2,
            bbox=dict(boxstyle="round,pad=0.18", facecolor=cs.SURFACE,
                      edgecolor="none"))

    # 图例：五种角色各是什么。流程图不用 ax.legend，直接画色块更省地方。
    for k, (name, label) in enumerate(
            (("input", "输入"), ("step", "处理"), ("model", "建模求解"),
             ("check", "校验回检"), ("output", "交付"))):
        x = 2 + k * 19.6
        ax.add_patch(plt.Rectangle((x, 96.6), 3.2, 2.3,
                                   facecolor=cs.FLOW_TINTS[name],
                                   edgecolor=cs.AXIS, linewidth=0.7))
        ax.text(x + 4.2, 97.75, label, va="center", ha="left",
                fontsize=cs.BASE_FONT - 2, color=cs.INK_2)

    ax.set_title("总体技术路线（框=做什么，虚线=回检不过时的返工路径）",
                 loc="left", pad=8, fontsize=cs.BASE_FONT)
    cs.add_units_note(fig, "画法依据：44 篇官方展示论文中 52% 有流程图，"
                           "平均 2.3 张（总体一张 + 每问一张）")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "09_通用_技术路线流程图.png"))]


# ============================================================ 通用：相关矩阵
def _spearman(X: "np.ndarray") -> "np.ndarray":
    """Spearman = 秩上的 Pearson。自己算，省一个 scipy 依赖。

    用 Spearman 而不是 Pearson 的理由要写进论文：不要求正态、对单调非线性
    和离群点都稳。2024C 一等奖就是这么选的。
    """
    R = np.apply_along_axis(
        lambda col: np.argsort(np.argsort(col)).astype(float), 0, X)
    return np.corrcoef(R, rowvar=False)


def fig_corr() -> list[dict]:
    """相关系数矩阵 + 最强那一对的散点确认。

    为什么要配第二个面板：**热力图只给候选，不给结论**。一个 0.9 的格子可能
    来自真单调关系，也可能来自两个离群点，或者是被中间段的散点掩盖的 U 形——
    矩阵上都长成同一个深色格。`playbook-evaluation-decision.md` 要求
    "必须先做相关系数矩阵，必要时合并或删减指标"，而删指标之前必须看散点。

    色标的坑写在 `cs.corr_heatmap` 的 docstring 里：随手 `imshow(C)` 会按数据
    范围自动拉伸，0 就不在中点上了，**"看起来中性"的格子其实是强正相关**。
    """
    rng = np.random.default_rng(20240907)
    n = 240
    # 因子模型生成，保证矩阵是真正的相关矩阵（半正定），不是手填的数
    f_scale = rng.normal(size=n)          # 地块规模因子
    f_price = rng.normal(size=n)          # 市场行情因子
    area = 60 + 14 * f_scale + rng.normal(0, 3, n)
    yield_ = 420 + 55 * f_scale + rng.normal(0, 40, n)
    price = 6.2 + 1.5 * f_price + rng.normal(0, 0.35, n)
    cost = 2.4 + 0.42 * f_price + 0.006 * area + rng.normal(0, 0.22, n)
    demand = 2.6e4 + 320 * f_price - 900 * f_scale + rng.normal(0, 2600, n)
    # 斤/亩 × 亩 × 元/斤 = 元；元/亩 × 亩 = 元。两项同量纲才能相减，再折成万元。
    profit = (yield_ * area * price - cost * area) / 1e4
    bean = np.clip(0.30 - 0.0022 * area + rng.normal(0, 0.05, n), 0, 1)

    X = np.column_stack([area, yield_, price, cost, demand, profit, bean])
    # 单位跟着变量走，**不要在轴标签里硬写**——最强那一对是算出来的，
    # 换一份数据就换一对变量，硬写的单位不会报错，只会写错。
    labels = ["种植面积", "亩产量", "销售价格", "种植成本",
              "预期销量", "净利润", "豆类占比"]
    units = ["亩", "斤/亩", "元/斤", "元/亩", "斤", "万元", "无量纲"]
    C = _spearman(X)

    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(9.4, 4.2), gridspec_kw={"width_ratios": [1.25, 1]})

    cs.corr_heatmap(ax, C, labels, annot_min=0.45,
                    cbar_label=r"Spearman $\rho$ (无量纲)")
    ax.set_title("(a) 只标 |ρ|≥0.45 的格子；遮上三角（矩阵对称）",
                 loc="left", pad=8, fontsize=cs.BASE_FONT)

    # 挑出下三角里 |ρ| 最大的一对，画散点确认
    tri = np.tril(np.abs(C), k=-1)
    i, j = np.unravel_index(np.argmax(tri), tri.shape)
    ax2.plot(X[:, j], X[:, i], label="观测 (n=%d)" % n,
             **cs.series_kw(0, "scatter", n_series=1,
                            markersize=3.4, alpha=0.55))
    # 单调趋势线用秩回归的等价物：分位数分箱中位数，不做线性假设
    q = np.quantile(X[:, j], np.linspace(0, 1, 9))
    mid, med = [], []
    for a, b in zip(q[:-1], q[1:]):
        m = (X[:, j] >= a) & (X[:, j] <= b)
        if m.sum() >= 5:
            mid.append(np.median(X[m, j]))
            med.append(np.median(X[m, i]))
    ax2.plot(mid, med, color=cs.COLORS[7], lw=1.6, ls="--", marker="",
             zorder=4, label="分箱中位数")
    cs.finish(ax2, xlabel="%s (%s)" % (labels[j], units[j]),
              ylabel="%s (%s)" % (labels[i], units[i]),
              title="(b) ρ=%.2f 这一对：散点确认是单调关系，不是离群点撑出来的"
                    % C[i, j], legend=True)
    cs.add_units_note(fig, "范例数据为合成（因子模型，保证矩阵半正定）；"
                           "相关矩阵必须用发散色且把 0 钉在中点")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "10_通用_相关矩阵热力图.png"))]


# ============================================================ 通用：描述统计
def fig_descriptive() -> list[dict]:
    """描述统计三联：分布 + 分组箱线 + 逐列缺失概览。

    这三张对应 Stage 2 Step 4 的产出。**先看清楚数据长什么样，再决定动不动它**
    ——而"动不动"的判据在 `题型与算法对照.md` §四第一步：常规统计预处理
    （去重/插补/按分位删异常值）默认不做，领域方法内在要求的质控要做并写依据。

    (c) 那张尤其值得画进论文的"数据说明"一节：它把缺失结构摊开给评委看，
    比一句"数据存在少量缺失"有说服力，而且**画出来才会发现缺失不是随机的**
    （这里"检测日期"整段缺失和"孕周"的缺失是同一批行）。
    """
    rng = np.random.default_rng(925)
    n = 1081
    # 右偏的浓度分布：不做对数变换就直接上正态假设的检验会失效
    conc = rng.lognormal(mean=1.85, sigma=0.42, size=n)
    grp_id = rng.integers(0, 4, size=n)
    shift = np.array([-0.9, 0.0, 0.7, 1.4])
    grouped = conc + shift[grp_id]

    fig, axes = plt.subplots(1, 3, figsize=(10.4, 3.5),
                             gridspec_kw={"width_ratios": [1, 1, 1.05]})

    # ---- (a) 分布：直方 + 中位数/均值。**右偏时这两条会分开，一眼看出来**
    ax = axes[0]
    ax.hist(conc, bins=36, **cs.series_kw(0, "fill", alpha=0.75))
    for v, name, slot in ((np.median(conc), "中位数", 7), (conc.mean(), "均值", 3)):
        ax.axvline(v, color=cs.COLORS[slot], lw=1.4,
                   ls="--" if name == "均值" else "-",
                   label="%s %.2f" % (name, v), zorder=4)
    cs.finish(ax, xlabel="Y 染色体浓度 (%)", ylabel="频数 (次)",
              title="(a) 右偏：均值被右尾拉走，报中位数", legend=True)

    # ---- (b) 分组箱线：Stage 6 的标准交付形式之一
    ax = axes[1]
    data = [grouped[grp_id == g] for g in range(4)]
    bp = ax.boxplot(data, widths=0.58, patch_artist=True, showfliers=True,
                    medianprops=dict(color=cs.INK, linewidth=1.3),
                    whiskerprops=dict(color=cs.AXIS, linewidth=0.9),
                    capprops=dict(color=cs.AXIS, linewidth=0.9),
                    flierprops=dict(marker="o", markersize=2.4,
                                    markerfacecolor=cs.MUTED,
                                    markeredgecolor="none", alpha=0.5))
    for i, patch in enumerate(bp["boxes"]):
        kw = cs.series_kw(i, "bar")
        patch.set(facecolor=kw["facecolor"], hatch=kw["hatch"],
                  edgecolor=cs.SURFACE, linewidth=0.0)
    ax.set_xticks(range(1, 5), ["<28", "28–32", "32–36", "≥36"])
    ax.axhline(4, color=cs.COLORS[7], lw=1.1, ls="--", zorder=1)
    cs.annotate_value(ax, 4.1, 4, "达标线 4%", dy=5, color=cs.COLORS[7])
    cs.finish(ax, xlabel="BMI 分组 (无量纲)", ylabel="Y 染色体浓度 (%)",
              title="(b) 离群点保留并标出，不要先删掉再画", legend=False)

    # ---- (c) 逐列缺失概览。**缺失率排序 + 标出共现，比一句"少量缺失"有用**
    ax = axes[2]
    cols = ["检测孕周", "孕妇BMI", "原始读段数", "GC 含量",
            "唯一比对读段数", "检测日期", "末次月经"]
    miss = np.array([0.002, 0.000, 0.000, 0.000, 0.006, 0.171, 0.171])
    order = np.argsort(miss)
    ax.barh(np.arange(len(cols)), miss[order] * 100,
            **cs.series_kw(0, "bar", height=0.62))
    ax.set_yticks(range(len(cols)), [cols[k] for k in order])
    for y, v in enumerate(miss[order]):
        if v > 0:
            ax.text(v * 100 + 0.35, y, "%.1f%%" % (v * 100), va="center",
                    fontsize=cs.BASE_FONT - 2, color=cs.INK_2)
    ax.set_xlim(0, max(miss) * 100 * 1.35)
    cs.finish(ax, xlabel="缺失率 (%)", ylabel="附件列 (按缺失率排序)",
              title="(c) 后两列缺失率相同 → 同一批行，缺失非随机",
              legend=False)

    cs.add_units_note(fig, "范例数据为合成；口径照 2025C 附件的列结构。"
                           "看清分布与缺失结构之后再决定动不动数据——"
                           "判据见 题型与算法对照.md §四第一步")
    fig.tight_layout()
    return [cs.save(fig, os.path.join(OUT, "11_通用_描述统计三联.png"))]


BUILDERS = {
    "机理": fig_mechanism,
    "反演": fig_inverse,
    "数据": fig_data_stats,
    "决策": fig_decision,
    "成分": fig_compositional,
    "灵敏度": fig_sensitivity,
    "权衡": fig_tradeoff,
    "示意图": fig_schematic,
    "流程图": fig_flow,
    "相关矩阵": fig_corr,
    "描述统计": fig_descriptive,
}


def main() -> int:
    _console.init()
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
                print(_console.sym("  ✓ %s  %.1f×%.1f in  灰度校样 %s"
                                   % (os.path.basename(info["path"]),
                                      *info["size_inch"],
                                      "有" if info["gray"] else "无(缺 Pillow)")))
        except MissingAttachment as exc:
            skipped.append(key)
            print("  – %s 跳过：%s" % (key, exc))
        except Exception as exc:                       # noqa: BLE001
            print(_console.sym("  ✗ %s 失败：%s: %s"
                               % (key, type(exc).__name__, exc)))
    print("\n共 %d 张，输出在 %s" % (len(made), OUT))
    if skipped:
        print("跳过 %d 张（%s）：这几张用真题附件画，设 CUMCM_REPO 指向资料库根目录后重跑。"
              % (len(skipped), "/".join(skipped)))
    print("翻一遍 _gray.png 可以看打印稿的样子（成本近零的保险，不是硬门槛）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
