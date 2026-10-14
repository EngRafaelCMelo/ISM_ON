"""Ciclo de vida de um worker de aquisicao sem reutilizar QThreads encerradas."""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QMetaObject, QObject, QThread, Qt, pyqtSignal, pyqtSlot

from operation_state import (
    InvalidTransition,
    OperationEvent,
    OperationState,
    OperationStateMachine,
)


class AcquisitionController(QObject):
    state_changed = pyqtSignal(str)
    data = pyqtSignal(dict)
    error = pyqtSignal(str)
    worker_started = pyqtSignal()
    worker_stopped = pyqtSignal()

    def __init__(self, worker_factory: Callable[[], QObject], parent=None):
        super().__init__(parent)
        self.worker_factory = worker_factory
        self.machine = OperationStateMachine()
        self.thread: Optional[QThread] = None
        self.worker: Optional[QObject] = None
        self._faulted = False

    @property
    def state(self) -> OperationState:
        return self.machine.state

    def _set_state(self, event: OperationEvent) -> None:
        try:
            state = self.machine.transition(event)
        except InvalidTransition:
            return
        self.state_changed.emit(state.value)

    @pyqtSlot()
    def start(self) -> bool:
        if self.state in (OperationState.STARTING, OperationState.RUNNING, OperationState.STOPPING):
            return False
        if self.thread is not None and self.thread.isRunning():
            return False
        self._faulted = False
        self._set_state(OperationEvent.START_REQUEST)
        self.thread = QThread(self)
        self.worker = self.worker_factory()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.worker.started.connect(self._on_worker_started)
        self.worker.stopped.connect(self._on_worker_stopped)
        self.worker.error.connect(self._on_worker_error)
        self.worker.data.connect(self.data)
        self.worker.stopped.connect(self.thread.quit)
        self.thread.finished.connect(self._on_thread_finished)
        self.thread.start()
        return True

    @pyqtSlot()
    def stop(self) -> bool:
        if self.state not in (OperationState.STARTING, OperationState.RUNNING, OperationState.ERROR):
            return False
        self._set_state(OperationEvent.STOP_REQUEST)
        if self.worker is None or self.thread is None or not self.thread.isRunning():
            self._set_state(OperationEvent.WORKER_STOPPED)
            return True
        QMetaObject.invokeMethod(self.worker, "stop", Qt.QueuedConnection)
        return True

    @pyqtSlot()
    def close(self) -> None:
        self.stop()
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(2000)

    def _on_worker_started(self):
        self._set_state(OperationEvent.WORKER_STARTED)
        self.worker_started.emit()

    def _on_worker_error(self, message: str):
        self._faulted = True
        self._set_state(OperationEvent.WORKER_ERROR)
        self.error.emit(message)

    def _on_worker_stopped(self):
        if not self._faulted:
            self._set_state(OperationEvent.WORKER_STOPPED)
        self.worker_stopped.emit()

    def _on_thread_finished(self):
        # A nova partida sempre cria novos objetos. Referencias sao mantidas
        # para diagnostico ate a proxima partida ou o fechamento da aplicacao.
        if self.state == OperationState.STOPPING and not self._faulted:
            self._set_state(OperationEvent.WORKER_STOPPED)
