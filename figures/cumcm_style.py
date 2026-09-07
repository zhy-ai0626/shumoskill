# -*- coding: utf-8 -*-
"""CUMCM 论文图表统一样式。

为什么要有这个文件
------------------
组委会点名的失分项里，**结果呈现占比最高**：2022A 讲评「评阅中发现的问题」9 条里
5 条与建模无关，全是"计算方法不清楚 / 结果不完整 / 没有很好地呈现结果 /
没有对结果进行分析 / 结果文件格式不对"。一等奖论文的图数中位是 **20 张**。
图不是装饰，是主要得分位。

**评委会打印。** 这一条决定了全部配色规则。实测这套配色在灰度下的相对亮度：

    violet 0.073 · green 0.162 · blue 0.188 · red 0.216 · orange 0.278
    aqua 0.323 · magenta 0.340 · yellow 0.435

最难分的几对：aqua↔magenta ΔL=0.017、blue↔green 0.025、blue↔red 0.028
——**打印出来基本同色**。所以本模块把"第二通道"做成**默认**而不是选项：
取第 i 个系列时，颜色、填充网格、线型、标记是**捆在一起**给的，
你没法只拿颜色。想验证打印效果，`save()` 会顺手出一份灰度校样。

配色来源
--------
基础色板取自经验证的分类色板（八槽固定顺序，不是随手挑的）：
相邻对最差 CVD ΔE 9.1、正常视觉 ΔE 19.6，均过硬门槛。
散点/气泡这类**任意两两都会同时出现**的图，只有前三槽能全对通过——
所以 `series_kw(..., kind="scatter")` 超过 3 个系列会直接报错，
逼你去做分面或合并成"其他"，而不是继续加颜色。

用法
----
    import cumcm_style as cs
    cs.use()                                   # 设中文字体与 rcParams
    fig, ax = plt.subplots(figsize=cs.SIZE_1COL)
    for i, (name, y) in enumerate(series):
        ax.plot(x, y, label=name, **cs.series_kw(i, "line"))
    cs.finish(ax, xlabel="孕周 (周)", ylabel="Y 染色体浓度 (%)")
    cs.save(fig, "figures/fig3_concentration.png")   # 同时出灰度校样
"""

from __future__ import annotations

import os
import sys

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgb

# ---------------------------------------------------------------- 尺寸
# 论文里图按 \textwidth(约 16 cm) 或半栏插入。宽度定死、字号定死，
# 才能保证"最终 PDF 尺寸下仍然可读"——这是 Stage 9 的人工检查项之一。
SIZE_1COL = (6.4, 4.0)      # 整幅宽，默认
SIZE_WIDE = (9.6, 3.6)      # 跨页宽/时间序列
SIZE_HALF = (3.6, 3.0)      # 并排两图
SIZE_SQUARE = (5.0, 5.0)    # 布局图/散点/三元图

BASE_FONT = 9.0             # 图按原尺寸插入时约等于正文小五号

# ---------------------------------------------------------------- 墨色
INK = "#0b0b0b"             # 主文字
INK_2 = "#52514e"           # 次要文字
MUTED = "#898781"           # 轴标签
GRID = "#e1e0d9"            # 网格（发丝级）
AXIS = "#c3c2b7"            # 轴线/基线
SURFACE = "#fcfcfb"         # 画布

# ---------------------------------------------------------------- 系列
# 颜色 + 填充网格 + 线型 + 标记 捆在一起。灰度打印时颜色会塌缩，
# 后三样才是真正区分系列的东西。
_SLOTS = (
    ("blue",    "#2a78d6", "//",   "-",   "o"),
    ("orange",  "#eb6834", "\\\\", "--",  "s"),
    ("aqua",    "#1baf7a", "xx",   "-.",  "^"),
    ("yellow",  "#eda100", "..",   ":",   "D"),
    ("magenta", "#e87ba4", "++",   (0, (3, 1, 1, 1)), "v"),
    ("green",   "#008300", "||",   (0, (5, 2)), "P"),
    ("violet",  "#4a3aa7", "--",   (0, (1, 1)), "X"),
    ("red",     "#e34948", "OO",   (0, (7, 2, 1, 2)), "*"),
)
SERIES_NAMES = [s[0] for s in _SLOTS]
COLORS = [s[1] for s in _SLOTS]

