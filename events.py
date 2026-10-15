"""Eventos e alarmes informativos centralizados."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from typing import Callable, List, Optional


@dataclass(frozen=True)
class SystemEvent:
    timestamp: str
    source: str
    severity: str
    message: str
    code: str = ""

    def as_dict(self):
        return asdict(self)


class EventManager:
    def __init__(self, log_path: Optional[str] = None):
        self.events: List[SystemEvent] = []
        self._listeners: List[Callable[[SystemEvent], None]] = []
        self.log_path = os.path.abspath(log_path) if log_path else None

    def subscribe(self, callback: Callable[[SystemEvent], None]) -> None:
        self._listeners.append(callback)

    def emit(self, source: str, severity: str, message: str, code: str = "") -> SystemEvent:
        event = SystemEvent(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            source=str(source), severity=str(severity).upper(),
            message=str(message), code=str(code),
        )
        self.events.append(event)
        if self.log_path:
            try:
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as file:
                    file.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")
            except OSError:
                # O registro operacional nao pode derrubar a aquisicao. A
                # falha continua observavel na memoria e no status da UI.
                pass
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                # Um consumidor (por exemplo, o writer de um ensaio) nao
                # deve impedir que os demais recebam o alarme.
                continue
        return event

    def last(self) -> Optional[SystemEvent]:
        return self.events[-1] if self.events else None
