# -*- coding: utf-8 -*-
"""竞赛论文图表的统一样式。所有绘图脚本第一件事：`from plot_setup import *; setup_mpl()`。

为什么要统一
------------
`competitions/cumcm/winning_patterns.md` §2.5 把"结果呈现"列为**失分占比最高**的一节，
并要求「图要能读：坐标轴含义、单位、图例齐全；对比类结果画在同一张图上」。
但每个脚本各写各的 `rcParams`，结果是同一篇论文里字号、配色、网格深浅都不一样。

三条硬约束
----------
1. **中文不能出豆腐块**。matplotlib 默认字体没有中文字形，缺字只会打一行 warning，
   图照出，评委看到的是一排方块。这里给了回退链并在找不到时**显式报错**。
2. **黑白打印仍要能区分**。评委可能拿到黑白复印件。所以颜色之外必须有第二重编码：
   marker 形状 + 线型。只靠颜色区分的图，转灰度后就废了。
3. **配色不是随便挑的**。下面的定类色板通过了六项校验（亮度带、彩度下限、
   色觉障碍相邻对可分辨、常色视觉可分辨、与背景对比度），色板与校验脚本同源。

用法
----
    from plot_setup import setup_mpl, tidy, PAL, MARK, LS
    setup_mpl()
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    for i, (label, series) in enumerate(groups):
        ax.plot(x, series, color=PAL[i], ls=LS[i], marker=MARK[i], markevery=6, label=label)
    ax.set_xlabel('孕周'); ax.set_ylabel('Y 染色体浓度')   # 轴一定要有含义和单位
    ax.legend(); tidy(ax)
    fig.savefig('figures/fig1_xxx.png')                  # 文件名带编号和含义
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt

# ---- 定类色板：蓝 / 橙 / 绿 / 紫 / 金。超过 5 类就不要再加颜色了，
# ---- 改用分面（small multiples）或把尾部合并成"其他"。
PAL = ['#2f6f9f', '#d2691e', '#3f8f5f', '#9a4fa8', '#b8860b']
# ---- 二级编码：黑白打印与色觉障碍下靠这两组区分
MARK = ['o', 's', '^', 'D', 'v']
LS = ['-', '--', '-.', ':', (0, (3, 1, 1, 1))]
# ---- 文字与线条用中性墨色，不要用系列色（系列色只归马克所有）
INK, INK2, MUTED = '#1a1a1a', '#4a4a4a', '#8a8a8a'
SURFACE = '#fcfcfb'

# 顺序型（表示量级大小）用**单一色相由浅到深**，不要用彩虹色
SEQ_CMAP = 'Blues'
# 发散型（表示正负两极）用两个色相 + 中性灰中点
DIV_CMAP = 'RdBu_r'

_CJK_CANDIDATES = ('SimHei', 'Microsoft YaHei', 'DengXian', 'SimSun',
                   'Noto Sans CJK SC', 'Source Han Sans SC', 'WenQuanYi Zen Hei')


def available_cjk_fonts() -> list[str]:
    """本机实际装了的中文字体，按 _CJK_CANDIDATES 的优先级排序。"""
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    return [name for name in _CJK_CANDIDATES if name in installed]


def setup_mpl(base_size: float = 10.5, dpi: int = 160, strict_cjk: bool = True) -> None:
    """设置全局样式。

    strict_cjk=True 时，本机一个中文字体都没有就直接抛 RuntimeError——
    与其出一张全是方块的图，不如当场失败。真的要出英文图时传 False。
    """
    fonts = available_cjk_fonts()
    if not fonts:
        if strict_cjk:
            raise RuntimeError(
                '找不到任何中文字体，图里的中文会变成方块。\n'
                'Windows 通常自带 SimHei/Microsoft YaHei；\n'
                'Linux 可 apt install fonts-wqy-zenhei 或装思源黑体；\n'
                '确实只出英文图时用 setup_mpl(strict_cjk=False)。'
            )
        fonts = []

    plt.rcParams.update({
        'font.sans-serif': fonts + ['DejaVu Sans'],
        'axes.unicode_minus': False,      # 不然负号会显示成方块
        'font.size': base_size,
        'figure.dpi': dpi,
        'savefig.dpi': 300,               # 论文里图要经得起放大
        'savefig.bbox': 'tight',
        'figure.facecolor': SURFACE,
        'axes.facecolor': SURFACE,
        'axes.edgecolor': MUTED,
        'axes.linewidth': 0.8,
        'axes.labelcolor': INK,
        'axes.titlesize': base_size + 1.5,
        # 不要设 bold：SimHei 没有粗体字面，matplotlib 每次 savefig 都会打
        # "Failed to find font weight bold" 的 warning。靠字号区分标题就够了。
        'axes.titleweight': 'normal',
        'axes.prop_cycle': matplotlib.cycler(color=PAL),
        'xtick.color': INK2, 'ytick.color': INK2,
        'xtick.labelsize': base_size - 1, 'ytick.labelsize': base_size - 1,
        'grid.color': '#dedede', 'grid.linewidth': 0.6,
        'legend.frameon': False, 'legend.fontsize': base_size - 1,
        'lines.linewidth': 2.0, 'lines.markersize': 5,
    })


def tidy(ax, grid: str | None = 'y'):
    """去掉上/右边框，网格压到数据下面。网格是参考线，不该抢视线。

    grid: 'y' | 'x' | 'both' | None
    """
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    if grid:
        ax.grid(axis=grid, zorder=0)
        ax.set_axisbelow(True)
    return ax


def style(i: int) -> dict:
    """第 i 条系列的完整样式（颜色 + 线型 + 标记）。超出 5 条会循环，
    但那时应该先考虑分面而不是继续叠系列。"""
    k = i % len(PAL)
    return {'color': PAL[k], 'ls': LS[k], 'marker': MARK[k]}


if __name__ == '__main__':
    # 自检：出一张含中文标题、图例、负号的图，用于确认本机字体链可用
    import numpy as np
    setup_mpl()
    x = np.linspace(0, 10, 60)
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    for i, k in enumerate([1, 2, 3]):
        ax.plot(x, np.sin(x * k) - i * 0.5, markevery=8,
                label=f'第 {i + 1} 组（k={k}）', **style(i))
    ax.set_xlabel('自变量 x（单位）'); ax.set_ylabel('因变量 y（单位）')
    ax.set_title('中文标题自检：坐标轴负号与图例都应正常显示')
    ax.legend(); tidy(ax, 'both')
    out = 'plot_setup_selfcheck.png'
    fig.savefig(out)
    print(f'已生成 {out}；确认：中文无方块、负号正常、转灰度后三条线仍可区分。')
    print('本机可用中文字体：', available_cjk_fonts())
