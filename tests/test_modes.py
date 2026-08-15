"""core/modes.py 计算模式注册表测试。"""

import pytest

from fiber_tensile.core.modes import (
    MODES,
    MODE_FILAMENT,
    MODE_TEXTILE,
    VALID_MODES,
    get_mode_spec,
    strength_unit_label,
)


def test_registry_complete():
    assert set(MODES) == set(VALID_MODES)
    assert MODE_FILAMENT in MODES and MODE_TEXTILE in MODES
    for key, spec in MODES.items():
        assert spec.key == key
        assert spec.label and spec.strength_unit
        assert spec.dim_field and spec.dim_label
        assert callable(spec.compute)
        assert spec.dim_default > 0
        assert len(spec.dim_range) == 2 and spec.dim_range[0] < spec.dim_range[1]


def test_get_mode_spec_unknown_raises():
    with pytest.raises(ValueError):
        get_mode_spec("foobar")


def test_spec_compute_anchors():
    # 锚点：10 cN/7 μm → 2598.45 MPa；10 cN/2 dtex → 5 cN/dtex；×ρ1.14 → 570 MPa
    s, smpa = get_mode_spec(MODE_FILAMENT).compute(10.0, 7.0, None)
    assert s == pytest.approx(2598.45, rel=1e-3)
    assert smpa is None

    s, smpa = get_mode_spec(MODE_TEXTILE).compute(10.0, 2.0, None)
    assert s == pytest.approx(5.0)
    assert smpa is None
    s, smpa = get_mode_spec(MODE_TEXTILE).compute(10.0, 2.0, 1.14)
    assert smpa == pytest.approx(570.0)


def test_spec_compute_invalid_dim_raises():
    with pytest.raises(ValueError):
        get_mode_spec(MODE_FILAMENT).compute(10.0, 0.0, None)


def test_strength_unit_label_from_registry():
    assert strength_unit_label(MODE_FILAMENT) == "MPa"
    assert strength_unit_label(MODE_TEXTILE) == "cN/dtex"
    with pytest.raises(ValueError):
        strength_unit_label("x")


def test_models_reexports_unchanged():
    """models.py 再导出保持旧导入路径兼容。"""
    from fiber_tensile.core import models

    assert models.MODE_FILAMENT == MODE_FILAMENT
    assert models.MODE_TEXTILE == MODE_TEXTILE
    assert models.VALID_MODES == VALID_MODES
    assert models.MODE_LABELS == {MODE_FILAMENT: "单丝模式",
                                  MODE_TEXTILE: "纺织纤维模式"}


def test_config_reexports_ranges():
    """config.py 再导出数值范围保持旧导入路径兼容。"""
    from fiber_tensile import config
    from fiber_tensile.core import modes

    assert config.RANGE_DIAMETER_UM == modes.RANGE_DIAMETER_UM
    assert config.RANGE_LINEAR_DENSITY_DTEX == modes.RANGE_LINEAR_DENSITY_DTEX
