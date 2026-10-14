import csv
import json

from session_manager import SessionRecorder


def test_session_isolated_and_simulation_is_explicit(tmp_path):
    recorder = SessionRecorder(str(tmp_path / "ensaios"))
    path = recorder.start(
        session_id="ensaio-001",
        sample_name="amostra 001",
        operator="operador",
        notes="teste",
        test_type="Coreflooding",
        parameters={"diameter_m": 0.01},
        sensor_config=[{"name": "P1"}, {"name": "DP"}],
        calibration={"channels": {}},
        source="SIMULATED",
        simulated=True,
    )
    recorder.record({
        "ts": "2026-10-14T12:00:00+00:00", "timestamp_ms": 1,
        "source": "SIMULATED", "simulated": True,
        "channels": {
            "P1": {"mA": 12, "eng_raw": 5, "eng": 5, "status": "OK"},
            "DP": {"mA": 12, "eng_raw": 2, "eng": 2, "status": "OK"},
        },
    }, {"dp_measured": 2, "dp_calculated": 3})
    recorder.record_event("DAQ", "WARNING", "teste", "TEST")
    recorder.stop()

    metadata = json.loads((tmp_path / "ensaios" / path.split("\\")[-1] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["simulated"] is True
    rows = list(csv.DictReader(open(path + "/measurements.csv", encoding="utf-8", newline="")))
    assert rows[0]["P1_raw"] == "5"
    assert rows[0]["dp_calculated"] == "3"
    assert "TEST" in (tmp_path / "ensaios" / path.split("\\")[-1] / "events.log").read_text(encoding="utf-8")
