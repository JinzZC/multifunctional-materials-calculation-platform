"""2 参数 Weibull 分布拟合（纤维强度分析常用方法，参考 GB/T 31290）。

分布函数：
    F(σ) = 1 − exp(−(σ/σ₀)^m)
线性化：
    ln(−ln(1−F)) = m·ln(σ) − m·ln(σ₀)     即  y = m·x + a

拟合步骤：
    1. 强度升序排序 σ₁ ≤ σ₂ ≤ … ≤ σ_N
    2. 失效概率按所选绘图位置方法估计（默认 Hazen）
    3. xᵢ = ln(σᵢ)，yᵢ = ln(−ln(1−F̂ᵢ))，最小二乘回归
    4. m = 斜率；由截距 a = −m·ln(σ₀) 反推 σ₀ = exp(−a/m)

m 为 Weibull 模数（越大分散性越小），σ₀ 为特征强度（失效概率 63.2% 处）。
"""

import math

import numpy as np

from .models import WeibullResult


RANK_METHODS = {
    "hazen": ("Hazen（现有默认）", "(i − 0.5) / N"),
    "mean_rank": ("Origin 兼容（Mean Rank / Van der Waerden）", "i / (N + 1)"),
    "benard": ("Benard 中位秩", "(i − 0.3) / (N + 0.4)"),
    "blom": ("Blom", "(i − 0.375) / (N + 0.25)"),
}


def rank_method_label(method: str) -> str:
    """返回绘图位置方法的可读名称。"""
    try:
        return RANK_METHODS[method][0]
    except KeyError:
        raise ValueError(f"未知的 Weibull 排序概率方法：{method!r}") from None


def plotting_positions(n: int, method: str = "hazen") -> list:
    """计算 Weibull 绘图位置 F̂ᵢ，i = 1..N。"""
    if n < 2:
        raise ValueError("Weibull 分析至少需要 2 个数据点")
    if method not in RANK_METHODS:
        raise ValueError(f"未知的 Weibull 排序概率方法：{method!r}")
    if method == "hazen":
        return [(i - 0.5) / n for i in range(1, n + 1)]
    if method == "mean_rank":
        return [i / (n + 1.0) for i in range(1, n + 1)]
    if method == "benard":
        return [(i - 0.3) / (n + 0.4) for i in range(1, n + 1)]
    return [(i - 0.375) / (n + 0.25) for i in range(1, n + 1)]


def median_ranks(n: int) -> list:
    """兼容旧接口：返回 Hazen 绘图位置。"""
    return plotting_positions(n, "hazen")


def weibull_fit(strengths, rank_method: str = "hazen") -> WeibullResult:
    """对强度序列做 2 参数 Weibull 拟合，返回 m、σ₀、R² 及变换后的数据。"""
    values = [float(s) for s in strengths]
    if len(values) < 2:
        raise ValueError("数据量不足，Weibull 分析至少需要 2 个数据点")
    if any(not math.isfinite(s) or s <= 0 for s in values):
        raise ValueError("强度值必须为正数")

    sorted_strengths = sorted(values)
    n = len(sorted_strengths)
    if sorted_strengths[0] == sorted_strengths[-1]:
        raise ValueError("数据全部相等，无法进行 Weibull 拟合（无分散性）")
    f_hat = plotting_positions(n, rank_method)
    x = np.log(sorted_strengths)
    y = np.log(-np.log(1.0 - np.asarray(f_hat)))

    slope, intercept = np.polyfit(x, y, 1)   # y = slope·x + intercept
    if slope <= 0:
        # 斜率为负或为零在物理上无意义（强度越低失效概率越高才符合 Weibull）
        raise ValueError("数据不符合 Weibull 分布（拟合斜率 ≤ 0），请检查数据")

    m = float(slope)
    sigma0 = float(math.exp(-intercept / m))
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2)

    rank_label, rank_formula = RANK_METHODS[rank_method]
    steps = [
        "计算过程（Weibull 二参数线性最小二乘）",
        f"① 强度升序排列，样本数 N = {n}",
        f"② 排序概率：{rank_label}，F̂ᵢ = {rank_formula}",
        "③ 线性化：xᵢ = ln(σᵢ)，yᵢ = ln[−ln(1−F̂ᵢ)]",
        f"④ 普通最小二乘拟合 y = m·x + a：m = {m:.6f}，a = {intercept:.6f}",
        f"⑤ σ₀ = exp(−a/m) = {sigma0:.6g}，R² = {r2:.6f}",
    ]
    return WeibullResult(
        m=m, sigma0=sigma0, r2=r2,
        strengths_sorted=sorted_strengths,
        median_ranks=f_hat,
        x=x.tolist(), y=y.tolist(), steps=steps, rank_method=rank_method,
    )


# ---------- 极大似然估计（MLE）与三参数 Weibull ----------

