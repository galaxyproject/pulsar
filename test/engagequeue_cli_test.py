"""Execute real prepared Pulsar scripts through the thin scheduler adapter."""

import json
import shlex
import subprocess
import sys
from pathlib import Path
from threading import (
    Event,
    Thread,
)

import pytest

from pulsar.manager_endpoint_util import status_dict
from pulsar.managers import status
from pulsar.managers.queued_cli import CliQueueManager
from pulsar.managers.stateful import (
    JOB_FILE_FINAL_STATUS,
    JOB_FILE_PREPROCESSED,
    JOB_FILE_PREPROCESSING_FAILED,
    JOB_METADATA_SUBMISSION_STARTED,
    StatefulManagerProxy,
)
from pulsar.managers.util.cli.job import job_states
from pulsar.managers.util.cli.job.engagequeue import EngageQueue
from .test_utils import (
    minimal_app_for_managers,
    wait_for,
)

engagequeue = pytest.importorskip("engagequeue", reason="Integration tests require the optional executor installation")
Executor = engagequeue.Executor
PoolConfig = engagequeue.PoolConfig
DOCKER_TEST_IMAGE = "alpine@sha256:25109184c71bdad752c8312a8623239686a9a2071e8825f20acb8f2198c3f659"


def make_manager(tmp_path, **kwargs):
    app = minimal_app_for_managers()
    app.staging_directory = str(tmp_path / "staging")
    app.persistence_directory = str(tmp_path / "persistence")
    return CliQueueManager(
        "_default_",
        app,
        job_plugin="EngageQueue",
        job_executable=str(Path(sys.prefix) / "bin/engagequeue"),
        job_state_dir=str(tmp_path / "executor"),
        **kwargs,
    )


@pytest.fixture
def manager(tmp_path):
    manager = make_manager(tmp_path)
    try:
        yield manager
    finally:
        with Executor(tmp_path / "executor") as executor:
            for job in executor.list():
                if not job.terminal:
                    executor.cancel(job.id, wait=True, timeout=15)
            executor.shutdown(wait=True, timeout=15)


def wait_terminal(manager, job_id):
    return wait_for(
        lambda: manager.get_status(job_id),
        "terminal CLI job",
        until=lambda value: value in (status.COMPLETE, status.CANCELLED, status.FAILED),
        timeout=15,
        interval=0.05,
    )


def test_adapter_prepared_script_runs_and_setup_attempts_are_distinct(manager):
    first = manager.setup_job("same-galaxy-id", "tool", "1")
    second = manager.setup_job("same-galaxy-id", "tool", "1")
    assert first != second
    manager.launch(first, "printf 'exact result' > ../outputs/result")
    assert wait_terminal(manager, first) == status.COMPLETE
    assert Path(manager.job_directory(first).outputs_directory(), "result").read_text() == "exact result"
    assert manager.return_code(first) == 0


def test_foreground_jobs_obey_serial_pool_admission_without_pulsar_polling(manager, tmp_path):
    with Executor(tmp_path / "executor", pools={"serial": PoolConfig(max_jobs=1)}):
        pass
    manager.job_params["pool"] = "serial"
    first = manager.setup_job("serial-first", "tool", "1")
    second = manager.setup_job("serial-second", "tool", "1")
    first_root = Path(manager.job_directory(first).job_directory)
    second_root = Path(manager.job_directory(second).job_directory)
    manager.launch(first, "printf one > ../outputs/count; while [ ! -e ../release ]; do sleep .05; done")
    wait_for(lambda: (first_root / "outputs/count").exists(), "first foreground job start", timeout=10)
    manager.launch(second, "printf one > ../outputs/count")
    assert manager.get_status(second) == status.QUEUED
    assert not (second_root / "outputs/count").exists()
    (first_root / "release").touch()
    wait_for(lambda: (second_root / "outputs/count").exists(), "offline serial queue admission", timeout=15)
    replacement = make_manager(tmp_path, job_pool="serial")
    assert wait_terminal(replacement, first) == status.COMPLETE
    assert wait_terminal(replacement, second) == status.COMPLETE
    assert (first_root / "outputs/count").read_text() == (second_root / "outputs/count").read_text() == "one"


