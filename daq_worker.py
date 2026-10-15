from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from calibration_store import apply_channel_cal, ensure_channel, load_calibration
from config import load_config, resolve_relative_path
from logger_csv import CsvLogger
from units import mA_to_engineering


@dataclass
class ChannelCfg:
    name: str
    physical: str
    lrv: float
    urv: float
    unit: str = "bar"


def mA_to_eng(mA: float, lrv: float, urv: float) -> float:
    """Compatibilidade com o nome usado pelo codigo legado."""
    return mA_to_engineering(mA, lrv, urv)


class DaqWorker(QObject):
    data = pyqtSignal(dict)
    error = pyqtSignal(str)
    started = pyqtSignal()
    stopped = pyqtSignal()

    def __init__(self, config_path: str, calibration_path: str = "calibration.json"):
        super().__init__()
        self.config_path = config_path
        self.calibration_path = resolve_relative_path(config_path, calibration_path)
        self._task = None
        self._reader = None
        self._timer: Optional[QTimer] = None
        self._logger: Optional[CsvLogger] = None
        self._cfg: Dict[str, Any] = {}
        self._channels: List[ChannelCfg] = []
        self._rate_hz = 10.0
        self._open_loop_low = 3.6
        self._overrange_high = 21.0
        self._cal: Dict[str, Any] = {}
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def _load_config(self):
        self._cfg = load_config(self.config_path)
        self._rate_hz = float(self._cfg.get("sample_rate_hz", 10.0))
        limits = self._cfg.get("limits_mA", {})
        self._open_loop_low = float(limits.get("open_loop_low_mA", 3.6))
        self._overrange_high = float(limits.get("overrange_high_mA", 21.0))
        self._channels = [
            ChannelCfg(
                name=channel["name"],
                physical=channel["physical"],
                lrv=float(channel["lrv"]),
                urv=float(channel["urv"]),
                unit=channel.get("unit", "bar"),
            )
            for channel in self._cfg["channels"]
        ]

    @pyqtSlot()
    def start(self):
        if self._active:
            return
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType
            from nidaqmx.stream_readers import AnalogMultiChannelReader

            self._load_config()
            self._cal = load_calibration(self.calibration_path)
            for channel in self._channels:
                ensure_channel(self._cal, channel.name)

            self._task = nidaqmx.Task(new_task_name="PressureSupervisor")
            for channel in self._channels:
                self._task.ai_channels.add_ai_current_chan(
                    physical_channel=channel.physical,
                    name_to_assign_to_channel=channel.name,
                    min_val=0.0,
                    max_val=0.02,
                )
            self._task.timing.cfg_samp_clk_timing(
                rate=self._rate_hz,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=int(max(self._rate_hz, 10)),
            )
            self._reader = AnalogMultiChannelReader(self._task.in_stream)

            csv_cfg = self._cfg.get("csv", {})
            if bool(csv_cfg.get("enabled", True)):
                folder = resolve_relative_path(
                    self.config_path, str(csv_cfg.get("folder", "logs"))
                )
                self._logger = CsvLogger(
                    folder,
                    str(csv_cfg.get("file_prefix", "pressao")),
                    [channel.name for channel in self._channels],
                )

            self._timer = QTimer(self)
            self._timer.setInterval(max(1, int(1000 / self._rate_hz)))
            self._timer.timeout.connect(self._read_once)
            self._task.start()
            self._active = True
            self._timer.start()
            self.started.emit()
        except Exception as exc:
            self._cleanup()
            self.error.emit(f"Falha ao iniciar DAQ: {exc}")
            self.stopped.emit()

    @pyqtSlot()
    def stop(self):
        was_active = self._active or self._task is not None or self._timer is not None
        self._active = False
        self._cleanup()
        if was_active:
            self.stopped.emit()

    def _cleanup(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if self._task is not None:
            try:
                self._task.stop()
            except Exception:
                pass
            try:
                self._task.close()
            except Exception:
                pass
            self._task = None
        self._reader = None
        if self._logger is not None:
            self._logger.close()
            self._logger = None

    def _read_once(self):
        if not self._active or self._reader is None or self._task is None:
            return
        try:
            n_channels = len(self._channels)
            data_a = np.zeros((n_channels, 1), dtype=np.float64)
            self._reader.read_many_sample(
                data=data_a,
                number_of_samples_per_channel=1,
                timeout=0.3,
            )
            currents_mA = (data_a[:, 0] * 1000.0).tolist()
            eng_raw: list[Optional[float]] = []
            eng_corr: list[Optional[float]] = []
            statuses: list[str] = []
            channel_payload: dict[str, dict[str, Any]] = {}

            for index, channel in enumerate(self._channels):
                current = float(currents_mA[index])
                if not math.isfinite(current):
                    status = "INVALID"
                    raw = None
                    corrected = None
                else:
                    if current < self._open_loop_low:
                        status = "OPEN_LOOP"
                    elif current > self._overrange_high:
                        status = "OVERRANGE"
                    else:
                        status = "OK"
                    raw = float(mA_to_eng(current, channel.lrv, channel.urv))
                    corrected = (
                        float(apply_channel_cal(self._cal, channel.name, raw))
                        if status == "OK"
                        else None
                    )
                eng_raw.append(raw)
                eng_corr.append(corrected)
                statuses.append(status)
                channel_payload[channel.name] = {
                    "mA": current,
                    "eng_raw": raw,
                    "eng": corrected,
                    "status": status,
                    "unit": channel.unit,
                }

            now = datetime.now().astimezone()
            timestamp = now.isoformat(timespec="milliseconds")
            payload = {
                "ts": timestamp,
                "timestamp_ms": int(now.timestamp() * 1000),
                "mA": currents_mA,
                "eng_raw": eng_raw,
                "eng": eng_corr,
                "status": statuses,
                "channels": channel_payload,
                "source": "REAL",
                "simulated": False,
            }
            if self._logger:
                self._logger.write_row(
                    timestamp,
                    currents_mA,
                    eng_corr,
                    statuses=statuses,
                    eng_raw=eng_raw,
                )
            self.data.emit(payload)
        except Exception as exc:
            self.error.emit(f"Erro de leitura: {exc}")
            self.stop()
