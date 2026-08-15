"""composites/core.py 混合法则与体积分数测试。"""

import pytest

from fiber_tensile.composites.core import (
    compute_rom,
    compute_vf_acid,
    compute_vf_density,
)


def test_rom_anchors():
    # T300/环氧典型值：Ef=230, Em=3.5, Gf=20, Gm=1.3, νf=0.2, νm=0.35,
    # ρf=1.76, ρm=1.2, Vf=0.6
    r = compute_rom(230.0, 3.5, 20.0, 1.3, 0.2, 0.35, 1.76, 1.2, 0.6)
    assert r.e1_gpa == pytest.approx(230 * 0.6 + 3.5 * 0.4)       # 139.4
    assert r.e2_gpa == pytest.approx(230 * 3.5 / (0.6 * 3.5 + 0.4 * 230))
    assert r.g12_gpa == pytest.approx(20 * 1.3 / (0.6 * 1.3 + 0.4 * 20))
    assert r.nu12 == pytest.approx(0.2 * 0.6 + 0.35 * 0.4)        # 0.26
    assert r.rho_gcm3 == pytest.approx(1.76 * 0.6 + 1.2 * 0.4)    # 1.536
    assert r.vm == pytest.approx(0.4)
    assert any("纵向模量" in s for s in r.steps)
    assert any("横向模量" in s for s in r.steps)


def test_rom_validation():
    with pytest.raises(ValueError, match="V_f"):
        compute_rom(230, 3.5, 20, 1.3, 0.2, 0.35, 1.76, 1.2, 1.5)
    with pytest.raises(ValueError, match="泊松比"):
        compute_rom(230, 3.5, 20, 1.3, 0.9, 0.35, 1.76, 1.2, 0.6)
    with pytest.raises(ValueError, match="E_f"):
        compute_rom(0.5, 3.5, 20, 1.3, 0.2, 0.35, 1.76, 1.2, 0.6)


def test_vf_density_anchor():
    r = compute_vf_density(1.55, 1.76, 1.2)
    assert r.vf == pytest.approx(0.35 / 0.56, rel=1e-9)    # 0.625
    assert r.vm == pytest.approx(0.375)
    assert r.vv is None


def test_vf_density_validation():
    # ρ_c 不在 ρ_m 与 ρ_f 之间
    with pytest.raises(ValueError, match="密度法要求"):
        compute_vf_density(1.1, 1.76, 1.2)
    with pytest.raises(ValueError, match="密度法要求"):
        compute_vf_density(1.9, 1.76, 1.2)


def test_vf_acid_anchor():
    # wf=0.65, ρf=1.76, ρm=1.2, ρc=1.5
    r = compute_vf_acid(0.65, 1.76, 1.2, 1.5)
    term = 0.65 / 1.76 + 0.35 / 1.2
    assert r.vf == pytest.approx((0.65 / 1.76) / term, rel=1e-9)
    assert r.vv == pytest.approx(1.0 - 1.5 * term, rel=1e-6)
    assert r.vv > 0
    assert r.vm == pytest.approx(1 - r.vf - r.vv)
    assert any("孔隙率" in s for s in r.steps)


def test_vf_acid_negative_porosity_raises():
    # 孔隙率出现负值 → 数据不一致，应报错
    with pytest.raises(ValueError, match="孔隙率"):
        compute_vf_acid(0.65, 1.76, 1.2, 1.55)


def test_vf_acid_validation():
    with pytest.raises(ValueError, match="w_f"):
        compute_vf_acid(1.5, 1.76, 1.2, 1.5)
