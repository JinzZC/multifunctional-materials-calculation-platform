"""复合材料基础计算（纯计算层，仅依赖标准库）。

混合法则（Rule of Mixtures）：
    E₁ = E_f·V_f + E_m·(1−V_f)            纵向模量
    E₂ = E_f·E_m / (V_f·E_m + (1−V_f)·E_f) 横向模量（反混合法则）
    G₁₂ = G_f·G_m / (V_f·G_m + (1−V_f)·G_f)
    ν₁₂ = ν_f·V_f + ν_m·(1−V_f)
    ρ_c = ρ_f·V_f + ρ_m·(1−V_f)

纤维体积分数：
    密度法：V_f = (ρ_c − ρ_m) / (ρ_f − ρ_m)
    酸解法：V_f = (w_f/ρ_f) / (w_f/ρ_f + w_m/ρ_m)（忽略孔隙）
    孔隙率：V_v = 1 − ρ_c·(w_f/ρ_f + w_m/ρ_m)

公式中的 ⟨分子|分母⟩ 记号由界面渲染为分数形式。
"""

import math
from dataclasses import dataclass, field


@dataclass
class ROMResult:
    e1_gpa: float
    e2_gpa: float
    g12_gpa: float
    nu12: float
    rho_gcm3: float
    vf: float
    vm: float
    steps: list = field(default_factory=list)


@dataclass
class VFResult:
    vf: float
    vm: float
    vv: float | None       # 孔隙率（酸解法才有）
    steps: list = field(default_factory=list)


def _check(value, name, lo, hi):
    if not math.isfinite(value) or not lo < value < hi:
        raise ValueError(f"{name} 需在 ({lo:g}, {hi:g}) 之间，实际值：{value!r}")
    return float(value)


def compute_rom(ef_gpa, em_gpa, gf_gpa, gm_gpa, nuf, num, rhof, rhom, vf) -> ROMResult:
    """单层板工程常数（混合法则）。单位：E/G GPa，ρ g/cm³，ν 无量纲。"""
    ef = _check(ef_gpa, "纤维纵向模量 E_f", 1, 2000)
    em = _check(em_gpa, "树脂模量 E_m", 0.1, 100)
    gf = _check(gf_gpa, "纤维剪切模量 G_f", 1, 1000)
    gm = _check(gm_gpa, "树脂剪切模量 G_m", 0.05, 50)
    _check(nuf, "纤维泊松比 ν_f", 0.01, 0.49)
    _check(num, "树脂泊松比 ν_m", 0.01, 0.49)
    rhof = _check(rhof, "纤维密度 ρ_f", 0.1, 10)
    rhom = _check(rhom, "树脂密度 ρ_m", 0.1, 10)
    vf = _check(vf, "纤维体积分数 V_f", 0.01, 0.99)
    vm = 1.0 - vf

    e1 = ef * vf + em * vm
    e2 = ef * em / (vf * em + vm * ef)
    g12 = gf * gm / (vf * gm + vm * gf)
    nu12 = nuf * vf + num * vm
    rho = rhof * vf + rhom * vm

    steps = [
        "计算过程（混合法则，Rule of Mixtures）",
        f"① 基体体积分数：V_m = 1 − V_f = 1 − {vf:g} = {vm:.4f}",
        f"② 纵向模量：E₁ = E_f×V_f + E_m×V_m"
        f" = {ef:g}×{vf:g} + {em:g}×{vm:.4f} = {e1:.2f} GPa",
        f"③ 横向模量（反混合法则）：E₂ = E_f×E_m/(V_f×E_m + V_m×E_f)"
        f" = {ef:g}×{em:g}÷({vf:g}×{em:g} + {vm:.4f}×{ef:g}) = {e2:.2f} GPa",
        f"④ 剪切模量：G₁₂ = G_f×G_m/(V_f×G_m + V_m×G_f) = {g12:.2f} GPa",
        f"⑤ 主泊松比：ν₁₂ = ν_f×V_f + ν_m×V_m"
        f" = {nuf:g}×{vf:g} + {num:g}×{vm:.4f} = {nu12:.4f}",
        f"⑥ 密度：ρ_c = ρ_f×V_f + ρ_m×V_m"
        f" = {rhof:g}×{vf:g} + {rhom:g}×{vm:.4f} = {rho:.3f} g/cm³",
    ]
    return ROMResult(e1_gpa=e1, e2_gpa=e2, g12_gpa=g12, nu12=nu12,
                     rho_gcm3=rho, vf=vf, vm=vm, steps=steps)


def compute_vf_density(rhoc, rhof, rhom) -> VFResult:
    """纤维体积分数（密度法）。"""
    rc = _check(rhoc, "复合材料密度 ρ_c", 0.1, 10)
    rf = _check(rhof, "纤维密度 ρ_f", 0.1, 10)
    rm = _check(rhom, "树脂密度 ρ_m", 0.1, 10)
    if not rm < rc < rf:
        raise ValueError(f"密度法要求 ρ_m({rm:g}) < ρ_c({rc:g}) < ρ_f({rf:g})，请检查密度数据")
    vf = (rc - rm) / (rf - rm)
    steps = [
        "计算过程（纤维体积分数，密度法）",
        f"① V_f = (ρ_c − ρ_m)/(ρ_f − ρ_m) = ({rc:g} − {rm:g})÷({rf:g} − {rm:g})"
        f" = {vf:.4f}",
        f"② V_m = 1 − V_f = {1 - vf:.4f}",
    ]
    return VFResult(vf=vf, vm=1 - vf, vv=None, steps=steps)


def compute_vf_acid(wf, rhof, rhom, rhoc) -> VFResult:
    """纤维体积分数与孔隙率（酸解法/灼烧法）。wf 为纤维质量分数（0~1）。"""
    wf = _check(wf, "纤维质量分数 w_f", 0.01, 0.99)
    wm = 1.0 - wf
    rf = _check(rhof, "纤维密度 ρ_f", 0.1, 10)
    rm = _check(rhom, "树脂密度 ρ_m", 0.1, 10)
    rc = _check(rhoc, "复合材料密度 ρ_c", 0.1, 10)
    term = wf / rf + wm / rm
    vf = (wf / rf) / term
    vv = 1.0 - rc * term
    if vv < -1e-6:
        raise ValueError("计算得到的孔隙率为负值，请检查密度与质量分数数据")
    vv = max(vv, 0.0)
    steps = [
        "计算过程（纤维体积分数与孔隙率，酸解法）",
        f"① 树脂质量分数：w_m = 1 − w_f = {wm:.4f}",
        f"② 无孔隙假设下的体积分数：V_f = (w_f/ρ_f)/(w_f/ρ_f + w_m/ρ_m)"
        f" = ({wf:g}÷{rf:g})÷({wf:g}÷{rf:g} + {wm:.4f}÷{rm:g}) = {vf:.4f}",
        f"③ 孔隙率：V_v = 1 − ρ_c×(w_f/ρ_f + w_m/ρ_m)"
        f" = 1 − {rc:g}×({term:.6f}) = {vv:.4f}",
        f"④ 校正后基体体积分数：V_m = 1 − V_f − V_v = {1 - vf - vv:.4f}",
    ]
    return VFResult(vf=vf, vm=1 - vf - vv, vv=vv, steps=steps)
