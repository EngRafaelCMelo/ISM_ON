from __future__ import annotations

import math
import re
import time

from PyQt5.QtCore import QThread, pyqtSignal

from device_state import CONNECTING, DISCONNECTED, ERROR, INVALID, OK, STALE

try:
    import serial
except Exception:
    serial = None


class OvenWorker(QThread):
    temp_received = pyqtSignal(float)
    raw_received = pyqtSignal(str)
    status = pyqtSignal(str)
    state = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, port="COM6", baudrate=9600, timeout_s=1.0, stale_after_s=3.0, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout_s = float(timeout_s)
        self.stale_after_s = float(stale_after_s)
        self._running = False
        self._ser = None
        self._last_valid_at = None
        self._connected_at = None
        self._backoff_s = 1.0

    def configure(self, port, baudrate, timeout_s, stale_after_s):
        if self.isRunning():
            raise RuntimeError("Nao e possivel alterar a estufa conectada.")
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.timeout_s = float(timeout_s)
        self.stale_after_s = float(stale_after_s)

    def start(self, priority=QThread.InheritPriority):
        if self.isRunning():
            return
        super().start(priority)

    def run(self):
        if serial is None:
            self._emit_error("pyserial nao esta instalado.")
            self.state.emit(DISCONNECTED)
            return
        self._running = True
        self._last_valid_at = None
        self._backoff_s = 1.0
        try:
            while self._running:
                if self._ser is None:
                    self.state.emit(CONNECTING)
                    self.status.emit(f"Conectando em {self.port}")
                    try:
                        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout_s)
                        self._connected_at = time.monotonic()
                        self._last_valid_at = None
                        self._backoff_s = 1.0
                        self.status.emit("Porta da estufa aberta; aguardando leitura")
                    except Exception as exc:
                        self._ser = None
                        self._emit_error(f"Falha ao conectar estufa: {exc}")
                        self._wait_backoff()
                        continue
                try:
                    line = self._ser.readline().decode(errors="ignore").strip()
                except Exception as exc:
                    if not self._running:
                        break
                    self._emit_error(f"Falha lendo estufa: {exc}")
                    self._close_serial()
                    self._wait_backoff()
                    continue
                if not line:
                    self._mark_stale_if_needed()
                    continue
                self.raw_received.emit(line)
                temperature = self.parse_temp(line)
                if temperature is None or not math.isfinite(temperature):
                    self.state.emit(INVALID)
                    self.status.emit("Estufa: mensagem invalida")
                    continue
                self._last_valid_at = time.monotonic()
                self.state.emit(OK)
                self.temp_received.emit(temperature)
        except Exception as exc:
            if self._running:
                self._emit_error(f"Falha lendo estufa: {exc}")
                self._close_serial()
                self._wait_backoff()
        finally:
            self._running = False
            self._close_serial()
            self.state.emit(DISCONNECTED)
            self.status.emit("Estufa desconectada")

    def stop(self):
        self._running = False
        self._close_serial()
        if self.isRunning() and QThread.currentThread() != self:
            self.wait(1500)

    def _wait_backoff(self):
        deadline = time.monotonic() + self._backoff_s
        self._backoff_s = min(30.0, self._backoff_s * 2.0)
        while self._running and time.monotonic() < deadline:
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

    def _close_serial(self):
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass
        self._ser = None

    def _mark_stale_if_needed(self):
        reference = self._last_valid_at or self._connected_at
        if reference is not None and time.monotonic() - reference > self.stale_after_s:
            self.state.emit(STALE)
            self.status.emit("Estufa sem leitura valida (STALE)")

    def _emit_error(self, message: str):
        self.state.emit(ERROR)
        self.status.emit("Estufa em erro")
        self.error.emit(message)

    @staticmethod
    def parse_temp(line: str):
        text = line.strip().lower().replace(",", ".")
        patterns = [
            r"temp\s*[:=]\s*([-+]?\d*\.?\d+)",
            r"pv\s*[:=]\s*([-+]?\d*\.?\d+)",
            r"([-+]?\d*\.?\d+)\s*°?c",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        return None
