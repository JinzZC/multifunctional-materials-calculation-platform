"""Tensile engineering stress/strain; numpy only.

Force is total applied load in N; lengths are mm; strain is dimensionless.
No automatic fracture detection, sorting, smoothing or machine compliance correction.
"""

from dataclasses import dataclass, field
import math

import numpy as np

ALGORITHM_VERSION = "mechanical-1"
MODES = {"tensile": "拉伸"}
SOURCES = {"strain": "实测工程应变", "extension": "标距内实测伸长",
           "crosshead": "横梁位移（表观应变）"}


@dataclass(frozen=True)
class Spec:
    mode: str = "tensile"
    source: str = "strain"
    section: str = "rectangle"
    width_mm: float = 10.0
    thickness_mm: float = 2.0
    diameter_mm: float = 5.0
    area_mm2: float = 20.0
    gauge_mm: float = 50.0
    fit_mode: str = "strain"
    fit_lo: float = 0.05  # percent strain, or percent of peak force
    fit_hi: float = 0.25
    target_pct: float = 1.0
    fracture_point: int = 0  # user-confirmed, one-based point; 0 means unspecified


@dataclass
class Result:
    modulus_gpa: float
    strength_mpa: float
    peak_strain_pct: float
    end_strain_pct: float
    target_stress_mpa: float | None
    work_to_peak_mj_m3: float | None
    r2: float
    slope_mpa: float
    intercept_mpa: float
    peak_index: int
    fit_indices: list[int]
    strain: list[float]
    stress_mpa: list[float]
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fracture_strain_pct: float | None = None
    fracture_stress_mpa: float | None = None


def _positive(value, label):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label}必须为有限正数")
    return value


def conversion(spec):
    """Return stress per N, strain per x, and an auditable formula description."""
    if spec.mode != "tensile":
        raise ValueError("通用力学曲线仅支持拉伸分析")
    if spec.source not in SOURCES:
        raise ValueError("拉伸需使用应变、标距伸长或横梁位移")
    if spec.section == "rectangle":
        area = _positive(spec.width_mm, "宽度") * _positive(spec.thickness_mm, "厚度")
    elif spec.section == "circle":
        area = math.pi * _positive(spec.diameter_mm, "直径") ** 2 / 4
    elif spec.section == "area":
        area = _positive(spec.area_mm2, "截面积")
    else:
        raise ValueError("未知截面类型")
    factor = 1.0 if spec.source == "strain" else 1 / _positive(spec.gauge_mm, "标距")
    return 1 / area, factor, f"σ = F/A；A = {area:.8g} mm²；ε = " + (
        "实测工程应变" if spec.source == "strain" else f"ΔL/L₀；L₀ = {spec.gauge_mm:g} mm")


