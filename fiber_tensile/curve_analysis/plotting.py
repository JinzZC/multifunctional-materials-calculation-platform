"""单丝拉伸曲线图：原始曲线 + 线性区拟合线 + 平台校正点 + 断裂点标注。"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from ..config import apply_matplotlib_chinese

apply_matplotlib_chinese()


def build_curve_figure(disp_mm, force_n, result,
                       fig: Figure | None = None,
                       title: str = "单丝拉伸曲线分析") -> Figure:
    """result: CurveResult；fig 传入时清空重绘（嵌入 Qt 画布用）。"""
    if fig is None:
        fig, ax = plt.subplots(figsize=(7.0, 5.0))
    else:
        fig.clf()
        ax = fig.add_subplot(111)

    x = np.asarray(disp_mm, dtype=float)
    y = np.asarray(force_n, dtype=float)
    ax.plot(x, y, linewidth=1.4, label="实测曲线")
    # 拟合直线（线性区扩展到 [x0, 断裂点]）
    xline = np.linspace(result.toe_disp_mm, x[result.break_idx], 50)
    ax.plot(xline, result.fit_k * xline + result.fit_b,
            linewidth=1.5, linestyle="--", label="线性区拟合")
    ax.axvline(result.toe_disp_mm, color="green", linestyle=":",
               linewidth=1.2, label=f"平台校正点（位移₀={result.toe_disp_mm:.3f} mm）")
    ax.scatter([x[result.break_idx]], [y[result.break_idx]], s=40,
               color="red", zorder=5, label="断裂点")
    ax.set_xlabel("位移 (mm)")
    ax.set_ylabel("力 (N)")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(fontsize=9)

    note = (f"弹性模量 E = {result.e_gpa:.2f} GPa\n"
            f"断裂强度 $\\sigma_b$ = {result.strength_mpa:.2f} MPa\n"
            f"断裂伸长率（校正后）$\\varepsilon_b$ = {result.elongation_pct:.3f}%\n"
            f"平台段应变（已校正）$\\varepsilon_0$ = {result.toe_eps_pct:.3f}%\n"
            f"拟合优度 R² = {result.r2:.4f}")
    ax.text(0.97, 0.03, note, transform=ax.transAxes, fontsize=9.5,
            ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                      edgecolor="#9AA5B1", alpha=0.92))
    fig.tight_layout()
    return fig
