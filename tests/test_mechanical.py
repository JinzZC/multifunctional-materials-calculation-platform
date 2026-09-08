from dataclasses import replace
import math

import numpy as np
import pytest

from fiber_tensile.mechanical.core import Spec, analyze, summarize


def test_tensile_known_modulus_stress_and_energy():
    strain = np.linspace(0, .02, 201)
    result = analyze(strain, 3000 * strain * 20, Spec(target_pct=1))
    assert result.modulus_gpa == pytest.approx(3)
    assert result.strength_mpa == pytest.approx(60)
    assert result.peak_strain_pct == pytest.approx(2)
    assert result.target_stress_mpa == pytest.approx(30)
    assert result.work_to_peak_mj_m3 == pytest.approx(.6)
    assert result.r2 == pytest.approx(1)


@pytest.mark.parametrize("section, area", [("rectangle", 20), ("circle", math.pi * 25 / 4), ("area", 17)])
def test_geometry_and_extension(section, area):
    strain = np.linspace(0, .01, 101)
    spec = Spec(section=section, area_mm2=17, source="extension", gauge_mm=25)
    r = analyze(strain * 25, strain * 70000 * area, spec)
    assert r.modulus_gpa == pytest.approx(70)
    assert r.strength_mpa == pytest.approx(700)


def test_peak_is_not_fracture_and_fit_excludes_post_peak():
    x = np.linspace(0, .02, 201)
    force = np.minimum(x * 60000, 600)
    force[150:] = 100
    r = analyze(x, force, Spec(target_pct=1.8))
    assert r.peak_index == 100  # first plateau point
    assert r.end_strain_pct == 2
    assert r.peak_strain_pct == 1
    assert r.target_stress_mpa is None
    assert max(r.fit_indices) < r.peak_index
    assert r.fracture_strain_pct is None
    confirmed = analyze(x, force, Spec(fracture_point=150))
    assert confirmed.fracture_strain_pct == pytest.approx(x[149] * 100)
    assert confirmed.fracture_stress_mpa == 30
    with pytest.raises(ValueError, match="断裂点"):
        analyze(x, force, Spec(fracture_point=20))
    with pytest.raises(ValueError, match="断裂点"):
        analyze(x, force, Spec(fracture_point=999))


def test_selected_fit_interval_controls_modulus():
    x = np.linspace(0, .02, 201)
    stress = np.where(x <= .005, x * 3000, 15 + (x - .005) * 1000)
    early = analyze(x, stress * 20, Spec())
    later = analyze(x, stress * 20, Spec(fit_lo=.6, fit_hi=1.0))
    assert early.modulus_gpa == pytest.approx(3)
    assert later.modulus_gpa == pytest.approx(1)


@pytest.mark.parametrize("changes", [
    {"width_mm": 0}, {"fit_hi": .01}, {"fit_hi": float("nan")},
    {"fit_mode": "force", "fit_hi": 101}, {"target_pct": -1},
    {"mode": "bend4", "source": "deflection"},
    {"mode": "bend3", "source": "crosshead"},
])
def test_invalid_parameters(changes):
    x = np.linspace(0, .01, 101)
    with pytest.raises(ValueError):
        analyze(x, x * 60000, replace(Spec(), **changes))


@pytest.mark.parametrize("problem", ["nan", "negative", "reversal", "constant", "short", "shape"])
def test_invalid_curves(problem):
    x = np.linspace(0, .01, 101)
    force = x * 60000
    if problem == "nan": force[10] = np.nan
    if problem == "negative": force[10] = -1
    if problem == "reversal": x[10] = 0
    if problem == "constant": force[:] = 1
    if problem == "short": x, force = x[:3], force[:3]
    if problem == "shape": x, force = x.reshape(1, -1), force.reshape(1, -1)
    with pytest.raises(ValueError):
        analyze(x, force, Spec())


def test_crosshead_warning_and_no_extrapolated_work():
    strain = np.linspace(.001, .01, 101)
    r = analyze(strain * 50, strain * 60000, Spec(source="crosshead"))
    assert any("表观" in w for w in r.warnings)
    assert r.work_to_peak_mj_m3 == pytest.approx(1500 * (.01**2 - .001**2))
    assert summarize([r])["modulus_gpa"]["sd"] is None
    r2 = analyze(strain * 50, strain * 120000, Spec(source="crosshead"))
    stats = summarize([r, r2])["modulus_gpa"]
    assert stats["mean"] == pytest.approx(4.5)
    assert stats["sd"] == pytest.approx(3 / math.sqrt(2))