def test_foreground_command_failure_preserves_real_exit_code(manager):
    job_id = manager.setup_job("foreground-error", "tool", "1")
    manager.launch(job_id, "printf 'failure details' >&2; exit 7")
    assert wait_terminal(manager, job_id) == status.FAILED
    assert manager.return_code(job_id) == 7
    with Executor(manager.job_params["state_dir"]) as executor:
        receipt = executor.inspect(manager._external_id(job_id))
        assert receipt["returncode"] == 7 and receipt["writers_stopped"]


@pytest.mark.parametrize("action", ["cancel", "shutdown"])
def test_accepted_execution_survives_delayed_submit_response_until_confirmed_stop(manager, tmp_path, monkeypatch, action):
    proxy = StatefulManagerProxy(manager, min_polling_interval=0)
    job_id = proxy.setup_job("delayed-response", "tool", "1")
    directory = manager.job_directory(job_id)
    root = Path(directory.job_directory)
    accepted, release_reply = Event(), Event()
    shell, _ = manager.cli_interface.get_plugins(manager.shell_params, manager.job_params)
    original_execute = shell.execute
    errors = []
    restored = None

    def hold_submit_reply(command, *args, **kwargs):
        result = original_execute(command, *args, **kwargs)
        if "submit" in shlex.split(command):
            accepted.set()
            assert release_reply.wait(30)
        return result

    def launch():
        try:
            proxy.preprocess_and_launch(
                job_id,
                {"command_line": "printf one > ../outputs/count; while [ ! -e ../release ]; do sleep .05; done", "remote_staging": {}},
            )
        except Exception as error:
            errors.append(error)

    monkeypatch.setattr(shell, "execute", hold_submit_reply)
    thread = Thread(target=launch)
    thread.start()
    try:
        assert accepted.wait(15)
        wait_for(lambda: (root / "outputs/count").exists(), "accepted foreground writer", timeout=10)
        assert manager._external_id(job_id) is None
        assert directory.has_metadata(JOB_METADATA_SUBMISSION_STARTED)
        assert not directory.has_metadata(JOB_FILE_PREPROCESSED)
        with Executor(tmp_path / "executor") as executor:
            execution = executor.lookup(EngageQueue.submission_key(root / "command.sh"))
            assert execution is not None
            accepted_id = execution.id
            assert executor.status(accepted_id).state.value == "RUNNING"
        if action == "cancel":
            delivered = []
            original_kill = manager._kill_external
            monkeypatch.setattr(manager, "_kill_external", lambda external_id: delivered.append(external_id))
            proxy.kill(job_id)
            assert status_dict(proxy, job_id) == {"complete": "false", "status": status.RUNNING, "job_id": job_id}
            assert delivered == [accepted_id]
            assert root.exists() and not directory.has_metadata(JOB_FILE_FINAL_STATUS)
            monkeypatch.setattr(manager, "_kill_external", original_kill)
            assert wait_terminal(proxy, job_id) == status.CANCELLED
            with Executor(tmp_path / "executor") as executor:
                assert executor.inspect(accepted_id)["writers_stopped"]
            release_reply.set()
            thread.join(timeout=15)
            assert not thread.is_alive()
            assert job_id not in proxy.active_jobs.active_job_ids()
            assert directory.load_metadata(JOB_FILE_FINAL_STATUS) == status.CANCELLED
            assert not (root / "release").exists()
        else:
            proxy.shutdown()
            assert not manager._was_cancelled(job_id)
            with Executor(tmp_path / "executor") as executor:
                assert executor.status(accepted_id).state.value == "RUNNING"
            release_reply.set()
            thread.join(timeout=15)
            assert not thread.is_alive()
            assert not directory.has_metadata(JOB_FILE_PREPROCESSING_FAILED)
            replacement = make_manager(tmp_path)
            restored = StatefulManagerProxy(replacement, min_polling_interval=0)
            restored.recover_active_jobs()
            assert replacement._external_id(job_id) == accepted_id
            assert status_dict(restored, job_id) == {"complete": "false", "status": status.RUNNING, "job_id": job_id}
            (root / "release").touch()
            assert wait_terminal(restored, job_id) == status.COMPLETE
        assert not errors
        assert (root / "outputs/count").read_text() == "one"
    finally:
        release_reply.set()
        thread.join(timeout=15)
        if restored is not None:
            restored.shutdown()
        proxy.shutdown()


