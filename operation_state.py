"""Maquina de estados da aquisicao.

O modulo e deliberadamente independente de PyQt para que as transicoes sejam
testadas sem hardware ou loop de eventos.
"""

from __future__ import annotations

from enum import Enum


class OperationState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


class OperationEvent(str, Enum):
    START_REQUEST = "START_REQUEST"
    WORKER_STARTED = "WORKER_STARTED"
    STOP_REQUEST = "STOP_REQUEST"
    WORKER_STOPPED = "WORKER_STOPPED"
    WORKER_ERROR = "WORKER_ERROR"
    RESET = "RESET"


class InvalidTransition(RuntimeError):
    pass


class OperationStateMachine:
    """Aplica transicoes validas e rejeita cliques/confirmacoes duplicadas."""

    def __init__(self, state: OperationState = OperationState.STOPPED):
        self.state = OperationState(state)

    def transition(self, event: OperationEvent) -> OperationState:
        event = OperationEvent(event)
        current = self.state
        next_state = None

        if event == OperationEvent.START_REQUEST:
            if current in (OperationState.STOPPED, OperationState.ERROR):
                next_state = OperationState.STARTING
        elif event == OperationEvent.WORKER_STARTED:
            if current == OperationState.STARTING:
                next_state = OperationState.RUNNING
        elif event == OperationEvent.STOP_REQUEST:
            if current in (OperationState.STARTING, OperationState.RUNNING):
                next_state = OperationState.STOPPING
            elif current == OperationState.ERROR:
                next_state = OperationState.STOPPING
        elif event == OperationEvent.WORKER_STOPPED:
            if current in (
                OperationState.STARTING,
                OperationState.RUNNING,
                OperationState.STOPPING,
            ):
                next_state = OperationState.STOPPED
        elif event == OperationEvent.WORKER_ERROR:
            if current != OperationState.STOPPED:
                next_state = OperationState.ERROR
        elif event == OperationEvent.RESET:
            if current == OperationState.ERROR:
                next_state = OperationState.STOPPED

        if next_state is None:
            raise InvalidTransition(f"{current.value} + {event.value}")
        self.state = next_state
        return self.state
