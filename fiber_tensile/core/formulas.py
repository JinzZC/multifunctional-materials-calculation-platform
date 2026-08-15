"""两种模式的强度计算公式。

单丝模式（参考 GB/T 31290、ASTM C1557）：
    σ = 4F / (π·d²)，F 为断裂强力(N)，d 为直径(m)。
    输入 F(cN)、d(μm)，输出 MPa；GPa 仅在显示时除以 1000。

纺织纤维模式（参考 GB/T 14337）：
    断裂强度 = F / Tt，F 为断裂强力(cN)，Tt 为线密度(dtex)，输出 cN/dtex。
    若已知纤维密度 ρ(g/cm³)，可换算 MPa：σ[MPa] = 强度[cN/dtex] × ρ × 100。

数值锚点：
    F=10 cN、d=7 μm → 2598.5 MPa ≈ 2.599 GPa
    5 cN/dtex、ρ=1.14 g/cm³ → 570 MPa
"""

import math

from .modes import get_mode_spec


def _require_positive(value, name: str) -> float:
    """校验输入为正的有限数，否则抛 ValueError。"""
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} 必须为正数，实际值：{value!r}")
    return float(value)


def filament_strength_mpa(force_cn: float, diameter_um: float) -> float:
    """单丝模式：σ = 4F/(πd²)。F 单位 cN，d 单位 μm，返回 MPa。"""
    f_cn = _require_positive(force_cn, "断裂强力")
    d_um = _require_positive(diameter_um, "直径")
    f_n = f_cn * 0.01              # cN → N
    d_m = d_um * 1e-6              # μm → m
    area = math.pi * d_m ** 2 / 4.0
    return f_n / area / 1e6        # Pa → MPa


def textile_tenacity_cn_dtex(force_cn: float, linear_density_dtex: float) -> float:
    """纺织模式：断裂强度 = F/Tt。F 单位 cN，Tt 单位 dtex，返回 cN/dtex。"""
    f_cn = _require_positive(force_cn, "断裂强力")
    t_dtex = _require_positive(linear_density_dtex, "线密度")
    return f_cn / t_dtex


def tenacity_to_mpa(tenacity_cn_dtex: float, density_gcm3: float) -> float:
    """由断裂强度(cN/dtex)与纤维密度(g/cm³)换算 MPa：σ[MPa] = 强度 × ρ × 100。"""
    t = _require_positive(tenacity_cn_dtex, "断裂强度")
    rho = _require_positive(density_gcm3, "密度")
    return t * rho * 100.0


def mpa_to_gpa(mpa: float) -> float:
    """MPa → GPa（仅用于显示）。"""
    return mpa / 1000.0


def compute_strength(mode: str, force_cn: float, diameter_um=None,
                     linear_density_dtex=None, density_gcm3=None) -> tuple:
    """按批次模式计算强度，返回 (strength, strength_mpa)。

    分发到计算模式注册表（core/modes.py）中该模式的公式：
    - filament：strength 为 MPa，strength_mpa 恒 None
    - textile：strength 为 cN/dtex；给了密度时 strength_mpa 为 MPa 换算值，否则 None
    """
    spec = get_mode_spec(mode)
    dim = {"diameter_um": diameter_um,
           "linear_density_dtex": linear_density_dtex}[spec.dim_field]
    if dim is None:
        raise ValueError(f"{spec.label}缺少{spec.dim_label}")
    return spec.compute(force_cn, dim, density_gcm3)
