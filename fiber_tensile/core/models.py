"""数据模型定义：纯 dataclass 与模式常量，无外部依赖。"""

from dataclasses import dataclass, field

# 模式常量（与数据库 CHECK 约束保持一致）
MODE_FILAMENT = "filament"  # 单丝模式：按直径计算 σ = 4F/(πd²)，MPa/GPa
MODE_TEXTILE = "textile"    # 纺织纤维模式：断裂强度 = F/线密度，cN/dtex

VALID_MODES = (MODE_FILAMENT, MODE_TEXTILE)
VALID_FORCE_UNITS = ("cN", "N", "mN")

# 模式显示名（UI 用）
MODE_LABELS = {
    MODE_FILAMENT: "单丝模式",
    MODE_TEXTILE: "纺织纤维模式",
}


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
    sort_order: int = 0
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
    """2 参数 Weibull 拟合结果。

    m：Weibull 模数（形状参数，无量纲）；
    sigma0：特征强度（尺度参数，失效概率 63.2% 处），单位与输入强度一致。
    """

    m: float
    sigma0: float
    r2: float
    strengths_sorted: list
    median_ranks: list      # F̂ᵢ = (i-0.5)/N
    x: list                 # ln(σ)
    y: list                 # ln(-ln(1-F̂))


@dataclass
class RowError:
    """导入文件时单行数据的错误信息。row_number 从 1 开始（1 为表头行）。"""

    row_number: int
    message: str
    column: str | None = None
    raw_value: object = None


def strength_unit_label(mode: str) -> str:
    """强度的本征单位标签：单丝=MPa，纺织=cN/dtex。"""
    if mode == MODE_FILAMENT:
        return "MPa"
    if mode == MODE_TEXTILE:
        return "cN/dtex"
    raise ValueError(f"未知模式：{mode!r}")
