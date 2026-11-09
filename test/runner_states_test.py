import pytest

from pulsar.managers.util import (
    register_runner_state,
    RUNNER_STATE_DEFINITIONS,
    runner_states,
)


def _unregister(name, value):
    RUNNER_STATE_DEFINITIONS.pop(value, None)
    runner_states.__dict__.pop(name, None)


def test_register_runner_state():
    try:
        assert register_runner_state("TEST_REASON", "test_reason", fail_message="why") == "test_reason"
        assert runner_states.TEST_REASON == "test_reason"
        assert RUNNER_STATE_DEFINITIONS["test_reason"].fail_message == "why"
    finally:
        _unregister("TEST_REASON", "test_reason")


def test_registering_a_value_twice_with_another_meaning_is_an_error():
    try:
        register_runner_state("TEST_REASON", "test_reason", fail_message="why")
        register_runner_state("TEST_REASON", "test_reason", fail_message="why")
        with pytest.raises(ValueError):
            register_runner_state("TEST_REASON", "test_reason", fail_message="another reason")
    finally:
        _unregister("TEST_REASON", "test_reason")


def test_cancelled_is_never_resubmitted():
    assert RUNNER_STATE_DEFINITIONS[runner_states.CANCELLED].resubmit_description is None


def test_new_reasons_can_be_used_in_resubmit_conditions():
    assert RUNNER_STATE_DEFINITIONS[runner_states.NODE_FAILURE].condition == "node_failure"
    assert RUNNER_STATE_DEFINITIONS[runner_states.PREEMPTED].condition == "preempted"
