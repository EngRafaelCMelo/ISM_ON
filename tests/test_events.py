from events import EventManager


def test_event_manager_records_and_notifies_events():
    manager = EventManager()
    received = []
    manager.subscribe(received.append)
    event = manager.emit("DAQ", "warning", "Canal invalido", "SENSOR_INVALID")
    assert manager.last() == event
    assert received == [event]
    assert event.severity == "WARNING"
    assert event.as_dict()["code"] == "SENSOR_INVALID"


def test_event_manager_persists_json_lines_and_isolates_listener_errors(tmp_path):
    manager = EventManager(str(tmp_path / "events.log"))
    received = []
    manager.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("listener")))
    manager.subscribe(received.append)

    manager.emit("SERIAL", "error", "Porta indisponivel", "SERIAL_ERROR")

    assert len(received) == 1
    line = (tmp_path / "events.log").read_text(encoding="utf-8").strip()
    assert '"source": "SERIAL"' in line
    assert '"severity": "ERROR"' in line
