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
        self._closing = False

    @property
    def state(self) -> OperationState:
        return self.machine.state

    def _set_state(self, event: OperationEvent) -> bool:
        try:
            state = self.machine.transition(event)
        except InvalidTransition:
            return False
        self.state_changed.emit(state.value)
        return True

    @pyqtSlot()
    def start(self) -> bool:
        if self._closing:
            return False
        if self.state in (OperationState.STARTING, OperationState.RUNNING, OperationState.STOPPING):
            return False
        if self.thread is not None and self.thread.isRunning():
            # A worker that failed can still be finishing its event loop.  Do
            # not create a second acquisition until that QThread is finished.
            return False
        self._faulted = False
        self._set_state(OperationEvent.START_REQUEST)
        thread = QThread(self)
        self.thread = thread
        try:
            worker = self.worker_factory()
            self.worker = worker
            worker.moveToThread(thread)
            thread.started.connect(worker.start)
            worker.started.connect(self._on_worker_started)
            worker.stopped.connect(self._on_worker_stopped)
            worker.error.connect(self._on_worker_error)
            worker.data.connect(self.data)
            # The worker owns resource cleanup.  It must request the event
            # loop to quit only after that cleanup has completed.
            # QThread.quit() is thread-safe; use a direct connection so a
            # close operation that is waiting for the thread cannot starve
            # the queued quit call in the GUI event loop.
            worker.stopped.connect(thread.quit, Qt.DirectConnection)
            worker.stopped.connect(worker.deleteLater)
            thread.finished.connect(self._on_thread_finished)
            thread.start()
            return True
        except Exception as exc:
            self._faulted = True
            self._set_state(OperationEvent.WORKER_ERROR)
            self.error.emit(f"Falha ao preparar aquisicao: {exc}")
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
            self.worker = None
            return False

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
        self._closing = True
        try:
            self.stop()
            thread = self.thread
            if thread is not None and thread.isRunning():
                # The worker owns the DAQ cleanup.  Give its queued stop a
                # chance to run before asking the event loop to quit.
                if not thread.wait(2500):
                    thread.quit()
                    thread.wait(1000)
            if thread is not None and not thread.isRunning() and self.state == OperationState.STOPPING:
                self._set_state(OperationEvent.WORKER_STOPPED)
        finally:
            self._closing = False

    def _on_worker_started(self):
        if self._set_state(OperationEvent.WORKER_STARTED):
            self.worker_started.emit()

    def _on_worker_error(self, message: str):
        self._faulted = True
        self._set_state(OperationEvent.WORKER_ERROR)
        self.error.emit(message)

    def _on_worker_stopped(self):
        # State STOPPED is emitted from _on_thread_finished, after the worker
        # has released its resources and the QThread event loop has finished.
        # An unexpected stop while RUNNING is a fault, not a successful stop.
        if self.state == OperationState.RUNNING and not self._closing:
            self._faulted = True
            self._set_state(OperationEvent.WORKER_ERROR)
            self.error.emit("Worker de aquisicao encerrou inesperadamente.")
        elif self.state == OperationState.STARTING and not self._closing:
            self._faulted = True
            self._set_state(OperationEvent.WORKER_ERROR)
            self.error.emit("Worker encerrou antes de confirmar a inicializacao.")
        self.worker_stopped.emit()

    def _on_thread_finished(self):
        # A nova partida sempre cria novos objetos. Referencias sao mantidas
        # para diagnostico ate a proxima partida ou o fechamento da aplicacao.
        if self.state == OperationState.STOPPING:
            self._set_state(OperationEvent.WORKER_STOPPED)
        elif self.state == OperationState.STARTING:
            self._faulted = True
            self._set_state(OperationEvent.WORKER_ERROR)
            self.error.emit("Worker encerrou antes de confirmar a inicializacao.")
        elif self.state == OperationState.RUNNING:
            self._faulted = True
            self._set_state(OperationEvent.WORKER_ERROR)
            self.error.emit("Thread de aquisicao encerrou inesperadamente.")