def test_cancellation_winning_at_submit_boundary_prevents_dispatch(manager, monkeypatch):
    proxy = StatefulManagerProxy(manager, min_polling_interval=0)
    job_id = proxy.setup_job("cancel-at-dispatch", "tool", "1")
    directory = manager.job_directory(job_id)
    was_cancelled = manager._was_cancelled
    checks = []
    shell, _ = manager.cli_interface.get_plugins(manager.shell_params, manager.job_params)

    def cancel_at_boundary(identifier):
        checks.append(identifier)
        if len(checks) == 2:
            manager._record_cancel(identifier)
        return was_cancelled(identifier)

    def unexpected_dispatch(*args, **kwargs):
        raise AssertionError("Cancellation won before submission; no CLI may run")

    monkeypatch.setattr(manager, "_was_cancelled", cancel_at_boundary)
    monkeypatch.setattr(shell, "execute", unexpected_dispatch)
    try:
        proxy.preprocess_and_launch(job_id, {"command_line": "never-executed", "remote_staging": {}})
        assert len(checks) >= 2
        assert proxy.get_status(job_id) == status.CANCELLED
        assert not directory.has_metadata(JOB_METADATA_SUBMISSION_STARTED)
        assert not directory.has_metadata(JOB_FILE_PREPROCESSING_FAILED)
        assert job_id not in proxy.active_jobs.active_job_ids()
    finally:
        proxy.shutdown()


def test_stateful_restart_adopts_original_execution_without_repeating(manager, tmp_path):
    proxy = StatefulManagerProxy(manager, min_polling_interval=0)
    job_id = proxy.setup_job("restart", "tool", "1")
    script = "printf one >> ../outputs/count; while [ ! -e ../release ]; do sleep .05; done"
    proxy.preprocess_and_launch(job_id, {"command_line": script, "remote_staging": {}})
    wait_for(lambda: Path(manager.job_directory(job_id).outputs_directory(), "count").exists(), "command start", timeout=10)
    external_id = manager._external_id(job_id)
    proxy.shutdown()
    replacement = make_manager(tmp_path)
    restored = StatefulManagerProxy(replacement, min_polling_interval=0)
    restored.recover_active_jobs()
    assert replacement._external_id(job_id) == external_id
    Path(manager.job_directory(job_id).job_directory, "release").touch()
    assert wait_terminal(restored, job_id) == status.COMPLETE
    assert Path(manager.job_directory(job_id).outputs_directory(), "count").read_text() == "one"
    restored.shutdown()


def test_missing_external_id_is_looked_up_without_submit_replay(manager, tmp_path):
    job_id = manager.setup_job("lost-reply", "tool", "1")
    manager.launch(job_id, "printf one >> ../outputs/count")
    expected = manager._external_id(job_id)
    manager.job_directory(job_id).remove_file("external_id")
    replacement = make_manager(tmp_path)
    replacement._recover_active_job(job_id)
    assert replacement._external_id(job_id) == expected
    assert wait_terminal(replacement, job_id) == status.COMPLETE
    assert Path(manager.job_directory(job_id).outputs_directory(), "count").read_text() == "one"


