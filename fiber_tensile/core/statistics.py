"""批量统计：均值、样本标准差（ddof=1）、变异系数 CV%。"""

import math

from .models import AnalysisResult


def batch_statistics(values) -> AnalysisResult:
    """对强度值序列做统计。

    样本数 < 2 时 std 与 cv_percent 为 None（单个样本无统计意义）。
    强度值必须为正的有限数。
    """
    v = [float(x) for x in values]
    if not v:
        raise ValueError("没有数据，无法统计")
    if any(not math.isfinite(x) or x <= 0 for x in v):
        raise ValueError("强度值必须为正数")

    n = len(v)
    mean = sum(v) / n
    if n < 2:
        return AnalysisResult(n=n, mean=mean, std=None, cv_percent=None,
                              min_val=mean, max_val=mean)

    var = sum((x - mean) ** 2 for x in v) / (n - 1)   # 样本方差，ddof=1
    std = math.sqrt(var)
    cv = std / mean * 100.0
    return AnalysisResult(n=n, mean=mean, std=std, cv_percent=cv,
                          min_val=min(v), max_val=max(v))
