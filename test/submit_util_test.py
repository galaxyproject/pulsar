"""Status messages published by ``pulsar-submit`` and ``pulsar-finish``.

TES and similar sequential coexecution environments run ``pulsar-submit
--no-wait``, the tool container and ``pulsar-finish`` one after another, each
with its own short-lived Pulsar app. Galaxy only learns a job's state from the
status messages those apps publish.
"""
import os
import socket
import subprocess
import uuid

import pytest

from pulsar.client.amqp_exchange import (
    DEFAULT_EXCHANGE_NAME,
    DEFAULT_EXCHANGE_TYPE,
)
from pulsar.client.staging.models import ClientOutputs
from pulsar.client.util import to_base64_json
from pulsar.main import ArgumentParser
from pulsar.scripts import (
    finish,
    submit,
)
from pulsar.scripts.submit_util import (
    add_common_submit_args,
    CoexecutionConfigBuilder,
    EXIT_FAILURE,
    EXIT_SUCCESS,
)
from .test_utils import (
    files_server,
    JobFilesApp,
    server_for_test_app,
    TestApp,
)

kombu = pytest.importorskip("kombu")

JOB_ID = "42"
OUTPUT_NAME = "dataset_1.dat"


class SequentialCoexecution:
    """Run a job the way a TES task's executors do, recording status messages."""

    def __init__(self, tmp_path, files_endpoint, input_action=None, message_queue_url=None):
        self.staging_directory = str(tmp_path / "staging")
        self.galaxy_working = tmp_path / "galaxy_working"
        self.galaxy_working.mkdir()
        self.key_prefix = "submit_util_test_%s" % uuid.uuid4().hex
        self.message_queue_url = message_queue_url or "memory://%s" % self.key_prefix
        self.app_conf = {
            "staging_directory": self.staging_directory,
            "persistence_directory": str(tmp_path / "persisted_data"),
            "message_queue_url": self.message_queue_url,
            "amqp_key_prefix": self.key_prefix,
            # What the Pulsar client sends for a sequential coexecution job.
            "manager": {"type": "coexecution", "monitor": "none"},
        }
        if input_action is None:
            input_action = {"action_type": "message", "contents": "cow file contents\n"}
        job_directory = os.path.join(self.staging_directory, JOB_ID)
        pulsar_input = os.path.join(job_directory, "inputs", "cow")
        pulsar_output = os.path.join(job_directory, "outputs", OUTPUT_NAME)
        client_outputs = ClientOutputs(
            working_directory=str(self.galaxy_working),
            output_files=[str(self.galaxy_output)],
        )
        self.launch_params = {
            "command_line": f"cat '{pulsar_input}' > '{pulsar_output}'",
            "job_id": JOB_ID,
            "setup_params": {"job_id": JOB_ID},
            "setup": True,
            "remote_staging": {
                "setup": [{"name": "cow", "type": "input", "action": input_action}],
                "action_mapper": {
                    "default_action": "remote_transfer",
                    "files_endpoint": files_endpoint,
                },
                "client_outputs": client_outputs.to_dict(),
            },
        }
        self.command_line_path = os.path.join(job_directory, "command_line")
        self._status_queue = kombu.Queue(
            "%s_status_update" % self.key_prefix,
            kombu.Exchange(DEFAULT_EXCHANGE_NAME, DEFAULT_EXCHANGE_TYPE, durable=True),
            routing_key="%s_status_update" % self.key_prefix,
        )
        if message_queue_url is None:
            # Declared up front, as Galaxy's consumer would be, so no message is dropped.
            with kombu.Connection(self.message_queue_url) as connection:
                self._status_queue(connection.default_channel).declare()

    @property
    def galaxy_output(self):
        return self.galaxy_working / OUTPUT_NAME

    def submit(self, wait=False):
        return submit.main([*self._script_args(), "--wait" if wait else "--no-wait"])

    def run_tool(self):
        with open(self.command_line_path) as fh:
            command_line = fh.read()
        subprocess.run(command_line, shell=True, check=True)

    def finish(self):
        return finish.main(self._script_args())

    def published_statuses(self):
        return [payload["status"] for payload in self.published_payloads()]

    def published_payloads(self):
        payloads = []
        with kombu.Connection(self.message_queue_url) as connection:
            queue = self._status_queue(connection.default_channel)
            while True:
                message = queue.get(no_ack=True)
                if message is None:
                    break
                payload = message.decode()
                assert payload["job_id"] == JOB_ID
                payloads.append(payload)
        return payloads

    def _script_args(self):
        return [
            "--base64", to_base64_json(self.launch_params),
            "--app_conf_base64", to_base64_json(self.app_conf),
        ]


@pytest.mark.timeout(60)
def test_no_wait_submit_publishes_running(tmp_path):
    with files_server("/") as server:
        job = SequentialCoexecution(tmp_path, server.application_url)
        assert job.submit() == EXIT_SUCCESS
        assert os.path.exists(job.command_line_path)
        assert job.published_statuses() == ["running"]


@pytest.mark.timeout(60)
def test_sequential_coexecution_publishes_running_then_complete(tmp_path):
    with files_server("/") as server:
        job = SequentialCoexecution(tmp_path, server.application_url)
        assert job.submit() == EXIT_SUCCESS
        job.run_tool()
        assert job.finish() == EXIT_SUCCESS
        assert job.published_statuses() == ["running", "complete"]
        assert job.galaxy_output.read_text() == "cow file contents\n"


