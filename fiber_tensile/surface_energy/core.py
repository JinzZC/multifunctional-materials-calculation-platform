"""表面能计算方法（纯计算层，仅依赖 numpy）。

四种方法（方法注册表 METHODS 为单一事实来源）：

- OWRK 双液法：γ_L(1+cosθ) = 2(√(γ_S^d·γ_L^d) + √(γ_S^p·γ_L^p))
  对 √γ_S^d、√γ_S^p 做最小二乘（≥2 种液体），平方得色散/极性分量。
- Wu 调和平均法：γ_L(1+cosθ) = 4γ_S^d·γ_L^d/(γ_S^d+γ_L^d) + 4γ_S^p·γ_L^p/(γ_S^p+γ_L^p)
  以 OWRK 解为初值做 Gauss-Newton 迭代。
- Fowkes 法：单液体 γ_S^d = [γ_L(1+cosθ)]²/(4γ_L^d)，仅色散分量。
- Zisman 法：cosθ 对 γ_L 线性回归，外推 cosθ=1 得临界表面张力 γ_c。

单位：mN/m；接触角为度（0–180）。另计算各液体的界面能与粘附功。
"""

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

METHOD_OWRK = "owrk"
METHOD_WU = "wu"
METHOD_FOWKES = "fowkes"
METHOD_ZISMAN = "zisman"

_MAX_ITER = 60
_STEP_TOL = 1e-12


@dataclass
class LiquidPoint:
    """一种测试液体及其在样品表面的接触角。"""

    liquid_name: str
    gamma_total: float          # 液体总表面张力 mN/m
    angle_deg: float            # 接触角（度）
    gamma_d: float | None = None   # 色散分量（Zisman 不需要）
    gamma_p: float | None = None   # 极性分量（Zisman 不需要）


@dataclass
class SurfaceEnergyResult:
    """表面能计算结果（不同方法填充不同字段）。"""

    method: str
    gamma_d: float | None = None       # 色散分量 mN/m
    gamma_p: float | None = None       # 极性分量 mN/m
    gamma_total: float | None = None   # 总表面能 mN/m
    gamma_c: float | None = None       # Zisman 临界表面张力 mN/m
    r2: float | None = None
    per_liquid: list | None = None     # [(液体名, 界面能 γ_SL, 粘附功 W_A)]


@dataclass(frozen=True)
class MethodSpec:
    """一种表面能计算方法的完整规格。"""

    key: str
    label: str
    min_points: int
    max_points: int | None       # None 不限；fowkes 固定 1
    needs_gamma_d: bool
    needs_gamma_p: bool
    hint: str
    compute: Callable            # compute(list[LiquidPoint]) -> SurfaceEnergyResult


def _check_angle(points) -> None:
    for p in points:
        if not math.isfinite(p.angle_deg) or not 0.0 < p.angle_deg < 180.0:
            raise ValueError(f"接触角必须为 0–180° 之间的数值（液体「{p.liquid_name}」θ={p.angle_deg}）")
        if not math.isfinite(p.gamma_total) or p.gamma_total <= 0:
            raise ValueError(f"液体表面张力必须为正数（液体「{p.liquid_name}」γ={p.gamma_total}）")


def _check_components(points) -> None:
    for p in points:
        for name, v in (("γ^d", p.gamma_d), ("γ^p", p.gamma_p)):
            if v is not None and (not math.isfinite(v) or v < 0):
                raise ValueError(f"液体「{p.liquid_name}」的 {name} 分量无效：{v}")
        if p.gamma_d is not None and p.gamma_p is not None \
                and p.gamma_d + p.gamma_p > p.gamma_total + 1e-6:
            raise ValueError(
                f"液体「{p.liquid_name}」的分量之和（{p.gamma_d + p.gamma_p:g}）"
                f"大于总表面张力（{p.gamma_total:g}）")


def _r2(observed: np.ndarray, predicted: np.ndarray) -> float:
    ss_res = float(np.sum((observed - predicted) ** 2))
    ss_tot = float(np.sum((observed - observed.mean()) ** 2))
    if ss_tot == 0:
        return 1.0
    return 1.0 - ss_res / ss_tot


def _per_liquid(points, gamma_d: float, gamma_p: float) -> list:
    """各液体的界面能 γ_SL 与粘附功 W_A = γ_L(1+cosθ)。"""
    out = []
    for p in points:
        wa = p.gamma_total * (1.0 + math.cos(math.radians(p.angle_deg)))
        if p.gamma_d is not None and p.gamma_p is not None:
            gamma_sl = (gamma_d + gamma_p + p.gamma_total
                        - 2.0 * (math.sqrt(gamma_d * p.gamma_d)
                                 + math.sqrt(gamma_p * p.gamma_p)))
        else:
            gamma_sl = None
        out.append((p.liquid_name, gamma_sl, wa))
    return out


