"""core/units.py 测试。"""

import pytest

from fiber_tensile.core.units import force_to_cn


def test_cn_passthrough():
    assert force_to_cn(1.0, "cN") == 1.0


def test_n_to_cn():
    assert force_to_cn(1.0, "N") == pytest.approx(100.0)


def test_mn_to_cn():
    assert force_to_cn(10.0, "mN") == pytest.approx(1.0)


def test_roundtrip():
    # cN → N → cN 往返一致
    assert force_to_cn(force_to_cn(250.0, "cN") / 100.0, "N") == pytest.approx(250.0)


def test_unknown_unit_raises():
    with pytest.raises(ValueError):
        force_to_cn(1.0, "kN")