@pytest.mark.timeout(60)
def test_no_wait_submit_preprocessing_failure_publishes_failed_only(tmp_path):
    missing_input = str(tmp_path / "missing_input")
    with files_server("/") as server:
        job = SequentialCoexecution(
            tmp_path,
            server.application_url,
            input_action={"action_type": "remote_copy", "source": {"path": missing_input}},
        )
        assert job.submit() == EXIT_FAILURE
        assert not os.path.exists(job.command_line_path)
        assert job.published_statuses() == ["failed"]


@pytest.mark.timeout(60)
def test_no_wait_submit_unreachable_galaxy_publishes_failed_and_exits_non_zero(tmp_path):
    # The TES task stops on a non-zero exit, rather than leaving the tool
    # executor waiting for a command line that is never written.
    files_endpoint = _unreachable_url()
    job = SequentialCoexecution(tmp_path, files_endpoint, input_action=_remote_transfer(files_endpoint))
    assert job.submit() == EXIT_FAILURE
    assert not os.path.exists(job.command_line_path)
    payloads = job.published_payloads()
    assert [payload["status"] for payload in payloads] == ["failed"]
    # Galaxy's runner reports this stderr with the failed job.
    stderr = payloads[0]["stderr"]
    assert stderr.startswith("Pulsar failed to stage inputs or launch the job: ")
    assert files_endpoint.split("//")[1].rstrip("/") in stderr


@pytest.mark.timeout(60)
def test_finish_output_staging_failure_publishes_failed_and_exits_non_zero(tmp_path):
    # A job files server of the test's own, not files_server(): CI points that
    # at a standing external server, which would still accept the outputs.
    with server_for_test_app(TestApp(JobFilesApp("/"))) as server:
        job = SequentialCoexecution(tmp_path, server.application_url)
        assert job.submit() == EXIT_SUCCESS
        job.run_tool()
    # Galaxy's job files API is gone by the time outputs are staged back.
    assert job.finish() == EXIT_FAILURE
    assert job.published_statuses() == ["running", "failed"]
    assert not job.galaxy_output.exists()


@pytest.mark.timeout(60)
def test_no_wait_submit_failure_exits_non_zero_with_unreachable_broker(tmp_path):
    files_endpoint = _unreachable_url()
    job = SequentialCoexecution(
        tmp_path,
        files_endpoint,
        input_action=_remote_transfer(files_endpoint),
        message_queue_url="amqp://guest:guest@127.0.0.1:%d//" % _unused_port(),
    )
    assert job.submit() == EXIT_FAILURE


@pytest.mark.timeout(60)
def test_waiting_submit_failure_still_exits_zero(tmp_path):
    # A Kubernetes Job would replace a failed pod and run the job again.
    files_endpoint = _unreachable_url()
    job = SequentialCoexecution(tmp_path, files_endpoint, input_action=_remote_transfer(files_endpoint))
    assert job.submit(wait=True) == EXIT_SUCCESS
    assert job.published_statuses() == ["failed"]


@pytest.mark.timeout(60)
def test_sequential_coexecution_writes_nothing_to_working_directory(tmp_path, monkeypatch):
    # TES and Kubernetes start these scripts in /, often on a read-only root filesystem.
    working_directory = tmp_path / "working_directory"
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)
    monkeypatch.delenv("PULSAR_CONFIG_TOOL_DEPENDENCY_DIR", raising=False)
    with files_server("/") as server:
        job = SequentialCoexecution(tmp_path, server.application_url)
        assert job.submit() == EXIT_SUCCESS
        job.run_tool()
        assert job.finish() == EXIT_SUCCESS
    assert job.published_statuses() == ["running", "complete"]
    assert list(working_directory.iterdir()) == []


@pytest.mark.parametrize("app_conf, environ, expected", [
    ({}, {}, "none"),
    ({"tool_dependency_dir": "/deps/app"}, {}, "/deps/app"),
    ({}, {"PULSAR_CONFIG_TOOL_DEPENDENCY_DIR": "/deps/env"}, "/deps/env"),
    ({"tool_dependency_dir": "/deps/app"}, {"PULSAR_CONFIG_TOOL_DEPENDENCY_DIR": "/deps/env"}, "/deps/app"),
])
def test_coexecution_tool_dependency_dir_default(monkeypatch, app_conf, environ, expected):
    monkeypatch.delenv("PULSAR_CONFIG_TOOL_DEPENDENCY_DIR", raising=False)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    arg_parser = ArgumentParser()
    add_common_submit_args(arg_parser)
    args = arg_parser.parse_args(["--app_conf_base64", to_base64_json(app_conf)])
    assert CoexecutionConfigBuilder(args).load()["tool_dependency_dir"] == expected


def _unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _unreachable_url():
    return "http://127.0.0.1:%d/" % _unused_port()


def _remote_transfer(files_endpoint):
    return {
        "action_type": "remote_transfer",
        "path": "/galaxy/files/cow",
        "source": {"path": "/galaxy/files/cow"},
        "url": "%sapi/jobs/%s/files?path=/galaxy/files/cow" % (files_endpoint, JOB_ID),
    }
