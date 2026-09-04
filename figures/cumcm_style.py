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
