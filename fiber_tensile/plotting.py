"""Weibull 拟合图构建（UI 画布与 Excel/PDF 报告共用）。

坐标变换：横轴 ln(σ/GPa)，纵轴 ln(−ln(1−F̂))，散点 + 拟合直线，
支持多批次曲线叠加对比。
"""

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from .config import apply_matplotlib_chinese
from .core.weibull import (
    rank_method_label, weibull_in_gpa, weibull_intercept, weibull_line_data,
)

# 模块导入即配置中文字体（幂等），保证任何调用方（UI/报告导出/测试）生成的图都正确渲染中文
apply_matplotlib_chinese()


def fit_equation_text(w) -> str:
    """拟合直线方程（mathtext 格式）：y = m·x + a，其中 a = −m·ln(σ₀)。"""
    a = weibull_intercept(w)
    sign, abs_a = ("+", a) if a >= 0 else ("-", abs(a))
    return f"$y = {w.m:.4f}x {sign} {abs_a:.4f}$"


def build_weibull_figure(series, labels=None, title="Weibull 分布拟合图",
                         sigma0_unit: str = "MPa", fig: Figure | None = None) -> Figure:
    """根据一个或多个 WeibullResult 构建拟合图。

    series: WeibullResult 列表（单个批次或对比多个批次）
    labels: 图例名列表，缺省为「批次 N」
    sigma0_unit: 未标记结果的原始强度单位；绘图统一换算为 GPa
    fig: 传入已有 Figure 时清空后在其上绘图（用于嵌入 Qt 画布），缺省新建

    图右下角标注拟合直线方程；多批次对比时逐条列出。
    """
    series = [weibull_in_gpa(w, sigma0_unit or "MPa") for w in series]
    if fig is None:
        fig, ax = plt.subplots(figsize=(7.5, 5.5))
    else:
        fig.clf()
        ax = fig.add_subplot(111)
    if labels is None:
        labels = [f"批次 {i + 1}" for i in range(len(series))]
    for w, label in zip(series, labels):
        ax.scatter(w.x, w.y, s=26, zorder=3, label=(
            f"{label}（m={w.m:.2f}，$\\sigma_0$={w.sigma0:.4f} GPa，R²={w.r2:.3f}）"))
        # 拟合直线：y = m·x − m·ln(σ₀)
        xline, yline = weibull_line_data(w)
        ax.plot(xline, yline, linewidth=1.5, zorder=2)
    # 三参数系列采用扣除各自位置参数后的强度。
    has_gamma = any(w.gamma > 0 for w in series)
    base = (r"$\ln[(\sigma-\gamma)/\mathrm{GPa}]$" if has_gamma
            else r"$\ln(\sigma/\mathrm{GPa})$")
    ax.set_xlabel(base)
    ax.set_ylabel(r"$\ln(-\ln(1-\hat{F}))$")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(fontsize=9)
    # 拟合直线方程标注（右下角，随系列数自动多行）
    if len(series) == 1:
        eq_lines = [f"拟合直线方程：{fit_equation_text(series[0])}"]
        eq_lines.append(f"排序概率：{rank_method_label(series[0].rank_method)}")
    else:
        eq_lines = ["拟合直线方程"] + [
            f"{label}：{fit_equation_text(w)}" for w, label in zip(series, labels)]
        rank_labels = {rank_method_label(w.rank_method) for w in series}
        if len(rank_labels) == 1:
            eq_lines.append(f"排序概率：{rank_labels.pop()}")
        else:
            eq_lines.append("排序概率：各批次方法不同")
    eq_lines.append(f"($x = {base[1:-1]}$，$y = \\ln(-\\ln(1-\\hat{{F}}))$)")
    ax.text(0.98, 0.03, "\n".join(eq_lines), transform=ax.transAxes,
            fontsize=9.5, ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                      edgecolor="#9AA5B1", alpha=0.92))
    fig.tight_layout()
    return fig