# 散点/气泡/小多图这类"任意两两同框"的形式，只有前三槽全对通过。
MAX_ALLPAIRS_SERIES = 3

# 顺序色（连续量：热图、场分布）。单一色相由浅到深，绝不用彩虹。
_SEQ_STEPS = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
              "#2a78d6", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("cumcm_seq", _SEQ_STEPS)
# 离散有序（分档、等级）：最浅一档也要能从纸面上看出来，故从第 3 步起
SEQ_ORDINAL = _SEQ_STEPS[2:]

# 发散色（有正负、有中性零点：残差、偏差、增减）。中点是灰，不是某个色相。
DIVERGING = LinearSegmentedColormap.from_list(
    "cumcm_div", ["#0d366b", "#2a78d6", "#9ec5f4", "#f0efec",
                  "#f4a6a5", "#e34948", "#8c1f1f"])

# 状态色（好/注意/严重/危急）。**专用**，不许当第 9 个系列使。
STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}

_CN_FONTS = ("SimHei", "Microsoft YaHei", "SimSun", "Noto Sans CJK SC",
             "Source Han Sans SC", "WenQuanYi Zen Hei")


def available_cn_font() -> str | None:
    """返回本机可用的第一个中文字体名；一个都没有返回 None。"""
    from matplotlib import font_manager

    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in _CN_FONTS:
        if name in installed:
            return name
    return None


def use(font: str | None = None) -> str:
    """设置全局样式。返回实际用上的中文字体名。

    中文缺字不会报错，只会把每个汉字画成方框（还会刷一堆 findfont 警告），
    所以这里显式检查并在找不到时抛异常——图里全是方框比编译失败更难发现。
    """
    picked = font or available_cn_font()
    if picked is None:
        raise RuntimeError(
            "找不到中文字体，图里的中文会变成方框。Windows 装 SimHei/微软雅黑；"
            "Linux 装 fonts-noto-cjk 或思源黑体，然后 "
            "`matplotlib.font_manager._load_fontmanager(try_read_cache=False)`")
    matplotlib.rcParams.update({
        "font.sans-serif": [picked] + list(_CN_FONTS),
        "font.family": "sans-serif",
        "axes.unicode_minus": False,          # 否则负号显示成方框
        "font.size": BASE_FONT,
        "axes.titlesize": BASE_FONT + 1,
        "axes.labelsize": BASE_FONT,
        "xtick.labelsize": BASE_FONT - 1,
        "ytick.labelsize": BASE_FONT - 1,
        "legend.fontsize": BASE_FONT - 1,
        "figure.dpi": 160,
        "savefig.dpi": 300,                   # 论文里放大看不糊
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        # 轴与网格要"退到后面"，不能和数据抢
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,               # 网格在数据下面
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "lines.linewidth": 1.8,
        "lines.markersize": 4.5,
        "lines.markeredgewidth": 0.0,
        "hatch.linewidth": 0.9,
        "errorbar.capsize": 2.5,
    })
    return picked


