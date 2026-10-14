import pytest

from operation_state import InvalidTransition, OperationEvent, OperationState, OperationStateMachine


def test_start_requires_worker_confirmation_and_stop_requires_completion():
    machine = OperationStateMachine()
    assert machine.transition(OperationEvent.START_REQUEST) == OperationState.STARTING
    assert machine.state == OperationState.STARTING
    with pytest.raises(InvalidTransition):
        machine.transition(OperationEvent.START_REQUEST)
    assert machine.transition(OperationEvent.WORKER_STARTED) == OperationState.RUNNING
    assert machine.transition(OperationEvent.STOP_REQUEST) == OperationState.STOPPING
    assert machine.transition(OperationEvent.WORKER_STOPPED) == OperationState.STOPPED


def test_worker_failure_enters_error_and_can_be_recovered():
    machine = OperationStateMachine()
    machine.transition(OperationEvent.START_REQUEST)
    assert machine.transition(OperationEvent.WORKER_ERROR) == OperationState.ERROR
    assert machine.transition(OperationEvent.START_REQUEST) == OperationState.STARTING