# ---------- OWRK 双液法 ----------

def compute_owrk(points: list) -> SurfaceEnergyResult:
    for p in points:
        if p.gamma_d is None or p.gamma_p is None:
            raise ValueError(f"OWRK 法需要液体的 γ^d 与 γ^p 分量（液体「{p.liquid_name}」缺失）")
    n = len(points)
    a = np.zeros((n, 2))
    c = np.zeros(n)
    for i, p in enumerate(points):
        a[i] = (2.0 * math.sqrt(p.gamma_d), 2.0 * math.sqrt(p.gamma_p))
        c[i] = p.gamma_total * (1.0 + math.cos(math.radians(p.angle_deg)))
    x, *_ = np.linalg.lstsq(a, c, rcond=None)
    xd, xp = float(x[0]), float(x[1])
    if xd < 0 or xp < 0:
        raise ValueError(
            "出现负的平方根，所选液体组合不适用 OWRK 法"
            "（建议极性 + 非极性液体搭配，如 水 + 二碘甲烷）")
    gamma_d, gamma_p = xd ** 2, xp ** 2
    return SurfaceEnergyResult(
        method=METHOD_OWRK, gamma_d=gamma_d, gamma_p=gamma_p,
        gamma_total=gamma_d + gamma_p, r2=_r2(c, a @ x),
        per_liquid=_per_liquid(points, gamma_d, gamma_p))


# ---------- Wu 调和平均法 ----------

def compute_wu(points: list) -> SurfaceEnergyResult:
    for p in points:
        if p.gamma_d is None or p.gamma_p is None:
            raise ValueError(f"Wu 法需要液体的 γ^d 与 γ^p 分量（液体「{p.liquid_name}」缺失）")
    seed = compute_owrk(points)   # OWRK 解作迭代初值

    def term(v, lv):
        # 任一分量为 0 时该项为 0（避免 0/0）
        return 0.0 if v <= 0 or lv <= 0 else 4.0 * v * lv / (v + lv)

    def target(gd, gp):
        return [p.gamma_total * (1.0 + math.cos(math.radians(p.angle_deg)))
                - term(gd, p.gamma_d) - term(gp, p.gamma_p) for p in points]

    def solve_1d(fn):
        # 单变量 Gauss-Newton：最小化残差平方和
        v = 1.0
        for _ in range(_MAX_ITER):
            f = np.asarray(fn(v), dtype=float)
            h = 1e-6
            d = (np.asarray(fn(v + h), dtype=float) - f) / h
            g = float(np.dot(f, d))
            dd = float(np.dot(d, d))
            if dd < 1e-14:
                break
            step = -g / dd
            v += step
            if abs(step) < _STEP_TOL:
                break
        return max(v, 0.0)

    has_d = any(p.gamma_d > 0 for p in points)
    has_p = any(p.gamma_p > 0 for p in points)
    if not has_d and not has_p:
        raise ValueError("液体分量数据无效，无法用 Wu 法计算")
    if has_d and not has_p:
        gd = solve_1d(lambda gd: np.array(target(gd, 0.0)))
        gp = 0.0
    elif has_p and not has_d:
        gd = 0.0
        gp = solve_1d(lambda gp: np.array(target(0.0, gp)))
    else:
        # 2 维 Gauss-Newton（数值 Jacobian）
        v = np.array([max(seed.gamma_d, 1e-6), max(seed.gamma_p, 1e-6)])
        for _ in range(_MAX_ITER):
            f = np.array(target(v[0], v[1]))
            jac = np.zeros((len(points), 2))
            for j in range(2):
                vh = v.copy()
                vh[j] += 1e-6
                jac[:, j] = (np.array(target(vh[0], vh[1])) - f) / 1e-6
            step = np.linalg.lstsq(jac, -f, rcond=None)[0]
            v = v + step
            if np.linalg.norm(step) < _STEP_TOL:
                break
            if v[0] <= 0 or v[1] <= 0:
                raise ValueError("Wu 法迭代出现负值，所选液体组合不适用（可换用 OWRK 法）")
        gd, gp = float(v[0]), float(v[1])

    residual = np.abs(np.asarray(target(gd, gp)))
    c = np.array([p.gamma_total * (1.0 + math.cos(math.radians(p.angle_deg)))
                  for p in points])
    if np.max(residual) > 0.5 * np.max(np.abs(c)):
        raise ValueError("Wu 法迭代未收敛，请检查数据或换用 OWRK 法")
    gamma_d, gamma_p = max(gd, 0.0), max(gp, 0.0)
    c_pred = c - np.array(target(gamma_d, gamma_p))   # 模型预测 = 观测值 − 残差
    return SurfaceEnergyResult(
        method=METHOD_WU, gamma_d=gamma_d, gamma_p=gamma_p,
        gamma_total=gamma_d + gamma_p, r2=_r2(c, c_pred),
        per_liquid=_per_liquid(points, gamma_d, gamma_p))


