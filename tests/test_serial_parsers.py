import time

import pytest

import oven_worker
import pump_worker
from oven_worker import OvenWorker
from pump_worker import PumpWorker
from device_state import STALE


def test_pump_parser_accepts_valid_and_rejects_incomplete_messages():
    assert PumpWorker.parse_flow("FLOW: 1.23 ml/min") == pytest.approx(1.23e-6 / 60)
    assert PumpWorker.parse_flow("Q=0,5 ml/min") == pytest.approx(0.5e-6 / 60)
    assert PumpWorker.parse_flow("FLOW:") is None


def test_oven_parser_accepts_valid_and_rejects_incomplete_messages():
    assert OvenWorker.parse_temp("TEMP: 45.2") == pytest.approx(45.2)
    assert OvenWorker.parse_temp("PV:45,2") == pytest.approx(45.2)
    assert OvenWorker.parse_temp("PV:") is None


def test_workers_return_cleanly_without_serial_hardware(monkeypatch):
    monkeypatch.setattr(pump_worker, "serial", None)
    monkeypatch.setattr(oven_worker, "serial", None)
    PumpWorker().run()
    OvenWorker().run()


def test_serial_settings_and_stale_state_are_validated():
    with pytest.raises(ValueError):
        PumpWorker(port="", baudrate=9600, timeout_s=1, stale_after_s=3)
    with pytest.raises(ValueError):
        PumpWorker(timeout_s=float("nan"))
    with pytest.raises(ValueError):
        OvenWorker(stale_after_s=float("inf"))
    worker = PumpWorker()
    states = []
    worker.state.connect(states.append)
    worker._connected_at = time.monotonic() - 10
    worker._mark_stale_if_needed()
    assert states[-1] == STALE
