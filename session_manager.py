"""Registro assicrono, rastreavel e separado por ensaio."""

from __future__ import annotations

import csv
import json
import os
import queue
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _safe_name(value: str, default: str = "ensaio") -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return value.strip("_.") or default


class SessionRecorder:
    """Writer de ensaio em thread propria; filas preservam dados durante a UI."""

    def __init__(self, base_dir: str = "ensaios"):
        self.base_dir = os.path.abspath(base_dir)
        self.path: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_marker = object()
        self._active = False
        self._lock = threading.Lock()
        self._error: Optional[Exception] = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def error(self) -> Optional[Exception]:
        return self._error

    def start(
        self,
        session_id: str,
        sample_name: str,
        operator: str,
        notes: str,
        test_type: str,
        parameters: Dict[str, Any],
        sensor_config: Any,
        calibration: Any,
        source: str,
        simulated: bool,
    ) -> str:
        if self.active:
            raise RuntimeError("Ja existe um ensaio ativo.")
        for field_name, field_value in {
            "session_id": session_id,
            "sample_name": sample_name,
            "operator": operator,
            "test_type": test_type,
        }.items():
            if not isinstance(field_value, str):
                raise ValueError(f"{field_name} deve ser texto.")
        source = str(source).upper()
        simulated = bool(simulated)
        if source not in {"REAL", "SIMULATED"}:
            raise ValueError("A origem do ensaio deve ser REAL ou SIMULATED.")
        if simulated != (source == "SIMULATED"):
            raise ValueError("Origem e indicador de simulacao sao inconsistentes.")
        self._queue = queue.Queue()
        started = datetime.now().astimezone()
        folder = f"{started:%Y-%m-%d}_{_safe_name(sample_name)}_{uuid.uuid4().hex[:8]}"
        self.path = os.path.join(self.base_dir, folder)
        os.makedirs(self.path, exist_ok=False)
        self.metadata = {
            "session_id": session_id.strip() or uuid.uuid4().hex,
            "sample_name": sample_name.strip(),
            "operator": operator.strip(),
            "notes": notes.strip(),
            "test_type": test_type,
            "started_at": started.isoformat(timespec="milliseconds"),
            "ended_at": None,
            "duration_s": None,
            "source": source,
            "simulated": simulated,
            "parameters": parameters,
            "sensor_config": sensor_config,
            "calibration": calibration,
        }
        self._write_json("metadata.json", self.metadata)
        self._write_text("events.log", "")
        with self._lock:
            self._active = True
            self._error = None
        self._thread = threading.Thread(target=self._writer_loop, name="session-writer", daemon=True)
        self._thread.start()
        self.record_event("SESSION", "INFO", "Ensaio iniciado", "SESSION_STARTED")
        return self.path

    def _write_json(self, name: str, data: Any) -> None:
        target = os.path.join(self.path or self.base_dir, name)
        temporary = None
        try:
            with open(target + ".tmp", "w", encoding="utf-8") as file:
                temporary = file.name
                json.dump(data, file, indent=2, ensure_ascii=False, default=str)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def _write_text(self, name: str, data: str) -> None:
        with open(os.path.join(self.path or self.base_dir, name), "w", encoding="utf-8") as file:
            file.write(data)

    def _append_event_now(self, event: Dict[str, Any]) -> None:
        """Persiste um evento diretamente quando o writer nao esta disponivel."""
        if not self.path:
            return
        with open(os.path.join(self.path, "events.log"), "a", encoding="utf-8") as events_file:
            events_file.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_file.flush()

    def record_event(self, source: str, severity: str, message: str, code: str = "") -> None:
        if self.active:
            self._queue.put(("event", {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "source": source, "severity": severity, "message": message, "code": code,
            }))

    def record(self, payload: Dict[str, Any], derived: Optional[Dict[str, Any]] = None) -> None:
        if self.active:
            expected_source = self.metadata.get("source", "REAL")
            expected_simulated = bool(self.metadata.get("simulated", False))
            payload_source = str(payload.get("source", "SIMULATED" if payload.get("simulated") else "REAL")).upper()
            payload_simulated = bool(payload.get("simulated", payload_source == "SIMULATED"))
            if payload_source != expected_source or payload_simulated != expected_simulated:
                self.record_event(
                    "SESSION", "ERROR",
                    f"Amostra ignorada: origem {payload_source} incompativel com o ensaio {expected_source}.",
                    "SESSION_SOURCE_MISMATCH",
                )
                return
            self._queue.put(("measurement", (payload, derived or {})))

    def _writer_loop(self) -> None:
        file = None
        writer = None
        try:
            file = open(os.path.join(self.path or self.base_dir, "measurements.csv"), "w", newline="", encoding="utf-8")
            fields = ["timestamp_iso", "timestamp_ms", "source", "simulated"]
            channel_names = [str(item.get("name")) for item in self.metadata.get("sensor_config", []) if isinstance(item, dict)]
            for name in channel_names:
                fields.extend([f"{name}_mA", f"{name}_raw", f"{name}_calibrated", f"{name}_status"])
            fields.extend(["dp_measured", "dp_calculated", "flow_m3s", "temperature_c", "permeability_mD"])
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            file.flush()
            while True:
                kind, value = self._queue.get()
                if kind == "stop":
                    break
                if kind == "event":
                    with open(os.path.join(self.path or self.base_dir, "events.log"), "a", encoding="utf-8") as events_file:
                        events_file.write(json.dumps(value, ensure_ascii=False) + "\n")
                    continue
                payload, derived = value
                row = {
                    "timestamp_iso": payload.get("ts"),
                    "timestamp_ms": payload.get("timestamp_ms"),
                    "source": payload.get("source", "REAL"),
                    "simulated": payload.get("simulated", False),
                    "dp_measured": derived.get("dp_measured"),
                    "dp_calculated": derived.get("dp_calculated"),
                    "flow_m3s": derived.get("flow_m3s"),
                    "temperature_c": derived.get("temperature_c"),
                    "permeability_mD": derived.get("permeability_mD"),
                }
                for name, item in (payload.get("channels") or {}).items():
                    row[f"{name}_mA"] = item.get("mA")
                    row[f"{name}_raw"] = item.get("eng_raw")
                    row[f"{name}_calibrated"] = item.get("eng")
                    row[f"{name}_status"] = item.get("status")
                writer.writerow(row)
                file.flush()
        except Exception as exc:
            self._error = exc
            try:
                self._append_event_now({
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "source": "SESSION",
                    "severity": "ERROR",
                    "message": f"Falha no gravador do ensaio: {exc}",
                    "code": "SESSION_WRITER_ERROR",
                })
            except OSError:
                pass
        finally:
            if file is not None:
                file.close()

    def stop(self, reason: str = "Ensaio encerrado", timeout: float = 5.0) -> Optional[str]:
        if not self.active:
            return self.path
        ended = datetime.now().astimezone()
        started_text = self.metadata.get("started_at")
        try:
            started = datetime.fromisoformat(started_text) if started_text else ended
            duration = max(0.0, (ended - started).total_seconds())
        except (TypeError, ValueError):
            duration = None
        self.metadata["ended_at"] = ended.isoformat(timespec="milliseconds")
        self.metadata["duration_s"] = duration
        self.record_event("SESSION", "INFO", reason, "SESSION_STOPPED")
        self._queue.put(("stop", None))
        if self._thread is not None:
            self._thread.join(timeout)
        if self._thread is not None and self._thread.is_alive():
            self._error = TimeoutError("O gravador do ensaio nao encerrou no prazo.")
            try:
                self._append_event_now({
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "source": "SESSION",
                    "severity": "ERROR",
                    "message": str(self._error),
                    "code": "SESSION_WRITER_TIMEOUT",
                })
            except OSError:
                pass
        try:
            self._write_json("metadata.json", self.metadata)
        finally:
            with self._lock:
                self._active = False
        return self.path
