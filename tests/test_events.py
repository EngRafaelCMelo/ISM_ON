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
