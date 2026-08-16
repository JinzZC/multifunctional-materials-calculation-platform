"""单丝拉伸曲线分析（纯计算层，仅依赖 numpy）。

方法：
    1. 取力最大点为断裂点；
    2. 在最大力的 [fit_lo, fit_hi] 区间内对 力-位移 做线性拟合：F = k·x + b；
    3. 平台校正（toe correction）：拟合直线与位移轴的交点 x₀ = −b/k 即
       测试起始"只伸长不增力"的平台终点，应变零点平移到 x₀；
    4. 弹性模量 E = k·标距/截面积；断裂强度 σ = F_max/截面积；
       断裂伸长率 ε_b = (断裂位移 − x₀)/标距。

单位：力 N、位移 mm、直径 μm、标距 mm；输出 E(GPa)、σ(MPa)、ε(%)。
"""

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class CurveResult:
    """曲线分析结果。fit: (斜率 k, 截距 b)；toe_disp_mm 为平台段长度。"""

    e_gpa: float
    strength_mpa: float
    elongation_pct: float
    toe_eps_pct: float
    toe_disp_mm: float
    r2: float
    n_points: int
    fit_k: float
    fit_b: float
    break_idx: int
    steps: list = field(default_factory=list)


def _require_positive(value, name):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} 必须为正数")
    return float(value)


def analyze_curve(disp_mm, force_n, diameter_um, gauge_mm,
                  fit_lo: float = 0.2, fit_hi: float = 0.7) -> CurveResult:
    """分析单丝拉伸曲线（含平台校正）。

    disp_mm/force_n：等长序列；fit_lo/fit_hi：线性拟合区间（占最大力的比例）。
    """
    d = _require_positive(diameter_um, "直径")
    gauge = _require_positive(gauge_mm, "标距")
    if not 0.0 < fit_lo < fit_hi <= 1.0:
        raise ValueError("拟合区间比例需满足 0 < 下限 < 上限 ≤ 1")

    x = np.asarray(disp_mm, dtype=float)
    y = np.asarray(force_n, dtype=float)
    if x.shape != y.shape or len(x) < 5:
        raise ValueError("曲线数据点不足（至少 5 个点）")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("曲线数据包含无效数值")
    if np.any(y < 0):
        raise ValueError("力数据不能为负")

    f_max = float(np.max(y))
    if f_max <= 0:
        raise ValueError("最大力必须为正数")
    if float(np.min(y)) == f_max:
        raise ValueError("力数据全部相等，无法分析（无有效线性区）")
    # 取最后一个最大力点作为断裂点（峰值保持段按平台终点计，伸长率更准确）
    break_idx = len(y) - 1 - int(np.argmax(y[::-1]))
    if break_idx == 0:
        raise ValueError("断裂点在曲线起点，数据异常")

    # 线性区：断裂点之前、力在 [fit_lo, fit_hi]×F_max 之间的点
    sel = [i for i in range(break_idx + 1)
           if fit_lo * f_max <= y[i] <= fit_hi * f_max]
    if len(sel) < 3:
        raise ValueError("线性拟合区间内数据点不足（<3 个），请调整拟合区间比例")
    k, b = np.polyfit(x[sel], y[sel], 1)
    if k <= 0:
        raise ValueError("拟合斜率为负，曲线数据异常")
    r2 = float(np.corrcoef(x[sel], y[sel])[0, 1] ** 2)

    # 平台校正：拟合线与位移轴交点（力=0 处）
    x0 = float(-b / k)
    if x0 < 0:
        x0 = 0.0    # 无正向平台
    area = math.pi * (d * 1e-6) ** 2 / 4.0        # m²
    e_pa = k * gauge / area                        # N/mm × mm / m² = N/m²
    e_gpa = e_pa / 1e9
    strength_mpa = f_max / area / 1e6
    elongation_pct = (x[break_idx] - x0) / gauge * 100.0
    if elongation_pct < 0:
        raise ValueError("校正后断裂伸长率为负，请检查数据或拟合区间")
    toe_eps_pct = x0 / gauge * 100.0

    steps = [
        f"计算过程（单丝拉伸曲线分析，共 {len(x)} 个数据点）",
        f"① 断裂点：最大力 F_max = {f_max:.4f} N，位于第 {break_idx + 1} 个点",
        f"② 线性拟合区间取 F_max 的 {fit_lo:.0%}~{fit_hi:.0%}，共 {len(sel)} 个点，"
        f"线性拟合 F = k×位移 + b：k = {k:.4f} N/mm，b = {b:.4f} N（R² = {r2:.4f}）",
        f"③ 平台校正：拟合直线与位移轴交点（F=0 处）位移₀ = −b/k = {x0:.4f} mm"
        + ("（曲线起始存在只伸长不增力的平台段）" if x0 > 0
           else "（无正向平台段，位移₀=0）"),
        f"④ 弹性模量：E = k×标距/截面积 = {k * gauge:.4f} N ÷ {area:g} m²"
        f" = {e_pa:.4f} Pa（÷10⁹）→ {e_gpa:.2f} GPa",
        f"⑤ 断裂强度：σ_b = F_max/截面积 = {f_max:.4f}÷{area * 1e6:g}"
        f" = {strength_mpa:.2f} MPa",
        f"⑥ 断裂伸长率（校正后）：ε_b = (断裂位移 {x[break_idx]:.4f} − 位移₀ {x0:.4f})"
        f"÷标距 {gauge:g} = {elongation_pct:.3f}%",
        f"⑦ 平台段应变（被校正掉的部分）：ε₀ = {toe_eps_pct:.3f}%",
    ]

    return CurveResult(
        e_gpa=e_gpa, strength_mpa=strength_mpa, elongation_pct=elongation_pct,
        toe_eps_pct=toe_eps_pct, toe_disp_mm=x0, r2=r2, n_points=len(x),
        fit_k=k, fit_b=b, break_idx=break_idx, steps=steps)
