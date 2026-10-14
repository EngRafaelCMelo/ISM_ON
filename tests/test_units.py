import math

import pytest

from daq_worker import mA_to_eng
from units import convert_pressure, flow_to_m3s, mA_to_engineering, pressure_to_pa


def test_current_4_20_ma_maps_to_sensor_range():
    assert mA_to_engineering(4.0, 0, 10000) == pytest.approx(0.0)
    assert mA_to_engineering(12.0, 0, 10000) == pytest.approx(5000.0)
    assert mA_to_eng(20.0, 0, 10000) == pytest.approx(10000.0)


def test_pressure_conversions_are_centralized():
    assert pressure_to_pa(1, "bar") == pytest.approx(100000.0)
    assert convert_pressure(1, "bar", "psi") == pytest.approx(14.5037738, rel=1e-6)
    assert convert_pressure(14.5037738, "psi", "bar") == pytest.approx(1.0, rel=1e-6)


def test_flow_conversion_to_si():
    assert flow_to_m3s(60, "ml/min") == pytest.approx(1e-6)
    assert flow_to_m3s(1, "l/min") == pytest.approx(1e-3 / 60)


def test_nonfinite_conversion_is_rejected():
    with pytest.raises(ValueError):
        mA_to_engineering(math.nan, 0, 100)