def series_kw(i: int, kind: str = "line", *, n_series: int | None = None,
              n_points: int | None = None, **overrides) -> dict:
    """第 i 个系列的绘图参数。**颜色不单独给**，一定连着第二通道。

    kind: line | bar | scatter | fill
    n_series: 传了就检查系列数上限（scatter 类超过 3 个会报错）。
    n_points: 折线的数据点数。给了就自动把标记稀释到约 12 个——
        900 个点上打 900 个标记，标记就不再是"区分系列"的通道，而是噪声。
    overrides: 任何 matplotlib 关键字，覆盖默认值（如 `alpha=0.6`）。
    """
    name, color, hatch, ls, marker = _SLOTS[i % len(_SLOTS)]
    if i >= len(_SLOTS):
        raise ValueError(
            "第 %d 个系列超出 8 槽。**不要循环复用颜色**——"
            "两个系列同色，读者只能靠位置猜。合并成『其他』、改用分面(小多图)，"
            "或者换一种编码（比如把其中一维放到 x 轴上）。" % (i + 1))
    if kind == "scatter" and (n_series or 0) > MAX_ALLPAIRS_SERIES:
        raise ValueError(
            "散点/气泡图里任意两个系列都会同时出现，这套色板只有前 %d 槽能全对通过"
            "（第 4 槽起黄色与橙色同框，正常视觉 ΔE 13.7 已低于 15 的地板）。"
            "现在有 %d 个系列：请分面、合并，或改用小多图。"
            % (MAX_ALLPAIRS_SERIES, n_series))

    if kind == "line":
        kw = {"color": color, "linestyle": ls, "marker": marker, "zorder": 3}
        if n_points:
            # 每条线约 12 个标记，各系列错开起点，避免标记在同一 x 上叠成一团
            step = max(1, int(n_points // 12))
            kw["markevery"] = (int(i * step / max(1, len(_SLOTS))) % step, step)
    elif kind == "bar":
        # **hatch 线用 edgecolor 画**。第一版把 edgecolor 设成和 facecolor 同色，
        # 网格线等于用填充色画在填充上——彩色稿看不出，**灰度稿里整根条糊成一块**。
        # 用画布色画网格，深填充上透出浅线条，彩色和灰度都成立；
        # 同时它兼作相邻色块之间的那道分隔缝。
        kw = {"facecolor": color, "hatch": hatch, "edgecolor": SURFACE,
              "linewidth": 0.0, "zorder": 3}
    elif kind == "fill":
        kw = {"facecolor": color, "hatch": hatch, "edgecolor": SURFACE,
              "alpha": 0.85, "linewidth": 0.0, "zorder": 2}
    elif kind == "scatter":
        kw = {"color": color, "marker": marker, "linestyle": "none", "zorder": 3}
    else:
        raise ValueError("kind 只能是 line / bar / scatter / fill，收到 %r" % kind)
    kw.update(overrides)
    return kw


def finish(ax, *, xlabel: str = "", ylabel: str = "", title: str = "",
           legend: bool = True, legend_loc: str = "best") -> None:
    """收尾：轴标签、图例、网格。

    **坐标轴含义与单位齐全是 Stage 9 的人工检查项**，所以这里强制要求
    xlabel/ylabel 非空——2022A 讲评点名的"没有很好地呈现结果"，
    很大一部分就是轴上没写单位。
    """
    if not xlabel or not ylabel:
        raise ValueError(
            "xlabel 与 ylabel 都必须写，且**带单位**（如『距离 (m)』『功率 (MW)』）。"
            "无量纲量写『(无量纲)』或『(比例)』。这是评委逐张看的东西。")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, loc="left", pad=8)
    handles, labels = ax.get_legend_handles_labels()
    if legend and len(labels) >= 2:
        ax.legend(loc=legend_loc, handlelength=2.6, borderaxespad=0.4)
    elif legend and len(labels) == 1:
        # 单系列不要图例框，标题里说清是什么就够
        leg = ax.get_legend()
        if leg is not None:
            leg.remove()


# ================================================================ 流程图
# 为什么这几个 helper 值得进样式模块：**52% 的一等奖论文有流程图/框架图**
# （44 篇官方展示实测，平均 2.3 张，通常"总体一张 + 每问一张"），
# `paper_skeleton.md` 有 `## 2.1 总体技术路线` 这个章节，`phrase_bank.md`
# 有"算法流程图见图 N"这句式——需求、章节、句式都在，**却没有画法**。
# 手搓 Rectangle + annotate 每次都要重新调框宽、箭头缩进和文字居中，
# 而且最容易犯的两个错（箭头扎进框里、层级靠颜色而非位置区分）没人拦。

# 流程图的框按**角色**上色，不按系列上色——流程图里没有"系列"这个东西。
# 一律用浅底 + 墨字：框里要塞中文，深底会让字不可读，灰度稿更糟。
FLOW_TINTS = {
    "input":  "#f3f2ee",     # 数据/题面输入
    "step":   "#e3eefb",     # 处理步骤（默认）
    "model":  "#e6f3ec",     # 建模/求解
    "output": "#fdf3d8",     # 结论/交付
    "check":  "#faeceb",     # 校验/回检（唯一带暖色的一档，视觉上跳出来）
}


class FlowBox:
    """流程图里的一个框。**用四边锚点连线，不要用中心点。**

    从中心画到中心，箭头会扎进框里压住文字——这是手搓流程图最常见的翻车点。
    `b.s`（下边中点）→ `b2.n`（上边中点）这样连，箭头永远停在框外。
    """

    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: float, y: float, w: float, h: float):
        self.x, self.y, self.w, self.h = x, y, w, h

    # 四边的**分数锚点**。多条边汇进同一个框时，全都指向 `n`（上边中点）
    # 会让三个箭头尖叠成一团黑；`top(0.15) / top(0.5) / top(0.85)` 摊开就干净了。
    def top(self, f: float = 0.5) -> tuple[float, float]:
        return self.x + self.w * f, self.y + self.h

    def bottom(self, f: float = 0.5) -> tuple[float, float]:
        return self.x + self.w * f, self.y

    def left(self, f: float = 0.5) -> tuple[float, float]:
        return self.x, self.y + self.h * f

    def right(self, f: float = 0.5) -> tuple[float, float]:
        return self.x + self.w, self.y + self.h * f

    @property
    def c(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def n(self) -> tuple[float, float]:
        return self.top()

    @property
    def s(self) -> tuple[float, float]:
        return self.bottom()

    @property
    def e(self) -> tuple[float, float]:
        return self.right()

    @property
    def w_(self) -> tuple[float, float]:
        """左边中点。名字带下划线是因为 `w` 已经被框宽占了。"""
        return self.left()


def flow_canvas(figsize=(6.6, 5.2), xlim=(0.0, 100.0), ylim=(0.0, 100.0)):
    """流程图专用画布：关掉坐标轴与网格，坐标系默认 0–100 便于摆框。

    必须显式关网格——`use()` 把 `axes.grid` 设成了 True（数据图要网格），
    流程图上留着就是一层横条纹。
    """
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_axis_off()
    ax.grid(False)
    return fig, ax


def flow_box(ax, x: float, y: float, w: float, h: float, text: str, *,
             tint: str = "step", fontsize: float | None = None,
             weight: str = "normal", **kw) -> FlowBox:
    """画一个流程框，返回 `FlowBox`（带 n/s/e/w_/c 五个锚点）。

    `x, y` 是**左下角**，与 matplotlib 的 Rectangle 一致。
    `tint` 取 `FLOW_TINTS` 的键；传了未知键直接报错，免得静默退化成白框。
    """
    if tint not in FLOW_TINTS:
        raise ValueError("tint 只能是 %s，收到 %r"
                         % ("/".join(FLOW_TINTS), tint))
    ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=FLOW_TINTS[tint],
                               edgecolor=AXIS, linewidth=0.8,
                               zorder=2, **kw))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize or (BASE_FONT - 0.5), color=INK,
            weight=weight, linespacing=1.45, zorder=4)
    return FlowBox(x, y, w, h)