def test_cancel_reports_terminal_only_after_owned_writer_stops(manager):
    job_id = manager.setup_job("cancel", "tool", "1")
    manager.launch(job_id, "printf started > ../outputs/started; sleep 30")
    wait_for(lambda: Path(manager.job_directory(job_id).outputs_directory(), "started").exists(), "writer start", timeout=10)
    manager.kill(job_id)
    assert wait_terminal(manager, job_id) == status.CANCELLED
    with Executor(Path(manager.job_params["state_dir"])) as executor:
        actual = executor.status(manager._external_id(job_id))
        assert actual.state.value == "CANCELLED" and actual.terminal
    assert manager.return_code(job_id) != 0


def test_per_job_resource_overrides_are_allowlisted(manager):
    job_id = manager.setup_job("limits", "tool", "1")
    requests = {"timeout": 0.2, "cpus": 2, "memory_mb": 256, "output_limit": 4096}
    manager.launch(job_id, "sleep 30", submit_params={**requests, "state_dir": "/untrusted", "executable": "/untrusted"})
    assert wait_terminal(manager, job_id) == status.FAILED
    assert manager.return_code(job_id) != 0
    with Executor(manager.job_params["state_dir"]) as executor:
        assert executor.status(manager._external_id(job_id)).returncode == 124
        accepted = executor.inspect(manager._external_id(job_id))["spec"]
        assert {name: accepted[name] for name in requests} == requests


def test_adapter_quotes_paths_and_supports_relative_container_sidecars(tmp_path):
    plugin = EngageQueue(
        state_dir=str(tmp_path / "state with spaces"),
        executable="/configured/bin/engagequeue",
        attach_only=True,
        container_spec="metadata/containers.json",
    )
    script = tmp_path / "job with spaces" / "command.sh"
    arguments = shlex.split(plugin.submit(str(script)))
    assert arguments[0] == "/configured/bin/engagequeue" and "--attach-only" in arguments
    assert arguments[arguments.index("--execution-mode") + 1] == "local"
    assert arguments.index("--attach-only") < arguments.index("submit")
    assert arguments.index("--execution-mode") < arguments.index("submit")
    assert arguments[arguments.index("--container-spec") + 1] == str(script.parent / "metadata/containers.json")


@pytest.mark.parametrize(
    "state,expected", [("STOPPING", job_states.RUNNING), ("LOST", job_states.RUNNING), ("FAILED", job_states.ERROR), ("SUCCEEDED", job_states.OK)]
)
def test_nonterminal_uncertainty_does_not_authorize_collection(state, expected):
    plugin = EngageQueue(state_dir="/unused")
    assert plugin.parse_single_status(json.dumps({"id": "job", "state": state}), "job") == expected


def test_crash_after_acceptance_before_id_persistence_is_discoverable(tmp_path):
    child = r"""
import os,sys
from pathlib import Path
from pulsar.managers.queued_cli import CliQueueManager
from pulsar.managers.stateful import StatefulManagerProxy
from test.test_utils import minimal_app_for_managers
root=Path(sys.argv[1]); app=minimal_app_for_managers()
app.staging_directory=str(root/'staging');app.persistence_directory=str(root/'persistence')
manager=CliQueueManager('_default_',app,job_plugin='EngageQueue',job_executable=str(Path(sys.prefix)/'bin/engagequeue'),job_state_dir=str(root/'executor'))
proxy=StatefulManagerProxy(manager,min_polling_interval=0)
job=proxy.setup_job('crash','tool','1');(root/'job-id').write_text(job)
def crash(*args): os._exit(91)
manager._register_external_id=crash
proxy.preprocess_and_launch(job,{'command_line':'printf one >> ../outputs/count; while [ ! -e ../release ]; do sleep .05; done','remote_staging':{}})
"""
    result = subprocess.run([sys.executable, "-c", child, str(tmp_path)], capture_output=True, timeout=20)
    assert result.returncode == 91, result.stderr.decode()
    job_id = (tmp_path / "job-id").read_text()
    replacement = make_manager(tmp_path)
    proxy = StatefulManagerProxy(replacement, min_polling_interval=0)
    try:
        assert job_id in proxy.active_jobs.active_job_ids()
        proxy.recover_active_jobs()
        assert replacement._external_id(job_id)
        Path(replacement.job_directory(job_id).job_directory, "release").touch()
        assert wait_terminal(proxy, job_id) == status.COMPLETE
        assert Path(replacement.job_directory(job_id).outputs_directory(), "count").read_text() == "one"
    finally:
        proxy.shutdown()
        with Executor(tmp_path / "executor") as executor:
            for job in executor.list():
                if not job.terminal:
                    executor.cancel(job.id, wait=True, timeout=15)
            executor.shutdown(wait=True, timeout=15)


