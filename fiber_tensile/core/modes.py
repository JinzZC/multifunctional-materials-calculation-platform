"""计算模式注册表：每种计算模式的单一事实来源。

新增计算模式/参数时，只需：
    1. 在 MODES 里加一条 ModeSpec（标签、单位、维度字段、范围、公式）；
    2. 写对应的公式函数（core/formulas.py）。
录入表单、导入校验、报告列、单位标签均从本注册表生成。

注意：数据库 batches.mode 的 CHECK 约束是冻结的 v1 结构（见 data/db.py 的迁移规则），
新增模式时需追加 v2 迁移重建 batches 表放宽约束。
"""

from dataclasses import dataclass
from typing import Callable

MODE_FILAMENT = "filament"  # 单丝模式：按直径计算 σ = 4F/(πd²)，MPa/GPa
MODE_TEXTILE = "textile"    # 纺织纤维模式：断裂强度 = F/线密度，cN/dtex

# 数值合理范围（超出仅警告，不阻断录入）
RANGE_DIAMETER_UM = (0.1, 1000.0)
RANGE_FORCE_CN = (0.001, 100000.0)
RANGE_LINEAR_DENSITY_DTEX = (0.05, 100000.0)
RANGE_DENSITY_GCM3 = (0.5, 3.5)


@dataclass(frozen=True)
class ModeSpec:
    """一种计算模式的完整规格。"""

    key: str                 # 模式标识（存数据库）
    label: str               # 中文显示名
    strength_unit: str       # 强度的本征单位
    dim_field: str           # Sample 上维度字段名（直径/线密度）
    dim_label: str           # 维度显示名（表头/表单/错误提示用）
    dim_default: float       # 录入表单默认值
    dim_range: tuple         # 维度常见范围（超出仅警告）
    uses_density: bool       # 密度是否参与换算（纺织=是）
    compute: Callable        # compute(force_cn, dim_value, density) -> (strength, strength_mpa)


def _filament_compute(force_cn: float, dim: float, density: float | None) -> tuple:
    from .formulas import filament_strength_mpa
    return filament_strength_mpa(force_cn, dim), None


def _textile_compute(force_cn: float, dim: float, density: float | None) -> tuple:
    from .formulas import tenacity_to_mpa, textile_tenacity_cn_dtex
    tenacity = textile_tenacity_cn_dtex(force_cn, dim)
    mpa = tenacity_to_mpa(tenacity, density) if density is not None else None
    return tenacity, mpa


MODES: dict[str, ModeSpec] = {
    MODE_FILAMENT: ModeSpec(
        key=MODE_FILAMENT, label="单丝模式", strength_unit="MPa",
        dim_field="diameter_um", dim_label="直径(μm)",
        dim_default=7.0, dim_range=RANGE_DIAMETER_UM,
        uses_density=False, compute=_filament_compute),
    MODE_TEXTILE: ModeSpec(
        key=MODE_TEXTILE, label="纺织纤维模式", strength_unit="cN/dtex",
        dim_field="linear_density_dtex", dim_label="线密度(dtex)",
        dim_default=1.5, dim_range=RANGE_LINEAR_DENSITY_DTEX,
        uses_density=True, compute=_textile_compute),
}

VALID_MODES = tuple(MODES)
MODE_LABELS = {key: spec.label for key, spec in MODES.items()}


def get_mode_spec(mode: str) -> ModeSpec:
    """按模式标识取规格，未知模式抛 ValueError。"""
    try:
        return MODES[mode]
    except KeyError:
        raise ValueError(f"未知模式：{mode!r}（仅支持 {VALID_MODES}）") from None


def strength_unit_label(mode: str) -> str:
    """强度的本征单位标签（从注册表取）。"""
    return get_mode_spec(mode).strength_unit
