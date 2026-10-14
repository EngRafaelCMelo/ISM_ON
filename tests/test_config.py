import json

import pytest

from config import device_config, load_config, validate_config


def test_current_config_is_valid_and_keeps_explicit_sensor_ranges():
    config = load_config("config.json")
    assert [channel["name"] for channel in config["channels"]] == ["P1", "P2", "P3", "P4", "DP"]
    assert config["channels"][-1]["urv"] == 200
    assert device_config(config, "pump")["port"] == "COM5"


def test_duplicate_channels_and_unknown_mapping_are_rejected():
    base = {
        "sample_rate_hz": 10,
        "channels": [{"name": "P1", "physical": "dev/ai0", "lrv": 0, "urv": 10, "unit": "bar"}],
        "calculations": {"permeability": {"upstream_channel": "P9"}},
    }
    with pytest.raises(ValueError):
        validate_config(base)
    base["calculations"]["permeability"]["upstream_channel"] = "P1"
    base["channels"].append(base["channels"][0].copy())
    with pytest.raises(ValueError):
        validate_config(base)
