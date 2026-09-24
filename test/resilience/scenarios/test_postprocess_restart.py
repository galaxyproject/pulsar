"""A5-A8. Pulsar dies while staging a job's outputs back to Galaxy.

The job itself is already over by the time these scenarios kill Pulsar - its
process has exited and its terminal status is on disk. Only Pulsar's own
bookkeeping has to survive, so unlike the A1/A2 scenarios (where
``queued_python`` loses the subprocess with its parent) these can assert a
hard ``complete`` rather than "some terminal status".

That window is issue #354: until the postprocessing index existed, a job
between ``__deactivate`` and the end of output staging was in no persistent
index at all, and a restart in that window left Galaxy waiting forever.

The stall is a latency toxic rather than ``disable()`` because
``RetryActionExecutor`` does not retry by default - a dead proxy fails
staging instantly instead of holding Pulsar inside it.
"""
import pytest
import requests

from pulsar.testing.resilience.assertions import (
    assert_exactly_once_terminal,
    await_terminal,
)
from pulsar.testing.resilience.job_factory import (
    files_url,
    GALAXY_HOST_URL,
    make_setup_message,
)

GALAXY_BASE = "http://localhost:8088"

# The toxic sits on ``galaxy_http``, which is also how this test process
# reaches mock-galaxy, so publishing a job blocks for this long too. The job
# therefore sleeps longer than the latency before writing its output: that puts
# stage-out safely after the submitting call has returned, leaving the whole
# latency window to kill inside.
STAGE_OUT_LATENCY_MS = 8000
JOB_DELAY_SECONDS = 12
# Deterministic, and big enough to be a real transfer rather than one packet.
OUTPUT_LINES = 200000
STAGE_OUT_MARKER = "collecting output"


def _expected_output():
    return "".join(f"{i}\n" for i in range(1, OUTPUT_LINES + 1)).encode()


def _submit_job_with_output(output_name):
    """Publish a job that writes a deterministic file into its outputs dir."""
    body = make_setup_message(
        command_line=(
            f"sleep {JOB_DELAY_SECONDS} && "
            f"seq 1 {OUTPUT_LINES} > ../outputs/{output_name}"
        ),
        output_files=[output_name],
    )
    requests.post(
        f"{GALAXY_BASE}/_publish_setup", json=body, timeout=60
    ).raise_for_status()
    return body


def _fetch_staged_output(galaxy_filename):
    r = requests.get(
        files_url(galaxy_filename, file_type="output", base=GALAXY_HOST_URL),
        timeout=30,
    )
    r.raise_for_status()
    return r.content


def _stall_stage_out(pulsar, galaxy_proxy, output_name):
    """Submit a job whose stage-out will hang, and stop once it has begun."""
    watch = pulsar.watch_logs()
    galaxy_proxy.add_latency(STAGE_OUT_LATENCY_MS)
    body = _submit_job_with_output(output_name)
    watch.wait_for(STAGE_OUT_MARKER, timeout=120)
    return body


@pytest.mark.resilience
def test_a5_sigkill_during_stage_out_recovers(pulsar, galaxy_proxy):
    """SIGKILL mid-upload: the job is recovered, not lost, and bytes match."""
    body = _stall_stage_out(pulsar, galaxy_proxy, "a5_out1")
    pulsar.kill()
    galaxy_proxy.remove_all_toxics()

    pulsar.start(wait_ready=True)

    await_terminal(body["job_id"], timeout=180, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")
    # Byte-exact, so a truncated or half-resumed transfer is a failure rather
    # than "a file exists".
    assert _fetch_staged_output("a5_out1") == _expected_output()


@pytest.mark.resilience
def test_a6_sigterm_during_stage_out_recovers(pulsar, galaxy_proxy):
    """Same window, graceful signal.

    The postprocess thread is non-daemon, so a clean shutdown may drain it
    before the process exits; if it doesn't, recovery on restart has to. Either
    way Galaxy sees exactly one ``complete``.
    """
    body = _stall_stage_out(pulsar, galaxy_proxy, "a6_out1")
    pulsar.sigterm()
    galaxy_proxy.remove_all_toxics()

    pulsar.start(wait_ready=True)

    await_terminal(body["job_id"], timeout=180, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")
    assert _fetch_staged_output("a6_out1") == _expected_output()


@pytest.mark.resilience
@pytest.mark.parametrize("mq_mode", ["amqp"], indirect=True, ids=lambda m: f"mode={m}")
def test_a8_stage_out_restart_under_broker_outage(pulsar, galaxy_proxy, rabbitmq_proxy):
    """Recovery and the outbox at the same time.

    Pinned to ``amqp``: the relay's own outage path is already covered by the
    A3/B scenarios, and every extra mode here costs a full restart cycle.
    """
    body = _stall_stage_out(pulsar, galaxy_proxy, "a8_out1")
    pulsar.kill()
    galaxy_proxy.remove_all_toxics()

    # Pulsar comes back to a broker it cannot reach, re-stages the outputs, and
    # has nowhere to publish the result until the outbox drains.
    rabbitmq_proxy.disable()
    pulsar.start(wait_ready=False)
    rabbitmq_proxy.enable()

    await_terminal(body["job_id"], timeout=180, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")
    assert _fetch_staged_output("a8_out1") == _expected_output()
