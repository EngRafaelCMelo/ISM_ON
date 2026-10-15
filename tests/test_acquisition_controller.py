from PyQt5.QtCore import QObject, QCoreApplication, pyqtSignal, pyqtSlot
from PyQt5.QtTest import QTest

from acquisition_controller import AcquisitionController
from operation_state import OperationState


class FakeWorker(QObject):
    data = pyqtSignal(dict)
    error = pyqtSignal(str)
    started = pyqtSignal()
    stopped = pyqtSignal()

    @pyqtSlot()
    def start(self):
        self.started.emit()

    @pyqtSlot()
    def stop(self):
        self.stopped.emit()


class FailingWorker(FakeWorker):
    @pyqtSlot()
    def start(self):
        self.error.emit("initialization failure")
        self.stopped.emit()


def wait_until(predicate, timeout_ms=1000):
    elapsed = 0
    while elapsed < timeout_ms:
        if predicate():
            return True
        QTest.qWait(10)
        elapsed += 10
    return predicate()


def test_controller_requires_worker_ack_and_supports_restart():
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = AcquisitionController(FakeWorker)

    assert controller.start() is True
    assert controller.state == OperationState.STARTING
    assert wait_until(lambda: controller.state == OperationState.RUNNING)
    assert controller.start() is False

    assert controller.stop() is True
    assert controller.state == OperationState.STOPPING
    assert wait_until(lambda: controller.state == OperationState.STOPPED)

    assert controller.start() is True
    assert wait_until(lambda: controller.state == OperationState.RUNNING)
    controller.close()
    assert controller.state == OperationState.STOPPED


def test_controller_reports_worker_factory_failure_and_can_retry():
    app = QCoreApplication.instance() or QCoreApplication([])
    calls = {"count": 0}

    def factory():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("factory failure")
        return FakeWorker()

    controller = AcquisitionController(factory)
    errors = []
    controller.error.connect(errors.append)

    assert controller.start() is False
    assert controller.state == OperationState.ERROR
    assert errors and "factory failure" in errors[-1]

    assert controller.start() is True
    assert wait_until(lambda: controller.state == OperationState.RUNNING)
    controller.close()
    assert controller.state == OperationState.STOPPED


def test_controller_enters_error_when_worker_fails_before_start_ack():
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = AcquisitionController(FailingWorker)
    errors = []
    controller.error.connect(errors.append)

    assert controller.start() is True
    assert wait_until(lambda: controller.state == OperationState.ERROR)
    assert errors and "initialization failure" in errors[-1]
    controller.close()
    assert controller.state == OperationState.STOPPED
