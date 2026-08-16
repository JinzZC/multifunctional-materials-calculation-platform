"""2 参数 Weibull 分布拟合（纤维强度分析常用方法，参考 GB/T 31290）。

分布函数：
    F(σ) = 1 − exp(−(σ/σ₀)^m)
线性化：
    ln(−ln(1−F)) = m·ln(σ) − m·ln(σ₀)     即  y = m·x + a

拟合步骤：
    1. 强度升序排序 σ₁ ≤ σ₂ ≤ … ≤ σ_N
    2. 失效概率用 median rank 估计：F̂ᵢ = (i−0.5)/N，天然落在 (0,1) 内
    3. xᵢ = ln(σᵢ)，yᵢ = ln(−ln(1−F̂ᵢ))，最小二乘回归
    4. m = 斜率；由截距 a = −m·ln(σ₀) 反推 σ₀ = exp(−a/m)

m 为 Weibull 模数（越大分散性越小），σ₀ 为特征强度（失效概率 63.2% 处）。
"""

import math

import numpy as np

from .models import WeibullResult


def median_ranks(n: int) -> list:
    """median rank：F̂ᵢ = (i − 0.5) / n，i = 1..n。"""
    if n < 2:
        raise ValueError("Weibull 分析至少需要 2 个数据点")
    return [(i + 0.5) / n for i in range(n)]


def weibull_fit(strengths) -> WeibullResult:
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
    f_hat = median_ranks(n)
    x = np.log(sorted_strengths)
    y = np.log(-np.log(1.0 - np.asarray(f_hat)))

    slope, intercept = np.polyfit(x, y, 1)   # y = slope·x + intercept
    if slope <= 0:
        # 斜率为负或为零在物理上无意义（强度越低失效概率越高才符合 Weibull）
        raise ValueError("数据不符合 Weibull 分布（拟合斜率 ≤ 0），请检查数据")

    m = float(slope)
    sigma0 = float(math.exp(-intercept / m))
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2)

    return WeibullResult(
        m=m, sigma0=sigma0, r2=r2,
        strengths_sorted=sorted_strengths,
        median_ranks=f_hat,
        x=x.tolist(), y=y.tolist(),
    )
