from __future__ import annotations

from typing import Any


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
