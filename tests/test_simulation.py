from PyQt5.QtCore import QCoreApplication

from simulation_worker import SimulationWorker


def test_simulation_worker_marks_payload_as_simulated():
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = SimulationWorker("config.json")
    received = []
    worker.data.connect(received.append)
    worker.start()
    worker._emit_sample()
    worker.stop()
    assert received
    assert received[0]["simulated"] is True
    assert received[0]["source"] == "SIMULATED"
    assert set(received[0]["channels"]) == {"P1", "P2", "P3", "P4", "DP"}