def analyze(x, force_n, spec: Spec) -> Result:
    stress_factor, strain_factor, formula = conversion(spec)
    x = np.asarray(x, dtype=float)
    force = np.asarray(force_n, dtype=float)
    if x.ndim != 1 or force.ndim != 1 or x.shape != force.shape or x.size < 5:
        raise ValueError("需要等长的一维变形与力数据，至少 5 点")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(force)):
        raise ValueError("曲线包含非有限值")
    if np.any(x < 0) or np.any(force < 0):
        raise ValueError("变形与力不能为负；请先确认仪器零点、方向和单位")
    if np.any(np.diff(x) < 0):
        raise ValueError("变形必须按采集顺序单调不减；请截取单调加载段，不要排序或混入卸载段")
    peak = int(np.argmax(force))  # first peak, explicitly not fracture
    if peak < 3 or force[peak] <= 0:
        raise ValueError("峰值前有效加载点不足")
    strain, stress = x * strain_factor, force * stress_factor
    if not np.all(np.isfinite(strain)) or not np.all(np.isfinite(stress)):
        raise ValueError("应力或应变换算超出数值范围，请检查尺寸与单位")
    if (not math.isfinite(spec.fit_lo) or not math.isfinite(spec.fit_hi)
            or not 0 <= spec.fit_lo < spec.fit_hi):
        raise ValueError("拟合上下限需满足 0 ≤ 下限 < 上限")
    if spec.fit_mode == "strain":
        coordinate = strain * 100
        interval = "原始工程应变（%）"
    elif spec.fit_mode == "force":
        if spec.fit_hi > 100:
            raise ValueError("峰值力比例上限不能超过 100%")
        coordinate = force / force[peak] * 100
        interval = "峰值力比例（%）"
    else:
        raise ValueError("未知拟合区间类型")
    selected = np.flatnonzero((np.arange(x.size) <= peak)
                             & (coordinate >= spec.fit_lo) & (coordinate <= spec.fit_hi))
    if selected.size < 3:
        raise ValueError("峰值前拟合区间不足 3 点，请调整区间")
    xx, yy = strain[selected], stress[selected]
    if float(np.ptp(xx)) <= np.finfo(float).eps * max(1, float(np.max(np.abs(xx)))) * 100:
        raise ValueError("拟合区间应变变化不足")
    k, b = np.polyfit(xx, yy, 1)
    total = float(np.sum((yy - yy.mean()) ** 2))
    if not math.isfinite(k) or not math.isfinite(b) or k <= 0 or total <= 0:
        raise ValueError("拟合斜率非正或区间没有有效载荷变化")
    r2 = float(1 - np.sum((yy - (k * xx + b)) ** 2) / total)
    if not math.isfinite(r2):
        raise ValueError("拟合优度非有限值，请检查数值范围")
    if not math.isfinite(spec.target_pct) or spec.target_pct < 0:
        raise ValueError("指定应变必须为有限非负数")
    target = spec.target_pct / 100
    # First loading occurrence at duplicate strain values; no extrapolation.
    unique, first = np.unique(strain[:peak + 1], return_index=True)
    target_stress = float(np.interp(target, unique, stress[first])) if unique[0] <= target <= unique[-1] else None
    work = float(np.trapezoid(stress[:peak + 1], strain[:peak + 1]))
    if (not isinstance(spec.fracture_point, int) or isinstance(spec.fracture_point, bool)
            or not 0 <= spec.fracture_point <= len(x)):
        raise ValueError("断裂点号必须为有效的整数点号，0 表示未指定")
    if spec.fracture_point and spec.fracture_point - 1 < peak:
        raise ValueError("指定断裂点早于曲线峰值；请检查点号或截去断裂后的异常信号")
    warnings = ["峰值点不是自动判定的断裂点；末点应变仅代表记录终点。"]
    if spec.source == "crosshead":
        warnings.append("横梁位移包含机架柔度与夹持变形，模量和应变为表观值，未做柔度校正。")
    if r2 < 0.98:
        warnings.append("拟合 R² < 0.98，请检查所选区间是否属于线性段。")
    if target_stress is None:
        warnings.append("指定应变不在峰值前实测范围内，未进行外推。")
    if strain[0] > 0:
        warnings.append("曲线并非从零应变开始，积分仅覆盖首个实测点至首次峰值。")
    steps = [f"试验：{MODES[spec.mode]}；变形来源：{SOURCES[spec.source]}", formula,
             f"输入 {x.size} 点；首次峰值位于第 {peak + 1} 点，F = {force[peak]:.8g} N。",
             f"拟合区间：{interval} {spec.fit_lo:g}–{spec.fit_hi:g}；峰值前 {selected.size} 点。",
             f"最小二乘 σ = Eε + b；E = {k:.8g} MPa = {k / 1000:.8g} GPa；b = {b:.8g} MPa；R² = {r2:.8g}。",
             "应变未平移、数据未平滑或排序；模量为所选区间回归斜率，不自动等同于标准规定的弦模量。",
             f"首次峰值应力 = {stress[peak]:.8g} MPa；对应应变 = {strain[peak] * 100:.8g}%；末点应变 = {strain[-1] * 100:.8g}%。",
             f"指定 {spec.target_pct:g}% 应变处应力：" + (f"{target_stress:.8g} MPa（峰值前线性插值）" if target_stress is not None else "—（范围外）")]
    if work is not None:
        steps.append(f"首点至首次峰值 ∫σdε = {work:.8g} MJ/m³（梯形积分，不补零，不称为断裂韧性）。")
    fracture_strain = fracture_stress = None
    if spec.fracture_point:
        fracture_strain = float(strain[spec.fracture_point - 1] * 100)
        fracture_stress = float(stress[spec.fracture_point - 1])
        steps.append(f"人工确认断裂点：第 {spec.fracture_point} 点；断裂应变 = {fracture_strain:.8g}%；该点应力 = {fracture_stress:.8g} MPa。")
    else:
        steps.append("未指定人工确认断裂点，不输出断裂应变。")
    return Result(float(k / 1000), float(stress[peak]), float(strain[peak] * 100),
                  float(strain[-1] * 100), target_stress, work, r2, float(k), float(b),
                  peak, selected.tolist(), strain.tolist(), stress.tolist(), steps, warnings,
                  fracture_strain, fracture_stress)


def summarize(results):
    """Call per compatible test/source group; sample SD is undefined at n=1."""
    output = {}
    for field in ("modulus_gpa", "strength_mpa", "peak_strain_pct"):
        values = np.array([getattr(r, field) for r in results], dtype=float)
        if not values.size:
            continue
        mean = float(values.mean())
        sd = float(values.std(ddof=1)) if values.size > 1 else None
        output[field] = {"n": int(values.size), "mean": mean, "sd": sd,
                         "cv_pct": sd / mean * 100 if sd is not None and mean != 0 else None}
    return output