def test_cancel_request_marker_alone_is_not_confirmation(manager, monkeypatch):
    job_id = manager.setup_job("cancel-marker", "tool", "1")
    manager.launch(job_id, "printf started > ../outputs/started; sleep 30")
    wait_for(lambda: Path(manager.job_directory(job_id).outputs_directory(), "started").exists(), "writer start", timeout=10)
    manager._record_cancel(job_id)
    original_kill = manager._kill_external
    monkeypatch.setattr(manager, "_kill_external", lambda external_id: None)
    assert manager.get_status(job_id) == status.RUNNING
    monkeypatch.setattr(manager, "_kill_external", original_kill)
    assert wait_terminal(manager, job_id) == status.CANCELLED


def test_cancel_before_id_recovery_stops_original_execution(manager, tmp_path):
    job_id = manager.setup_job("cancel-lost-id", "tool", "1")
    root = Path(manager.job_directory(job_id).job_directory)
    manager.launch(
        job_id,
        "printf one >> ../outputs/count; while [ ! -e ../release ]; do sleep .05; done; printf escaped > ../outputs/released",
    )
    wait_for(lambda: (root / "outputs/count").exists(), "accepted writer start", timeout=10)
    accepted_id = manager._external_id(job_id)
    manager.job_directory(job_id).remove_file("external_id")
    replacement = make_manager(tmp_path)
    replacement.kill(job_id)
    assert replacement._external_id(job_id) is None
    assert replacement._was_cancelled(job_id)
    with Executor(manager.job_params["state_dir"]) as executor:
        assert executor.status(accepted_id).state.value == "RUNNING"
    assert wait_terminal(replacement, job_id) == status.CANCELLED
    assert replacement._external_id(job_id) == accepted_id
    with Executor(manager.job_params["state_dir"]) as executor:
        receipt = executor.inspect(accepted_id)
        assert receipt["state"] == "CANCELLED" and receipt["writers_stopped"]
        assert [job.id for job in executor.list()] == [accepted_id]
    assert not (root / "release").exists()
    assert not (root / "outputs/released").exists()
    assert (root / "outputs/count").read_text() == "one"


def test_polling_retries_failed_cancel_delivery(manager, monkeypatch):
    job_id = manager.setup_job("cancel-transport", "tool", "1")
    root = Path(manager.job_directory(job_id).job_directory)
    manager.launch(job_id, "printf one > ../outputs/count; while [ ! -e ../release ]; do sleep .05; done")
    wait_for(lambda: (root / "outputs/count").exists(), "accepted writer start", timeout=10)
    accepted_id = manager._external_id(job_id)
    original_kill = manager._kill_external
    attempts = []

    def fail_once(external_id):
        attempts.append(external_id)
        if len(attempts) == 1:
            raise RuntimeError("simulated cancellation transport failure")
        original_kill(external_id)

    monkeypatch.setattr(manager, "_kill_external", fail_once)
    manager.kill(job_id)
    assert attempts == [accepted_id]
    assert manager._was_cancelled(job_id)
    with Executor(manager.job_params["state_dir"]) as executor:
        assert executor.status(accepted_id).state.value == "RUNNING"
    assert wait_terminal(manager, job_id) == status.CANCELLED
    assert len(attempts) >= 2 and set(attempts) == {accepted_id}
    with Executor(manager.job_params["state_dir"]) as executor:
        receipt = executor.inspect(accepted_id)
        assert receipt["state"] == "CANCELLED" and receipt["writers_stopped"]
    assert not (root / "release").exists()
    assert (root / "outputs/count").read_text() == "one"


