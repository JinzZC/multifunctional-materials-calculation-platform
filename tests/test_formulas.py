"""core/formulas.py 测试。"""

import math

import pytest

from fiber_tensile.core.formulas import (
    compute_strength,
    filament_strength_mpa,
    mpa_to_gpa,
    tenacity_to_mpa,
    textile_tenacity_cn_dtex,
)
from fiber_tensile.core.models import MODE_FILAMENT, MODE_TEXTILE


def test_filament_anchor():
    # 锚点：F=10 cN、d=7 μm → 2598.5 MPa
    assert filament_strength_mpa(10.0, 7.0) == pytest.approx(2598.5, rel=1e-3)


def test_filament_matches_direct_formula():
    f_cn, d_um = 25.0, 12.5
    expected = 4 * (f_cn * 0.01) / (math.pi * (d_um * 1e-6) ** 2) / 1e6
    assert filament_strength_mpa(f_cn, d_um) == pytest.approx(expected)


def test_mpa_to_gpa():
    assert mpa_to_gpa(filament_strength_mpa(10.0, 7.0)) == pytest.approx(2.5985, rel=1e-3)


def test_textile_anchor():
    # F=10 cN、Tt=2 dtex → 5 cN/dtex
    assert textile_tenacity_cn_dtex(10.0, 2.0) == pytest.approx(5.0)


def test_tenacity_to_mpa_anchor():
    # 锚点：5 cN/dtex、ρ=1.14 g/cm³ → 570 MPa
    assert tenacity_to_mpa(5.0, 1.14) == pytest.approx(570.0)


def test_compute_strength_filament():
    strength, strength_mpa = compute_strength(MODE_FILAMENT, 10.0, diameter_um=7.0)
    assert strength == pytest.approx(2598.5, rel=1e-3)
    assert strength_mpa is None


def test_compute_strength_textile_with_density():
    strength, strength_mpa = compute_strength(
        MODE_TEXTILE, 10.0, linear_density_dtex=2.0, density_gcm3=1.14)
    assert strength == pytest.approx(5.0)
    assert strength_mpa == pytest.approx(570.0)


def test_compute_strength_textile_without_density():
    strength, strength_mpa = compute_strength(
        MODE_TEXTILE, 10.0, linear_density_dtex=2.0)
    assert strength == pytest.approx(5.0)
    assert strength_mpa is None


@pytest.mark.parametrize("kwargs", [
    dict(force_cn=0.0, diameter_um=7.0),
    dict(force_cn=-1.0, diameter_um=7.0),
    dict(force_cn=10.0, diameter_um=0.0),
    dict(force_cn=float("nan"), diameter_um=7.0),
    dict(force_cn=float("inf"), diameter_um=7.0),
])
def test_filament_invalid_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        filament_strength_mpa(**kwargs)


def test_compute_strength_missing_required_field():
    with pytest.raises(ValueError):
        compute_strength(MODE_FILAMENT, 10.0)
    with pytest.raises(ValueError):
        compute_strength(MODE_TEXTILE, 10.0)


def test_compute_strength_unknown_mode():
    with pytest.raises(ValueError):
        compute_strength("foobar", 10.0, diameter_um=7.0)
