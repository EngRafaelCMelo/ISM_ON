import json

from calibration_store import apply_channel_cal, ensure_channel, load_calibration, save_calibration


def test_zero_span_calibration_and_atomic_metadata(tmp_path):
    path = tmp_path / "calibration.json"
    calibration = load_calibration(str(path))
    ensure_channel(calibration, "P1")
    calibration["channels"]["P1"] = {"a": 2.0, "b": -1.0}
    save_calibration(str(path), calibration)
    loaded = load_calibration(str(path))
    assert apply_channel_cal(loaded, "P1", 3.0) == 5.0
    assert loaded["metadata"]["updated_at_utc"]
    assert not list(tmp_path.glob(".calibration-*.tmp"))