def test_failed_id_persistence_recovers_in_same_controller(manager):
    original = manager._register_external_id
    calls = []

    def fail_once(*args):
        calls.append(True)
        if len(calls) == 1:
            raise OSError("simulated failed ID persistence")
        return original(*args)

    manager._register_external_id = fail_once
    proxy = StatefulManagerProxy(manager, min_polling_interval=0)
    job_id = proxy.setup_job("uncertain", "tool", "1")
    proxy.preprocess_and_launch(job_id, {"command_line": "printf one >> ../outputs/count; sleep .2", "remote_staging": {}})
    assert job_id in proxy.active_jobs.active_job_ids()
    assert wait_terminal(proxy, job_id) == status.COMPLETE
    assert Path(manager.job_directory(job_id).outputs_directory(), "count").read_text() == "one"


def test_missing_submission_remains_nonterminal_without_replay(manager):
    proxy = StatefulManagerProxy(manager, min_polling_interval=0)
    job_id = proxy.setup_job("not-accepted", "tool", "1")
    proxy.active_jobs.activate_job(job_id)
    proxy.recover_active_jobs()
    assert proxy.get_status(job_id) == status.QUEUED
    assert not status.is_job_done(proxy.get_status(job_id))
    assert status_dict(proxy, job_id) == {"complete": "false", "status": status.QUEUED, "job_id": job_id}
    assert job_id in proxy.active_jobs.active_job_ids()
    assert manager.job_directory(job_id).exists()
    with Executor(manager.job_params["state_dir"]) as executor:
        assert executor.list() == []


def test_unknown_submission_transport_does_not_become_failed_or_complete(manager, monkeypatch):
    from galaxy.util.bunch import Bunch

    proxy = StatefulManagerProxy(manager, min_polling_interval=0)
    job_id = proxy.setup_job("unknown-transport", "tool", "1")
    proxy.active_jobs.activate_job(job_id)
    shell, _ = manager.cli_interface.get_plugins(manager.shell_params, manager.job_params)
    monkeypatch.setattr(shell, "execute", lambda *args, **kwargs: Bunch(returncode=124, stdout="", stderr="transport timed out"))
    proxy.recover_active_jobs()
    assert proxy.get_status(job_id) == status.QUEUED
    assert not status.is_job_done(proxy.get_status(job_id))
    assert status_dict(proxy, job_id) == {"complete": "false", "status": status.QUEUED, "job_id": job_id}
    assert job_id in proxy.active_jobs.active_job_ids()


def test_known_execution_transport_failure_remains_nonterminal(manager, monkeypatch):
    from galaxy.util.bunch import Bunch

    job_id = manager.setup_job("unknown-status", "tool", "1")
    manager.launch(job_id, "sleep 30")
    shell, _ = manager.cli_interface.get_plugins(manager.shell_params, manager.job_params)
    monkeypatch.setattr(shell, "execute", lambda *args, **kwargs: Bunch(returncode=124, stdout="", stderr="transport timed out"))
    assert manager.get_status(job_id) == status.RUNNING
    assert not status.is_job_done(manager.get_status(job_id))
    assert status_dict(manager, job_id) == {"complete": "false", "status": status.RUNNING, "job_id": job_id}
    assert manager.job_directory(job_id).exists()


