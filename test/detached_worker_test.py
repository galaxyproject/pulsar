"""Offline proofs for the standalone detached execution protocol.

Real subprocess tests deliberately kill supervisors rather than mocking restart.
Docker tests verify ownership and terminal-state decisions without a daemon.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pulsar.managers.util import detached_worker as worker


def wait_for(function, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = function()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("Detached worker did not reach expected state")


@pytest.fixture
def execution(tmp_path):
    processes = []
    manifest = {
        "schema": 1,
        "job_id": "example",
        "token": uuid.uuid4().hex,
        "job_directory": str(tmp_path),
        "working_directory": str(tmp_path),
        "command_script": str(tmp_path / "command.sh"),
        "stdout": str(tmp_path / "stdout"),
        "stderr": str(tmp_path / "stderr"),
        "environment": dict(os.environ),
        "cancel_grace_seconds": 0.1,
        "poll_interval": 0.02,
        "host_identity": worker.host_identity(),
        "containers": [],
        "limits": {},
    }
    shutil.copyfile(worker.__file__, tmp_path / worker.WORKER_FILE)

    def prepare(script="printf 'completed\\n'\n"):
        script_path = Path(manifest["command_script"])
        script_path.write_text("#!/bin/sh\n" + script)
        script_path.chmod(0o700)
        worker.atomic_json(tmp_path / worker.MANIFEST_FILE, manifest)

    def launch(recover=False):
        process = subprocess.Popen(
            [
                sys.executable,
                str(tmp_path / worker.WORKER_FILE),
                str(tmp_path / worker.MANIFEST_FILE),
            ]
            + (["--recover"] if recover else []),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        processes.append(process)
        return process

    prepare()
    yield SimpleNamespace(
        root=tmp_path, manifest=manifest, prepare=prepare, launch=launch
    )
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        process.stderr.close()
    record = worker.read_json(tmp_path / worker.COMMAND_FILE, {})
    identity = record.get("command_identity")
    if identity:
        snapshot = worker.read_json(tmp_path / worker.LIVE_FILE, {})
        worker.signal_command(
            identity, signal.SIGKILL, snapshot.get("command_members", [identity])
        )


def result(execution):
    return worker.read_json(execution.root / worker.RESULT_FILE)


def command(execution):
    return worker.read_json(execution.root / worker.COMMAND_FILE, {})


def stop(execution, reason="cancelled"):
    worker.atomic_json(
        execution.root / worker.STOP_FILE,
        {
            "schema": 1,
            "job_id": execution.manifest["job_id"],
            "token": execution.manifest["token"],
            "reason": reason,
        },
    )


def test_native_exit_and_private_durable_records(execution):
    execution.prepare("printf 'native output\\n'; printf 'error text\\n' >&2; exit 7\n")
    process = execution.launch()
    record = wait_for(lambda: result(execution))
    process.wait(timeout=10)
    assert record["return_code"] == record["returncode"] == 7
    assert record["command_exit_confirmed"] and record["container_exit_confirmed"]
    assert record["stopped"] is False
    assert (execution.root / "stdout").read_text() == "native output\n"
    assert (execution.root / "stderr").read_text() == "error text\n"
    for name in (
        worker.MANIFEST_FILE,
        worker.LIVE_FILE,
        worker.COMMAND_FILE,
        worker.START_FILE,
        worker.EXIT_FILE,
        worker.RESULT_FILE,
    ):
        assert (execution.root / name).stat().st_mode & 0o777 == 0o600


def test_result_is_idempotent_and_duplicate_supervisor_cannot_replay(execution):
    execution.prepare("echo run >> launches; sleep 0.2\n")
    first = execution.launch()
    wait_for(lambda: command(execution).get("phase") == "executing")
    duplicate = execution.launch(recover=True)
    duplicate.wait(timeout=10)
    wait_for(lambda: result(execution))
    first.wait(timeout=10)
    execution.launch(recover=True).wait(timeout=10)
    assert (execution.root / "launches").read_text().splitlines() == ["run"]


@pytest.mark.parametrize("finish_during_downtime", [False, True])
def test_supervisor_loss_reconnects_to_same_execution(
    execution, finish_during_downtime
):
    execution.prepare("echo run >> launches; sleep 0.4; echo complete > output\n")
    original = execution.launch()
    identity = wait_for(
        lambda: command(execution).get("phase") == "executing"
        and command(execution)["command_identity"]
    )
    wait_for(lambda: (execution.root / "launches").exists())
    original.kill()
    original.wait(timeout=10)
    if finish_during_downtime:
        wait_for(lambda: (execution.root / worker.EXIT_FILE).exists())
    replacement = execution.launch(recover=True)
    record = wait_for(lambda: result(execution))
    replacement.wait(timeout=10)
    assert record["command_identity"] == identity
    assert record["return_code"] == 0
    assert (execution.root / "launches").read_text().splitlines() == ["run"]
    assert (execution.root / "output").read_text().strip() == "complete"


def test_cancel_before_launch_does_not_execute(execution):
    execution.prepare("touch should-not-exist\n")
    stop(execution)
    execution.launch().wait(timeout=10)
    assert result(execution)["stopped"] is True
    assert not (execution.root / "should-not-exist").exists()
    assert not (execution.root / worker.COMMAND_FILE).exists()


def test_cancel_terminates_verified_group(execution):
    execution.prepare("sleep 30\n")
    execution.launch()
    identity = wait_for(
        lambda: command(execution).get("phase") == "executing"
        and command(execution)["command_identity"]
    )
    stop(execution)
    record = wait_for(lambda: result(execution))
    assert record["stopped"] and record["command_exit_confirmed"]
    assert worker.command_group_status(identity)[1] is False


def test_background_writers_are_drained_before_result(execution):
    execution.prepare("(trap '' TERM; sleep 30) &\necho $! > writer; sleep 0.1\n")
    execution.launch()
    wait_for(lambda: (execution.root / "writer").exists())
    writer_identity = worker.process_identity(
        int((execution.root / "writer").read_text())
    )
    wait_for(lambda: result(execution))
    assert worker.identity_alive(writer_identity) is False


def test_walltime_survives_supervisor_replacement(execution):
    execution.manifest["limits"] = {"walltime_seconds": 0.3}
    execution.prepare("echo started > marker; sleep 30\n")
    process = execution.launch()
    wait_for(lambda: (execution.root / "marker").exists())
    started_at = command(execution)["started_at"]
    process.kill()
    process.wait(timeout=10)
    time.sleep(0.35)
    execution.launch(recover=True)
    record = wait_for(lambda: result(execution))
    assert record["stopped"]
    assert worker.read_json(execution.root / worker.STOP_FILE)["reason"] == "walltime"
    assert "walltime" in record["failure"]
    assert command(execution)["started_at"] == started_at


def test_output_limit_is_enforced_without_galaxy(execution):
    output = execution.root / "output"
    execution.manifest["limits"] = {
        "output_size_bytes": 10,
        "output_paths": [str(output)],
    }
    execution.prepare("printf 'a sufficiently large output' > output; sleep 30\n")
    execution.launch()
    record = wait_for(lambda: result(execution))
    assert record["stopped"]
    assert "output_size" in record["failure"]


def test_native_output_limit_is_per_file_not_total_job_output(execution):
    execution.manifest["limits"] = {
        "output_size_bytes": 10,
        "output_paths": [str(execution.root / "first"), str(execution.root / "second")],
    }
    execution.prepare("printf '123456' > first; printf '123456' > second; sleep 0.1\n")
    execution.launch()
    record = wait_for(lambda: result(execution))
    assert record["return_code"] == 0 and record["stopped"] is False
    assert not (execution.root / worker.STOP_FILE).exists()


def test_native_output_limit_counts_a_symlinked_declared_file(tmp_path):
    target = tmp_path / "actual"
    target.write_bytes(b"12345678901")
    link = tmp_path / "declared"
    link.symlink_to(target)
    manifest = {"limits": {"output_size_bytes": 10, "output_paths": [str(link)]}}
    assert worker.exceeded_limit(manifest, None) == "output_size"


def test_aggregate_directory_limit_requires_separate_explicit_policy(execution):
    directory = execution.root / "aggregate-output"
    directory.mkdir()
    (directory / "first").write_bytes(b"123456")
    (directory / "second").write_bytes(b"123456")
    limits = {
        "output_directory": str(directory),
        "output_directory_size_bytes": 10,
    }
    assert worker.exceeded_limit({"limits": limits}, None) == "output_directory_size"
    execution.manifest["limits"] = {
        "output_directory": str(execution.root),
        "output_size_bytes": 10,
    }
    with pytest.raises(ValueError, match="supplied together"):
        worker.run(execution.manifest)


def test_unknown_fork_window_never_replays(execution):
    execution.prepare("touch should-not-exist\n")
    worker.atomic_json(
        execution.root / worker.LIVE_FILE,
        {
            "schema": 1,
            "job_id": execution.manifest["job_id"],
            "token": execution.manifest["token"],
            "launch_intent": True,
            "phase": "starting_command",
        },
    )
    execution.launch(recover=True)
    wait_for(
        lambda: worker.read_json(execution.root / worker.LIVE_FILE, {}).get("phase")
        == "retained"
    )
    time.sleep(0.1)
    assert not result(execution)
    assert not (execution.root / "should-not-exist").exists()


def test_unstarted_manager_reservation_can_launch_on_recovery(execution):
    execution.manifest["phase"] = "launching"
    execution.prepare("echo single >> launches\n")
    execution.launch(recover=True).wait(timeout=10)
    assert result(execution)["return_code"] == 0
    assert (execution.root / "launches").read_text() == "single\n"


def test_host_boot_mismatch_neither_executes_nor_signals(execution, monkeypatch):
    execution.manifest["host_identity"]["boot_id"] = "other-boot"
    execution.prepare("touch should-not-exist\n")
    signal_mock = Mock()
    monkeypatch.setattr(worker, "signal_command", signal_mock)
    assert worker.run(execution.manifest, recover=True) == 0
    assert not result(execution)
    assert not signal_mock.called
    assert not (execution.root / "should-not-exist").exists()
    assert worker.read_json(execution.root / worker.LIVE_FILE)["phase"] == "retained"


def test_pid_reuse_does_not_authorize_process_group_signalling(monkeypatch):
    identity = {"pid": os.getpid(), "creation_time": 0}
    signal_mock = Mock()
    monkeypatch.setattr(os, "killpg", signal_mock)
    assert worker.identity_alive(identity) is False
    worker.signal_command(identity, signal.SIGTERM)
    assert not signal_mock.called
    assert worker.command_group_status(identity)[1] is None


def docker_response(**changes):
    info = {
        "Id": "immutable-owned-id",
        "Name": "/owned",
        "Mounts": [{"Source": "/jobs/1", "Destination": "/jobs/1", "RW": False}],
        "State": {"Running": True, "Status": "running"},
    }
    info.update(changes)
    return SimpleNamespace(returncode=0, stdout=json.dumps(info), stderr="")


@pytest.mark.parametrize("state", ["running", "created", "exited", "dead"])
def test_docker_verified_identity_and_mount(monkeypatch, state):
    response = docker_response(State={"Running": state == "running", "Status": state})
    monkeypatch.setattr(worker, "call_docker", Mock(return_value=response))
    observed, identity, info = worker.inspect_container(
        {}, "owned", expected_mount="/jobs/1"
    )
    assert observed == state and identity == "immutable-owned-id" and info


@pytest.mark.parametrize(
    "changes",
    [
        {"Name": "/other"},
        {"Id": "replacement"},
        {"Mounts": []},
        {"Mounts": [{"Source": "/jobs/other", "Destination": "/jobs/1", "RW": False}]},
        {"State": {"Status": "removing"}},
    ],
)
def test_docker_changed_identity_or_mount_is_unknown(monkeypatch, changes):
    monkeypatch.setattr(
        worker, "call_docker", Mock(return_value=docker_response(**changes))
    )
    state, identity, _ = worker.inspect_container(
        {}, "owned", "immutable-owned-id", "/jobs/1"
    )
    assert state == "unknown" and identity == "immutable-owned-id"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("No such container: owned", "absent"),
        ("Cannot connect to Docker daemon", "unknown"),
        ("permission denied", "unknown"),
    ],
)
def test_docker_absence_differs_from_daemon_failure(monkeypatch, message, expected):
    monkeypatch.setattr(
        worker,
        "call_docker",
        Mock(return_value=SimpleNamespace(returncode=1, stdout="", stderr=message)),
    )
    assert (
        worker.inspect_container({}, "owned", "immutable-owned-id", "/jobs/1")[0]
        == expected
    )


def test_owned_daemon_container_stops_after_wrapper_exits(execution, monkeypatch):
    execution.prepare("true\n")
    execution.manifest["containers"] = [
        {
            "container_type": "docker",
            "container_name": "owned",
            "connection_configuration": {},
            "expected_mount": str(execution.root),
            "role": "tool",
        }
    ]
    state = {"value": "running"}
    actions = []
    monkeypatch.setattr(
        worker,
        "inspect_container",
        lambda *args: (state["value"], "immutable-owned-id", None),
    )

    def call(configuration, *arguments, **kwds):
        actions.append(arguments)
        state["value"] = "exited"
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(worker, "call_docker", call)
    assert worker.run(execution.manifest) == 0
    assert actions and all(action[-1] == "immutable-owned-id" for action in actions)
    assert result(execution)["container_exit_confirmed"]
    assert result(execution)["container_identities"] == {"owned": "immutable-owned-id"}


def test_unknown_container_never_authorizes_result(execution, monkeypatch):
    execution.manifest["containers"] = [
        {
            "container_type": "docker",
            "container_name": "owned",
            "connection_configuration": {},
            "expected_mount": str(execution.root),
        }
    ]
    stop(execution)
    monkeypatch.setattr(
        worker, "inspect_container", lambda *args: ("unknown", None, None)
    )
    monkeypatch.setattr(
        worker.time, "sleep", Mock(side_effect=RuntimeError("end inspection"))
    )
    # No process has started, but an inaccessible daemon still blocks terminal proof.
    # A cancellation before any launch is safe because no container could exist.
    # Force an existing, finished command to exercise the uncertain-daemon case.
    identity = {"pid": 99999999, "creation_time": 0}
    for name, fields in (
        (worker.COMMAND_FILE, {"command_identity": identity}),
        (worker.EXIT_FILE, {"command_identity": identity, "return_code": 0}),
    ):
        worker.atomic_json(
            execution.root / name,
            {
                "job_id": execution.manifest["job_id"],
                "token": execution.manifest["token"],
                **fields,
            },
        )
    with pytest.raises(RuntimeError, match="end inspection"):
        worker.run(execution.manifest, recover=True)
    assert not result(execution)


def test_output_count_ignores_symlinks_and_counts_hardlinks_once(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "a").write_bytes(b"12345")
    os.link(output / "a", output / "hardlink")
    (output / "symlink").symlink_to(output / "a")
    assert worker.output_size([str(output), str(output / "a")]) == 5


@pytest.mark.parametrize(
    "key,value",
    [
        ("poll_interval", 0),
        ("poll_interval", True),
        ("poll_interval", float("nan")),
        ("cancel_grace_seconds", -1),
        ("cancel_grace_seconds", float("inf")),
    ],
)
def test_invalid_timings_rejected_before_execution(execution, key, value):
    execution.manifest[key] = value
    with pytest.raises(ValueError):
        worker.run(execution.manifest)
    assert not (execution.root / worker.COMMAND_FILE).exists()


def test_execution_records_cannot_be_adopted_by_another_token(execution):
    worker.atomic_json(
        execution.root / worker.RESULT_FILE,
        {"job_id": "example", "token": uuid.uuid4().hex},
    )
    with pytest.raises(ValueError, match="does not belong"):
        worker.run(execution.manifest)


def test_entry_points_retry_callback_and_never_log_credentials(execution, monkeypatch):
    callback = "http://galaxy.invalid/api/jobs/1/ports?job_key=private"
    execution.manifest["entry_point_config"] = {
        "container_name": "owned",
        "callback_url": callback,
    }
    info = {
        "owned": {
            "NetworkSettings": {
                "Ports": {"8888/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}
            }
        }
    }
    response = Mock()
    response.__enter__ = Mock(return_value=SimpleNamespace(status=200))
    response.__exit__ = Mock(return_value=False)
    request = Mock(side_effect=[OSError("Galaxy unavailable"), response])
    monkeypatch.setattr(worker.urlrequest, "urlopen", request)
    snapshot = {}
    worker.publish_entry_points(execution.manifest, snapshot, info)
    assert not snapshot.get("entry_points_published")
    worker.publish_entry_points(execution.manifest, snapshot, info)
    assert snapshot["entry_points_published"]
    assert snapshot["entry_point_ports"][8888]["port"] == 34567
    assert snapshot["entry_point_ports"][8888]["protocol"] == "http"
    worker.publish_entry_points(execution.manifest, snapshot, info)
    assert request.call_count == 2
    assert "private" not in json.dumps(snapshot)


@pytest.mark.parametrize("status", [403, 410])
def test_revoked_entry_point_callback_is_not_retried(execution, monkeypatch, status):
    execution.manifest["entry_point_config"] = {
        "container_name": "owned",
        "callback_url": "http://galaxy.invalid/ports",
    }
    info = {
        "owned": {
            "NetworkSettings": {
                "Ports": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "10000"}]}
            }
        }
    }
    request = Mock(
        side_effect=worker.urlerror.HTTPError("redacted", status, "revoked", None, None)
    )
    monkeypatch.setattr(worker.urlrequest, "urlopen", request)
    snapshot = {}
    worker.publish_entry_points(execution.manifest, snapshot, info)
    worker.publish_entry_points(execution.manifest, snapshot, info)
    assert snapshot["entry_points_revoked"] and request.call_count == 1