def flow_arrow(ax, src, dst, *, text: str = "", rad: float = 0.0,
               angle: tuple[float, float] | None = None,
               dashed: bool = False, pad: float = 1.2,
               text_dx: float = 0.0, text_dy: float = 0.0) -> None:
    """从 `src` 锚点连到 `dst` 锚点。

    `angle=(θ_src, θ_dst)` 画**直角折线**：θ_src 是离开 src 时的方向、
    θ_dst 是抵达 dst 时的方向（度，0=向右，90=向上，180=向左，-90=向下）。
    最常用的两个：

        angle=(0, 90)     先横着走，再竖着扎进目标的上/下边 —— 主流程换列
        angle=(180, 90)   先向左，再向上 —— 反馈环绕回上游

    两个方向都给成竖直（如 `(-90, 90)`）时两条线平行、没有交点，
    matplotlib 会画出一条奇怪的折线——这是最容易踩的一脚，所以这里直接拦住。

    `rad` 是弧度（不给 `angle` 时用，弧线绕开中间的框）；`dashed=True` 画虚线
    （"可选 / 反馈 / 不一定走"这类边）。`pad` 让箭头两端各缩进一点，
    否则箭头尖会压在框的边线上。

    `text_dx/text_dy` 把边上的文字挪开箭头。**短箭头一定要挪**——
    文字的白底 bbox 会把只有几个单位长的箭头整根盖掉，图上看起来就是"没连线"。
    """
    if angle is not None:
        a, b = angle
        if abs((a - b) % 180.0) < 1e-6:
            raise ValueError(
                "angle=(%g, %g) 两端方向平行，折线没有交点，画出来是条乱线。"
                "横→竖用 (0, 90)，竖→横用 (90, 0)。" % (a, b))
        style = "angle,angleA=%g,angleB=%g,rad=2" % (a, b)
    else:
        style = "arc3,rad=%.3f" % rad
    ax.annotate("", xy=dst, xytext=src, zorder=3,
                arrowprops=dict(arrowstyle="-|>", color=INK_2,
                                linewidth=0.9, shrinkA=pad, shrinkB=pad,
                                linestyle="--" if dashed else "-",
                                connectionstyle=style,
                                mutation_scale=9))
    if text:
        mx = (src[0] + dst[0]) / 2 + text_dx
        my = (src[1] + dst[1]) / 2 + text_dy
        ax.text(mx, my, text, ha="center", va="center",
                fontsize=BASE_FONT - 2, color=INK_2, zorder=5,
                bbox=dict(boxstyle="round,pad=0.16", facecolor=SURFACE,
                          edgecolor="none"))


