from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from config import load_config
from units import mA_to_engineering


class SimulationWorker(QObject):
    """Fonte sintetica explicita; nunca representa uma leitura de hardware."""

    data = pyqtSignal(dict)
    error = pyqtSignal(str)
    started = pyqtSignal()
    stopped = pyqtSignal()

    def __init__(self, config_path: str):
        super().__init__()
        self.config_path = config_path
        self._timer = None
        self._channels: list[dict[str, Any]] = []
        self._rate_hz = 10.0
        self._started_at = time.monotonic()
        self._active = False

    @pyqtSlot()
    def start(self):
        if self._active:
            return
        try:
            config = load_config(self.config_path)
            self._channels = config["channels"]
            self._rate_hz = float(config.get("sample_rate_hz", 10.0))
            self._started_at = time.monotonic()
            self._timer = QTimer(self)
            self._timer.setInterval(max(1, int(1000 / self._rate_hz)))
            self._timer.timeout.connect(self._emit_sample)
            self._active = True
            self._timer.start()
            self.started.emit()
        except Exception as exc:
            self.error.emit(f"Falha ao iniciar simulacao: {exc}")
            self.stopped.emit()

    @pyqtSlot()
    def stop(self):
        was_active = self._active or self._timer is not None
        self._active = False
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if was_active:
            self.stopped.emit()

    def _emit_sample(self):
        if not self._active:
            return
        elapsed = time.monotonic() - self._started_at
        channel_payload = {}
        raw_values = []
        corrected_values = []
        statuses = []
        for index, channel in enumerate(self._channels):
            lrv = float(channel["lrv"])
            urv = float(channel["urv"])
            if channel["name"] == "DP":
                value = lrv + (urv - lrv) * (0.10 + 0.01 * math.sin(elapsed))
            else:
                value = lrv + (urv - lrv) * (0.20 + 0.02 * math.sin(elapsed + index))
            value = max(lrv, min(urv, value))
            current = 4.0 + 16.0 * (value - lrv) / (urv - lrv)
            raw_values.append(value)
            corrected_values.append(value)
            statuses.append("OK")
            channel_payload[channel["name"]] = {
                "mA": current,
                "eng_raw": value,
                "eng": value,
                "status": "OK",
                "unit": channel.get("unit", "bar"),
            }
        now = datetime.now().astimezone()
        self.data.emit(
            {
                "ts": now.isoformat(timespec="milliseconds"),
                "timestamp_ms": int(now.timestamp() * 1000),
                "mA": [item["mA"] for item in channel_payload.values()],
                "eng_raw": raw_values,
                "eng": corrected_values,
                "status": statuses,
                "channels": channel_payload,
                "source": "SIMULATED",
                "simulated": True,
            }
        )
