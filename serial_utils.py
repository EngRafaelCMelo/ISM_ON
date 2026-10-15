from __future__ import annotations

import math
from typing import Any


def validate_serial_settings(port: str, baudrate: int, timeout_s: float, stale_after_s: float) -> None:
    """Validate settings before a worker is started or reconfigured."""
    if not str(port).strip():
        raise ValueError("A porta serial e obrigatoria.")
    try:
        baudrate = int(baudrate)
        timeout_s = float(timeout_s)
        stale_after_s = float(stale_after_s)
    except (TypeError, ValueError) as exc:
        raise ValueError("Configuracao serial numericamente invalida.") from exc
    if baudrate <= 0:
        raise ValueError("O baudrate deve ser maior que zero.")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("O timeout deve ser maior que zero.")
    if not math.isfinite(stale_after_s) or stale_after_s <= 0:
        raise ValueError("O tempo de STALE deve ser maior que zero.")


def list_available_ports() -> list[dict[str, Any]]:
    """Lista portas seriais sem abrir ou alterar qualquer equipamento."""
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    return [
        {"device": port.device, "description": port.description, "hwid": port.hwid}
        for port in list_ports.comports()
    ]