# ---------- Fowkes 法 ----------

def compute_fowkes(points: list) -> SurfaceEnergyResult:
    if len(points) != 1:
        raise ValueError(f"Fowkes 法需要恰好 1 种液体（当前 {len(points)} 种）")
    p = points[0]
    if p.gamma_d is None:
        raise ValueError(f"Fowkes 法需要液体的 γ^d 分量（液体「{p.liquid_name}」缺失）")
    gamma_d = (p.gamma_total * (1.0 + math.cos(math.radians(p.angle_deg)))) ** 2 \
        / (4.0 * p.gamma_d)
    return SurfaceEnergyResult(
        method=METHOD_FOWKES, gamma_d=gamma_d, gamma_p=None, gamma_total=gamma_d,
        r2=None, per_liquid=_per_liquid(points, gamma_d, 0.0))


# ---------- Zisman 法 ----------

def compute_zisman(points: list) -> SurfaceEnergyResult:
    x = np.array([p.gamma_total for p in points])
    y = np.array([math.cos(math.radians(p.angle_deg)) for p in points])
    slope, intercept = np.polyfit(x, y, 1)
    if abs(slope) < 1e-12:
        raise ValueError("拟合斜率接近 0，无法外推临界表面张力（请检查接触角数据）")
    gamma_c = (1.0 - intercept) / slope
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2)
    per_liquid = [(p.liquid_name, None,
                   p.gamma_total * (1.0 + math.cos(math.radians(p.angle_deg))))
                  for p in points]
    return SurfaceEnergyResult(
        method=METHOD_ZISMAN, gamma_c=gamma_c, r2=r2, per_liquid=per_liquid)


# ---------- 方法注册表与分发 ----------

METHODS: dict[str, MethodSpec] = {
    METHOD_OWRK: MethodSpec(
        key=METHOD_OWRK, label="OWRK 双液法", min_points=2, max_points=None,
        needs_gamma_d=True, needs_gamma_p=True,
        hint="需 ≥2 种液体，建议极性 + 非极性搭配（如 水 + 二碘甲烷）",
        compute=compute_owrk),
    METHOD_WU: MethodSpec(
        key=METHOD_WU, label="Wu 调和平均法", min_points=2, max_points=None,
        needs_gamma_d=True, needs_gamma_p=True,
        hint="需 ≥2 种液体，调和平均公式，适合低能表面",
        compute=compute_wu),
    METHOD_FOWKES: MethodSpec(
        key=METHOD_FOWKES, label="Fowkes 法", min_points=1, max_points=1,
        needs_gamma_d=True, needs_gamma_p=False,
        hint="仅 1 种非极性液体，只能计算色散分量 γ^d",
        compute=compute_fowkes),
    METHOD_ZISMAN: MethodSpec(
        key=METHOD_ZISMAN, label="Zisman 法", min_points=2, max_points=None,
        needs_gamma_d=False, needs_gamma_p=False,
        hint="同系列液体（建议 ≥3 种），外推临界表面张力 γ_c",
        compute=compute_zisman),
}

METHOD_LABELS = {key: spec.label for key, spec in METHODS.items()}


def get_method_spec(method: str) -> MethodSpec:
    try:
        return METHODS[method]
    except KeyError:
        raise ValueError(f"未知的表面能计算方法：{method!r}（仅支持 {tuple(METHODS)}）") from None


def compute_surface_energy(method: str, points: list) -> SurfaceEnergyResult:
    """按方法分发计算；先校验点数与角度、分量有效性。"""
    spec = get_method_spec(method)
    if len(points) < spec.min_points:
        raise ValueError(f"{spec.label}至少需要 {spec.min_points} 种液体（当前 {len(points)} 种）")
    if spec.max_points is not None and len(points) > spec.max_points:
        raise ValueError(f"{spec.label}最多允许 {spec.max_points} 种液体（当前 {len(points)} 种）")
    _check_angle(points)
    _check_components(points)
    return spec.compute(list(points))
