import pytest

import oven_worker
import pump_worker
from oven_worker import OvenWorker
from pump_worker import PumpWorker


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
