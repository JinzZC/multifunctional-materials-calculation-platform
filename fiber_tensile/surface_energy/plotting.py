"""Zisman 图构建：cosθ 对 γ_L 散点 + 线性回归外推临界表面张力。

UI 画布与报告导出共用；matplotlib 仅在调用时加载。
"""

import math

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from ..config import apply_matplotlib_chinese

# 模块导入即配置中文字体（幂等）
apply_matplotlib_chinese()


def build_zisman_figure(points, gamma_c: float, r2: float,
                        fig: Figure | None = None,
                        title: str = "Zisman 图") -> Figure:
    """points: LiquidPoint 列表；fig 传入时清空重绘（嵌入 Qt 画布用）。"""
    if fig is None:
        fig, ax = plt.subplots(figsize=(7.0, 5.0))
    else:
        fig.clf()
        ax = fig.add_subplot(111)

    x = np.array([p.gamma_total for p in points])
    y = np.array([math.cos(math.radians(p.angle_deg)) for p in points])
    ax.scatter(x, y, s=30, zorder=3, label="实测数据")
    slope, intercept = np.polyfit(x, y, 1)
    xline = np.linspace(0.0, x.max() * 1.1, 50)
    ax.plot(xline, slope * xline + intercept, linewidth=1.5, zorder=2,
            label="线性拟合")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel(r"$\gamma_L$ (mN/m)")
    ax.set_ylabel(r"$\cos\theta$")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(fontsize=9)

    sign, abs_b = ("+", intercept) if intercept >= 0 else ("-", abs(intercept))
    note = (f"拟合方程：$\\cos\\theta = {slope:.4f}\\,\\gamma_L {sign} {abs_b:.4f}$\n"
            f"临界表面张力 $\\gamma_c$ = {gamma_c:.2f} mN/m\n"
            f"拟合优度 R² = {r2:.4f}")
    ax.text(0.97, 0.03, note, transform=ax.transAxes, fontsize=9.5,
            ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                      edgecolor="#9AA5B1", alpha=0.92))
    fig.tight_layout()
    return fig
