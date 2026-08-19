import pytest

from harness import pulsar_control


@pytest.mark.parametrize(
    "stats, expected",
    [
        (None, None),
        ({}, None),
        ({"topic_subscriber_counts": None}, None),
        ({"topic_subscriber_counts": {}}, 0),
        ({"topic_subscriber_counts": {"owner/job_setup": 1, "owner/job_kill": 2}}, 1),
        ({"topic_subscriber_counts": {"job_setup": 1}}, 0),
        ({"topic_subscriber_counts": {"owner/job_setup": "invalid"}}, None),
    ],
)
def test_setup_waiter_count(stats, expected):
    assert pulsar_control._setup_waiter_count(stats) == expected


def test_wait_for_drain_requires_uninterrupted_zeros(monkeypatch):
    now = 0.0
    counts = iter([0, 0, 1, 0, 0, 0])

    def time():
        return now

    def sleep(seconds):
        nonlocal now
        now += seconds

    monkeypatch.setattr(pulsar_control.time, "time", time)
    monkeypatch.setattr(pulsar_control.time, "sleep", sleep)
    monkeypatch.setattr(pulsar_control, "_relay_setup_waiter_count", lambda: next(counts))
    monkeypatch.setattr(pulsar_control, "RELAY_DRAIN_CONFIRM_SECONDS", 0.5)

    assert pulsar_control._wait_relay_setup_waiters_drained(timeout=2, poll_interval=0.25)
    assert now == 1.25
