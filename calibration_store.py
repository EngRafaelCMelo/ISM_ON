import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any

DEFAULT_CAL = {
    "channels": {
        # "P1": {"a": 1.0, "b": 0.0},
    },
    "volumes": {
        "Vref_cm3": 10.0,
        "Vcell_cm3": 20.0,
        "Vu_cm3": 10.0,
        "Vd_cm3": 10.0,
    }
}

def load_calibration(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return json.loads(json.dumps(DEFAULT_CAL))
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "channels" not in data:
        data["channels"] = {}
    if "volumes" not in data:
        data["volumes"] = json.loads(json.dumps(DEFAULT_CAL["volumes"]))
    return data

def save_calibration(path: str, data: Dict[str, Any], create_backup: bool = True) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    if create_backup and os.path.exists(path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copy2(path, f"{path}.{stamp}.bak")
    data.setdefault("metadata", {})
    data["metadata"]["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, prefix=".calibration-", suffix=".tmp", delete=False
        ) as f:
            temp_path = f.name
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

def ensure_channel(cal: Dict[str, Any], name: str) -> None:
    cal.setdefault("channels", {})
    if name not in cal["channels"]:
        cal["channels"][name] = {"a": 1.0, "b": 0.0}

def apply_channel_cal(cal: Dict[str, Any], name: str, value_bar: float) -> float:
    ch = cal.get("channels", {}).get(name)
    if not ch:
        return value_bar
    a = float(ch.get("a", 1.0))
    b = float(ch.get("b", 0.0))
    return a * value_bar + b
