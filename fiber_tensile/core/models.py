"""数据模型定义：纯 dataclass 与常量，无外部依赖。

模式常量与单位标签的单一事实来源在 core/modes.py（计算模式注册表），此处再导出
以兼容既有导入路径。
"""

from dataclasses import dataclass, field

from .modes import (  # noqa: F401 — 兼容旧导入路径
    MODE_FILAMENT,
    MODE_LABELS,
    MODE_TEXTILE,
    VALID_MODES,
    get_mode_spec,
    strength_unit_label,
)

VALID_FORCE_UNITS = ("cN", "N", "mN")


@dataclass
class Sample:
    """单根纤维试样。breaking_force 按 force_unit 的录入原值保存。"""

    breaking_force: float
    force_unit: str = "cN"
    diameter_um: float | None = None            # 单丝模式必填，纺织模式为 None
    linear_density_dtex: float | None = None    # 纺织模式必填，单丝模式为 None
    sample_no: str | None = None
    remark: str | None = None
    test_date: str | None = None
    density_gcm3: float | None = None   # 仅文件导入时携带（密度最终存批次级）
    id: int | None = None
    batch_id: int | None = None
    strength: float | None = None       # 缓存：单丝=MPa；纺织=cN/dtex
    strength_mpa: float | None = None   # 缓存：纺织有密度时的 MPa 换算值，否则 None


@dataclass
class Batch:
    """一个测试批次。同一批次内只允许一种模式。"""

    batch_name: str
    mode: str
    fiber_type: str | None = None
    density: float | None = None    # g/cm³，纺织模式可选
    remark: str | None = None
    created_at: str | None = None
    id: int | None = None
    sample_count: int = 0           # 列表查询时填充，非库表字段
    samples: list = field(default_factory=list)


@dataclass
class AnalysisResult:
    """批量统计结果。样本数 < 2 时 std 与 cv_percent 为 None（无统计意义）。"""

    n: int
    mean: float
    std: float | None
    cv_percent: float | None
    min_val: float
    max_val: float


@dataclass
class WeibullResult:
    """Weibull 拟合结果（2 参数或 3 参数）。

    m：Weibull 模数（形状参数，无量纲）；
    sigma0：特征强度（尺度参数，失效概率 63.2% 处），单位与输入强度一致；
    gamma：位置参数（3 参数 Weibull），2 参数时为 0；
    x：ln(σ−γ)（3 参数）或 ln(σ)（2 参数）。
    """

    m: float
    sigma0: float
    r2: float
    strengths_sorted: list
    median_ranks: list      # F̂ᵢ：按 rank_method 计算的累计失效概率
    x: list                 # ln(σ−γ) 或 ln(σ)
    y: list                 # ln(-ln(1-F̂))
    gamma: float = 0.0
    steps: list = field(default_factory=list)   # 计算过程（MLE/3 参数用）
    rank_method: str = "hazen"                 # Weibull 绘图位置方法
    strength_unit: str = ""                   # 空值表示调用方的原始强度单位


@dataclass
class RowError:
    """导入文件时单行数据的错误信息。row_number 从 1 开始（1 为表头行）。"""

    row_number: int
    message: str
    column: str | None = None
    raw_value: object = None
