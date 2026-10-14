"""Eventos e alarmes informativos centralizados."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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
    def __init__(self):
        self.events: List[SystemEvent] = []
        self._listeners: List[Callable[[SystemEvent], None]] = []

    def subscribe(self, callback: Callable[[SystemEvent], None]) -> None:
        self._listeners.append(callback)

    def emit(self, source: str, severity: str, message: str, code: str = "") -> SystemEvent:
        event = SystemEvent(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            source=str(source), severity=str(severity).upper(),
            message=str(message), code=str(code),
        )
        self.events.append(event)
        for listener in list(self._listeners):
            listener(event)
        return event

    def last(self) -> Optional[SystemEvent]:
        return self.events[-1] if self.events else None