# ================================================================ 相关矩阵
def _needs_light_text(rgba) -> bool:
    """这个格子的底色够深，深色字就读不出来了。"""
    r, g, b = rgba[:3]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 0.45


def corr_heatmap(ax, matrix, labels, *, annot_min: float = 0.5,
                 mask_upper: bool = True, cbar: bool = True,
                 cbar_label: str = r"相关系数 $\rho$ (无量纲)"):
    r"""相关系数矩阵热力图。**发散色、0 居中、只标够大的格子。**

    为什么单独做成 helper 而不是让人随手 `imshow`：相关矩阵有正有负、
    有中性零点，**必须用发散色且把 0 钉在中点**（`vmin=-1, vmax=1`）。
    随手 `imshow(C)` 会按数据范围自动拉伸——若这份数据的相关系数都在
    0.3~0.9 之间，色标中点就落到 0.6 上，**图上"看起来中性"的格子其实是强正相关**，
    而且不报错。用顺序色（`SEQ`）则把 -0.8 和 +0.1 画成深浅之差，符号信息直接消失。

    `annot_min`: 只有 |ρ| ≥ 这个值的格子才写数字。README 硬规矩第 4 条——
    不要每个格子都标，20×20 全标就是一片糊。设成 0 则全标。
    `mask_upper`: 遮掉上三角。矩阵对称，全画等于把同一信息说两遍，
    还挤掉了字号。对角线一并遮掉（自相关恒为 1，没有信息）。

    **灰度下这张图必然丢符号。** 实测灰度校样：ρ=−0.49 与 ρ=+0.78 都是中深灰，
    色标本身塌成 V 形（两端深、中间浅）。这不是配色没调好，是任何发散色映射到
    单通道明度时的必然结果——正负两侧本来就要在中点两边对称地变深。
    所以这里的数字标注**不只是可读性装饰，它就是这张图的灰度第二通道**：
    `annot_min` 别关掉。矩阵大到标不下（>15 阶）时，正确的做法是先合并/筛指标，
    而不是画一张彩色稿能看、黑白稿丢符号的图。
    """
    M = np.asarray(matrix, dtype=float)
    n = M.shape[0]
    if M.ndim != 2 or M.shape[1] != n:
        raise ValueError("matrix 必须是方阵，收到 %s" % (M.shape,))
    if len(labels) != n:
        raise ValueError("labels 有 %d 个，矩阵是 %d 阶" % (len(labels), n))
    finite = M[np.isfinite(M)]
    if finite.size and (finite.min() < -1.0001 or finite.max() > 1.0001):
        raise ValueError(
            "取值超出 [-1, 1]，这不像相关系数矩阵（实际范围 %.3f~%.3f）。"
            "若要画协方差或其它无界量，请自己指定 vmin/vmax 并说明中点在哪。"
            % (finite.min(), finite.max()))

    shown = M.astype(float).copy()
    if mask_upper:
        shown[np.triu_indices(n, k=0)] = np.nan

    # 被遮的格子留白，不是画成 0。用 with_extremes 而不是 copy()+set_bad——
    # 后者在新版 matplotlib 上是 PendingDeprecationWarning。
    try:
        cmap = DIVERGING.with_extremes(bad=SURFACE)
    except AttributeError:                     # matplotlib < 3.4
        cmap = DIVERGING.copy()
        cmap.set_bad(SURFACE)
    im = ax.imshow(shown, cmap=cmap, vmin=-1.0, vmax=1.0,
                   interpolation="nearest")

    ax.grid(False)                             # rcParams 的 y 网格会横穿整张热图
    ax.set_xticks(range(n), labels, rotation=38, ha="right")
    ax.set_yticks(range(n), labels)
    ax.tick_params(length=0)
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    # 发丝级白缝，让相邻格子分得开（灰度稿上尤其需要）
    ax.set_xticks(np.arange(n + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(n + 1) - 0.5, minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=1.1)
    ax.tick_params(which="minor", length=0)

    if annot_min is not None:
        for i in range(n):
            for j in range(n):
                v = shown[i, j]
                if not np.isfinite(v) or abs(v) < annot_min:
                    continue
                # **这是"文字用墨色"那条规矩的唯一例外**：深底上墨字读不出来。
                # 例外的判据是底色亮度，不是系列身份，所以不违反那条的本意。
                light = _needs_light_text(cmap((v + 1.0) / 2.0))
                ax.text(j, i, ("%.2f" % v).replace("0.", ".", 1)
                        if abs(v) < 1 else "%.0f" % v,
                        ha="center", va="center", fontsize=BASE_FONT - 2,
                        color=SURFACE if light else INK, zorder=3)

    if cbar:
        cb = ax.figure.colorbar(im, ax=ax, fraction=0.040, pad=0.03,
                                ticks=[-1, -0.5, 0, 0.5, 1])
        cb.set_label(cbar_label, fontsize=BASE_FONT - 1, color=INK)
        cb.ax.tick_params(labelsize=BASE_FONT - 2, length=0)
        cb.outline.set_visible(False)
    return im


def grayscale_proof(png_path: str) -> str | None:
    """把已保存的图转成灰度校样，文件名加 `_gray` 后缀。

    评委很可能打印黑白稿。这套色板在灰度下有几对几乎同色
    （aqua↔magenta ΔL=0.017），全靠线型/网格/标记区分——
    **看一眼灰度稿**是唯一能确认第二通道真的起作用的办法。
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    out = os.path.splitext(png_path)[0] + "_gray.png"
    Image.open(png_path).convert("L").save(out)
    return out


def save(fig, path: str, *, proof: bool = True, close: bool = True) -> dict:
    """保存图，并顺手出灰度校样。返回 {path, gray, size_inch, min_font_pt}。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fig.savefig(path)
    info = {"path": path, "size_inch": tuple(round(v, 2) for v in fig.get_size_inches()),
            "gray": grayscale_proof(path) if proof else None}
    if close:
        plt.close(fig)
    return info


def annotate_value(ax, x, y, text, *, dx=0, dy=6, color=None):
    """选择性直接标注。**不要每个点都标**——只标最值、拐点、结论点。

    文字一律用墨色，不用系列色：颜色的活是标身份，标身份的是旁边那个标记。
    """
    ax.annotate(text, (x, y), textcoords="offset points", xytext=(dx, dy),
                ha="center", fontsize=BASE_FONT - 1, color=color or INK)


def add_units_note(fig, text: str) -> None:
    """图下角的说明（数据来源、口径、单位约定）。评委很看重口径。"""
    fig.text(0.005, 0.005, text, fontsize=BASE_FONT - 2, color=MUTED,
             ha="left", va="bottom")