@pytest.mark.parametrize("known_id", [False, True])
def test_managed_profile_during_recovery_remains_nonterminal(tmp_path, known_id):
    state_dir = tmp_path / "executor"
    state_dir.mkdir()
    marker = state_dir / "managed.json"
    marker.write_text("{}")
    manager = make_manager(tmp_path)
    try:
        job_id = manager.setup_job("profile-recovery", "tool", "1")
        if known_id:
            manager._register_external_id(job_id, "already-accepted")
        expected = status.RUNNING if known_id else status.QUEUED
        assert status_dict(manager, job_id) == {"complete": "false", "status": expected, "job_id": job_id}
        assert manager.job_directory(job_id).exists()
        assert not manager.job_directory(job_id).has_metadata("final_status")
        assert marker.read_text() == "{}"
    finally:
        manager.shutdown()


@pytest.mark.parametrize("known_id", [False, True])
def test_missing_state_configuration_during_recovery_remains_nonterminal(tmp_path, known_id):
    manager = make_manager(tmp_path)
    try:
        job_id = manager.setup_job("missing-state-recovery", "tool", "1")
        if known_id:
            manager._register_external_id(job_id, "already-accepted")
        del manager.job_params["state_dir"]
        expected = status.RUNNING if known_id else status.QUEUED
        assert status_dict(manager, job_id) == {"complete": "false", "status": expected, "job_id": job_id}
        assert manager.job_directory(job_id).exists()
        assert not manager.job_directory(job_id).has_metadata("final_status")
    finally:
        manager.shutdown()


@pytest.mark.parametrize("cancel_before_acceptance", [False, True])
def test_controller_crash_before_acceptance_retains_and_adopts_late_job(manager, tmp_path, cancel_before_acceptance):
    executable = str(Path(sys.prefix) / "bin/engagequeue")
    wrapper = tmp_path / "gated-engagequeue"
    wrapper.write_text(
        "#!" + sys.executable + "\n" + f"""
import os
import sys
import time
from pathlib import Path
root = Path({str(tmp_path)!r})
if 'submit' in sys.argv[1:]:
    (root / 'submit-started').touch()
    while not (root / 'submit-release').exists():
        time.sleep(.01)
os.execv({executable!r}, [{executable!r}] + sys.argv[1:])
"""
    )
    wrapper.chmod(0o700)
    child_script = r"""
import sys
from pathlib import Path
from pulsar.managers.queued_cli import CliQueueManager
from pulsar.managers.stateful import StatefulManagerProxy
from test.test_utils import minimal_app_for_managers
root=Path(sys.argv[1]); app=minimal_app_for_managers()
app.staging_directory=str(root/'staging'); app.persistence_directory=str(root/'persistence')
manager=CliQueueManager('_default_',app,job_plugin='EngageQueue',job_executable=str(root/'gated-engagequeue'),job_state_dir=str(root/'executor'))
proxy=StatefulManagerProxy(manager,min_polling_interval=0)
job=proxy.setup_job('before-acceptance','tool','1'); (root/'job-id').write_text(job)
command='printf one >> ../outputs/count; while [ ! -e ../execution-release ]; do sleep .05; done'
proxy.preprocess_and_launch(job,{'command_line':command,'remote_staging':{}})
"""
    child = None
    restored = None
    submission_key = None
    try:
        with (tmp_path / "original-controller.log").open("wb") as output:
            child = subprocess.Popen([sys.executable, "-c", child_script, str(tmp_path)], stdout=output, stderr=subprocess.STDOUT)
            wait_for(lambda: (tmp_path / "submit-started").exists(), "original submit CLI held before acceptance", timeout=15)
            child.kill()
            child.wait(timeout=10)
        job_id = (tmp_path / "job-id").read_text()
        replacement = make_manager(tmp_path)
        root = Path(replacement.job_directory(job_id).job_directory)
        submission_key = EngageQueue.submission_key(root / "command.sh")
        restored = StatefulManagerProxy(replacement, min_polling_interval=0)
        restored.recover_active_jobs()
        if cancel_before_acceptance:
            replacement.kill(job_id)
            assert replacement._was_cancelled(job_id)
        observed = restored.get_status(job_id)
        assert observed == status.QUEUED and not status.is_job_done(observed)
        response = status_dict(restored, job_id)
        assert response == {"complete": "false", "status": status.QUEUED, "job_id": job_id}
        assert "outputs_directory_contents" not in response and "job_directory_contents" not in response
        assert job_id in restored.active_jobs.active_job_ids()
        assert root.exists()
        assert not replacement.job_directory(job_id).has_metadata("final_status")
        with Executor(tmp_path / "executor") as executor:
            assert executor.list() == []
        (tmp_path / "submit-release").touch()
        wait_for(lambda: (root / "outputs/count").exists(), "late original acceptance and command start", timeout=15)
        with Executor(tmp_path / "executor") as executor:
            accepted_id = executor.lookup(submission_key).id
        if not cancel_before_acceptance:
            assert restored.get_status(job_id) == status.RUNNING
            (root / "execution-release").touch()
        expected = status.CANCELLED if cancel_before_acceptance else status.COMPLETE
        assert wait_terminal(restored, job_id) == expected
        assert (root / "outputs/count").read_text() == "one"
        with Executor(tmp_path / "executor") as executor:
            assert [job.id for job in executor.list()] == [accepted_id]
            receipt = executor.inspect(accepted_id)
            assert receipt["writers_stopped"]
            assert receipt["state"] == ("CANCELLED" if cancel_before_acceptance else "SUCCEEDED")
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        (tmp_path / "submit-release").touch()
        if restored is not None:
            restored.shutdown()
        if submission_key is not None:
            with Executor(tmp_path / "executor") as executor:
                wait_for(lambda: executor.lookup(submission_key), "original launcher acceptance before cleanup", timeout=15)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux Docker ownership integration is tested separately from native macOS")