def _fit_r2(y: np.ndarray, y_pred: np.ndarray) -> float:
    """SS 型拟合优度：R² = 1 − Σ(y−ŷ)²/Σ(y−ȳ)²。"""
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 1.0


def _mle_profile_2p(values) -> tuple:
    """2 参数 Weibull 极大似然：对 m 做黄金分割一维搜索（轮廓似然）。

    给定 m 时 σ₀ 的 MLE 有闭式解 σ₀ = (Σσᵢ^m/n)^(1/m)，故只需一维优化。
    返回 (m, sigma0)。
    """
    n = len(values)
    s = np.asarray(values, dtype=float)
    ln_s = np.log(s)
    mean_ln_s = float(np.mean(ln_s))
    centered_ln_s = ln_s - mean_ln_s

    def log_mean_exp_centered(m):
        scaled = m * centered_ln_s
        peak = float(np.max(scaled))
        return peak + math.log(float(np.exp(scaled - peak).sum())) - math.log(n)

    def log_sigma0_of(m):
        # ln σ₀ = [logsumexp(m·lnσᵢ) − ln(n)] / m。
        # 在对数域计算，避免 σᵢ^m 在高模数或大强度时溢出。
        return mean_ln_s + log_mean_exp_centered(m) / m

    def sigma0_of(m):
        return float(math.exp(log_sigma0_of(m)))

    def neg_loglik(m):
        # 去掉与 m 无关的 n·mean(lnσ) 后，使用中心化对数形式，避免单位整体
        # 缩放时两个巨大项相减造成消减误差。
        return -n * math.log(m) + n * log_mean_exp_centered(m)

    gr = (math.sqrt(5.0) - 1.0) / 2.0
    lo, hi = 0.05, 200.0
    c = hi - gr * (hi - lo)
    d = lo + gr * (hi - lo)
    fc, fd = neg_loglik(c), neg_loglik(d)
    while abs(hi - lo) > 1e-8:
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - gr * (hi - lo)
            fc = neg_loglik(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + gr * (hi - lo)
            fd = neg_loglik(d)
    m = (lo + hi) / 2.0
    return float(m), sigma0_of(m)


def _check_strengths(values) -> None:
    if len(values) < 2:
        raise ValueError("数据量不足，Weibull 分析至少需要 2 个数据点")
    if any(not math.isfinite(s) or s <= 0 for s in values):
        raise ValueError("强度值必须为正数")
    if min(values) == max(values):
        raise ValueError("数据全部相等，无法进行 Weibull 拟合（无分散性）")


def _build_transformed(sorted_s, gamma: float, rank_method: str = "hazen") -> tuple:
    """按所选绘图位置构造线性化坐标（x = ln(σ−γ)）。"""
    n = len(sorted_s)
    f_hat = plotting_positions(n, rank_method)
    x = np.log(np.asarray(sorted_s) - gamma)
    y = np.log(-np.log(1.0 - np.asarray(f_hat)))
    return x, y, f_hat


def weibull_fit_mle(strengths, rank_method: str = "hazen") -> WeibullResult:
    """2 参数 Weibull 极大似然估计（参数估计统计意义上最优）。

    注意：结果中的 R² 为所选绘图位置线性化下的拟合优度参考；
    该度量下最小二乘法最优，MLE 的优势在参数无偏性与效率。
    """
    values = [float(s) for s in strengths]
    _check_strengths(values)
    sorted_s = sorted(values)
    m, sigma0 = _mle_profile_2p(values)
    x, y, f_hat = _build_transformed(sorted_s, 0.0, rank_method)
    y_pred = m * x - m * math.log(sigma0)
    r2 = _fit_r2(y, y_pred)
    steps = [
        "计算过程（Weibull 极大似然估计 MLE，2 参数）",
        f"① 似然函数 L(m,σ₀) = Π (m/σ₀)·(σᵢ/σ₀)^(m−1)·exp(−(σᵢ/σ₀)^m)，"
        f"对 {len(values)} 个数据取对数后最大化",
        f"② 给定 m 时 σ₀ 的 MLE 有闭式解：σ₀ = (Σσᵢ^m/n)^(1/m)，"
        "因此只需对 m 做一维黄金分割搜索",
        f"③ 黄金分割搜索区间 m ∈ [0.05, 200]，收敛容差 1e-8",
        f"④ 结果：Weibull 模数 m = {m:.4f}，特征强度 σ₀ = {sigma0:.2f}",
        f"⑤ {rank_method_label(rank_method)} 线性化下的拟合优度 R² = {r2:.4f}（最小二乘法在该度量下最优，"
        "MLE 的优势是参数估计的统计最优性）",
        "⑥ 注：小样本（n<30）时 MLE 的 m 存在正偏倚，工程上可用 "
        "m×(n−1)/n 修正，本工具显示未修正值",
    ]
    return WeibullResult(
        m=m, sigma0=sigma0, r2=r2, strengths_sorted=sorted_s,
        median_ranks=f_hat, x=x.tolist(), y=y.tolist(), gamma=0.0, steps=steps,
        rank_method=rank_method)


def weibull_fit_3p(strengths, rank_method: str = "hazen") -> WeibullResult:
    """3 参数 Weibull（位置参数 γ）非线性最小二乘。

    最小化 Σ(F̂ᵢ − F(σᵢ; m, σ₀, γ))²（F̂ 按所选绘图位置计算），用带阻尼的
    Gauss-Newton（数值雅可比）求解。说明：3 参数 Weibull 的极大似然在
    γ→最小强度处常退化（文献已知病理），故采用非线性最小二乘，
    与 2 参数线性法的排序概率口径保持一致。
    """
    values = [float(s) for s in strengths]
    _check_strengths(values)
    sorted_s = sorted(values)
    s = np.asarray(sorted_s, dtype=float)
    n = len(s)
    s_min = float(s[0])
    f_hat = np.asarray(plotting_positions(n, rank_method))

    def fval(m, sigma0, gamma):
        z = (s - gamma) / sigma0
        # exp(m·ln z) 采用裁剪后的对数域计算，避免 z**m 溢出警告。
        log_power = m * np.log(z)
        power = np.exp(np.clip(log_power, -745.0, 709.0))
        return -np.expm1(-power)

    def residual(v):
        m, sigma0, gamma = v
        if m <= 0.05 or sigma0 <= 0 or gamma < 0 or gamma >= 0.8 * s_min:
            return None
        return f_hat - fval(m, sigma0, gamma)

    # 初值：2 参数最小二乘解，γ=0
    seed = weibull_fit(values, rank_method)
    v = np.array([seed.m, seed.sigma0, 0.0])
    iters = 0
    converged = False
    step_norm = float("nan")
    for iters in range(1, 200 + 1):
        f = residual(v)
        if f is None:
            break
        jac = np.zeros((n, 3))
        for j in range(3):
            vh = v.copy()
            vh[j] += 1e-6 * max(abs(v[j]), 1.0)
            fh = residual(vh)
            if fh is None:
                jac[:, j] = 0.0
            else:
                jac[:, j] = (fh - f) / (1e-6 * max(abs(v[j]), 1.0))
        step = np.linalg.lstsq(jac, -f, rcond=None)[0]
        alpha = 1.0
        v_new = v + step
        for _ in range(15):
            if residual(v_new) is not None:
                break
            alpha *= 0.5
            v_new = v + alpha * step
        if residual(v_new) is None:
            break
        v = v_new
        step_norm = float(np.linalg.norm(alpha * step))
        if step_norm < 1e-10:
            converged = True
            break
    m, sigma0, gamma = float(v[0]), float(v[1]), float(v[2])

    # 退化防护：γ 逼近最小强度或模数过小时退回 2 参数
    if (not converged and iters >= 200) or gamma >= 0.75 * s_min or m < 0.05:
        r = weibull_fit(values, rank_method)
        r.steps.insert(0, "3 参数拟合无稳定解（γ 趋于最小强度），已退回 2 参数最小二乘：")
        return r

    gamma = max(gamma, 0.0)
    x, y, f_hat_l = _build_transformed(sorted_s, gamma, rank_method)
    y_pred = m * x - m * math.log(sigma0)
    r2 = _fit_r2(y, y_pred)
    r2_lsq = weibull_fit(values, rank_method).r2
    steps = [
        f"计算过程（3 参数 Weibull，{rank_method_label(rank_method)} 非线性最小二乘）",
        "分布：F(σ) = 1 − exp(−((σ−γ)/σ₀)^m)，γ 为位置参数（强度下限）",
        f"① 最小化 Σ(F̂ᵢ − F(σᵢ))²（F̂ 为 {rank_method_label(rank_method)}），"
        "初值取 2 参数最小二乘解，γ₀ = 0",
        f"② 带阻尼 Gauss-Newton（数值雅可比）迭代 {iters} 次"
        + ("收敛" if converged else "（未完全收敛，取当前解）"),
        f"③ 结果：m = {m:.4f}，σ₀ = {sigma0:.2f}，γ = {gamma:.4f}",
        f"④ 平移后线性化（x = ln(σ−γ)）拟合优度 R² = {r2:.4f}"
        + (f"（2 参数最小二乘为 {r2_lsq:.4f}）" if r2_lsq > r2 else ""),
    ]
    return WeibullResult(
        m=m, sigma0=sigma0, r2=r2, strengths_sorted=sorted_s,
        median_ranks=f_hat_l, x=x.tolist(), y=y.tolist(), gamma=gamma, steps=steps,
        rank_method=rank_method)
