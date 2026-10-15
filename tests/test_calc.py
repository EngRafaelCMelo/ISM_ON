import numpy as np
import pytest

from calc import (
    bulk_volume_cylinder,
    estimate_alpha_from_decay,
    permeability_darcy,
    permeability_pulse_decay,
    porosity_from_p1_p2,
    differential_pressures,
)


def test_measured_and_calculated_dp_are_distinct_and_invalid_is_not_reused():
    result = differential_pressures(2, "bar", 10, "bar", 3, "bar")
    assert result["measured_pa"] == pytest.approx(2e5)
    assert result["calculated_pa"] == pytest.approx(7e5)
    invalid = differential_pressures(99, "bar", None, "bar", 3, "bar", upstream_status="INVALID")
    assert invalid == {"measured_pa": 99e5, "calculated_pa": None}


def test_porosity_model_returns_fraction_and_percent():
    result = porosity_from_p1_p2(50e5, 30e5, 10e-6, 20e-6, bulk_volume_cylinder(0.0254, 0.05))
    assert result["phi"] == pytest.approx(0.4737, rel=1e-3)
    assert result["phi_percent"] == pytest.approx(result["phi"] * 100)


def test_darcy_permeability_uses_pa_and_rejects_gas_model():
    result = permeability_darcy(1e-9, 1e-3, 0.05, 0.01, 1e5)
    assert result["k_m2"] > 0
    with pytest.raises(ValueError):
        permeability_darcy(1e-9, 1e-3, 0.05, 0.01, 1e5, "gas_pulse_decay")


def test_pulse_decay_and_alpha_estimation():
    t = np.linspace(0, 30, 301)
    d_p = 5e5 * np.exp(-0.05 * t)
    alpha = estimate_alpha_from_decay(t, d_p)
    result = permeability_pulse_decay(alpha, 1.78e-5, 0.05, 1e-4, 20e5, 10e-6, 10e-6)
    assert alpha == pytest.approx(0.05, rel=1e-3)
    assert result["k_mD"] > 0


def test_invalid_calculation_inputs_are_rejected():
    with pytest.raises(ValueError):
        bulk_volume_cylinder(0, 0.05)
    with pytest.raises(ValueError):
        porosity_from_p1_p2(1e5, 2e5, 1e-5, 2e-5, 1e-5)