def test_real_docker_sidecar_stops_all_owned_containers_even_after_script_exit(manager):
    import os
    import shutil

    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    available = subprocess.run(["docker", "image", "inspect", DOCKER_TEST_IMAGE], capture_output=True)
    if available.returncode:
        pytest.skip("Cached Alpine image and Docker daemon are required")
    job_id = manager.setup_job("containers", "tool", "1")
    root = Path(manager.job_directory(job_id).job_directory)
    names = ["engagequeue-pulsar-" + job_id[:16] + suffix for suffix in ("-tool", "-metadata")]
    descriptors = [{"name": name, "label_value": job_id} for name in names]
    sidecar = root / "metadata/containers.json"
    sidecar.write_text(json.dumps(descriptors))
    manager.job_params["container_spec"] = "metadata/containers.json"
    command = "; ".join(
        " ".join(
            shlex.quote(str(value))
            for value in [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                name,
                "--label",
                "engagequeue.attempt=" + job_id,
                "--user",
                str(os.getuid()) + ":" + str(os.getgid()),
                "--volume",
                str(root / "outputs") + ":/outputs",
                DOCKER_TEST_IMAGE,
                "/bin/sh",
                "-c",
                "printf ready > /outputs/" + name + "; sleep 30",
            ]
        )
        for name in names
    )
    try:
        manager.launch(job_id, command)
        for name in names:
            wait_for(lambda name=name: (root / "outputs" / name).exists(), "owned container start", timeout=15)
        wait_for(lambda: manager.return_code(job_id) == 0, "prepared script exit", timeout=10)
        assert manager.get_status(job_id) == status.RUNNING
        manager.kill(job_id)
        assert wait_terminal(manager, job_id) == status.CANCELLED
        assert manager.return_code(job_id) != 0
        for name in names:
            assert subprocess.run(["docker", "inspect", name], capture_output=True).returncode != 0
    finally:
        for name in names:
            inspected = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
            if not inspected.returncode:
                data = json.loads(inspected.stdout)[0]
                if data.get("Config", {}).get("Labels", {}).get("engagequeue.attempt") == job_id:
                    subprocess.run(["docker", "rm", "-f", data["Id"]], capture_output=True)
