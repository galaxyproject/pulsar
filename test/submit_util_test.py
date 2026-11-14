"""Status messages published by ``pulsar-submit`` and ``pulsar-finish``.

TES and similar sequential coexecution environments run ``pulsar-submit
--no-wait``, the tool container and ``pulsar-finish`` one after another, each
with its own short-lived Pulsar app. Galaxy only learns a job's state from the
status messages those apps publish.
"""
import os
import subprocess
import uuid

import pytest

from pulsar.client.amqp_exchange import (
    DEFAULT_EXCHANGE_NAME,
    DEFAULT_EXCHANGE_TYPE,
)
from pulsar.client.staging.models import ClientOutputs
from pulsar.client.util import to_base64_json
from pulsar.scripts import (
    finish,
    submit,
)
from .test_utils import files_server

kombu = pytest.importorskip("kombu")

JOB_ID = "42"
OUTPUT_NAME = "dataset_1.dat"


class SequentialCoexecution:
    """Run a job the way a TES task's executors do, recording status messages."""

    def __init__(self, tmp_path, files_endpoint, input_action=None):
        self.staging_directory = str(tmp_path / "staging")
        self.galaxy_working = tmp_path / "galaxy_working"
        self.galaxy_working.mkdir()
        self.key_prefix = "submit_util_test_%s" % uuid.uuid4().hex
        self.message_queue_url = "memory://%s" % self.key_prefix
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
        # Declared up front, as Galaxy's consumer would be, so no message is dropped.
        with kombu.Connection(self.message_queue_url) as connection:
            self._status_queue(connection.default_channel).declare()

    @property
    def galaxy_output(self):
        return self.galaxy_working / OUTPUT_NAME

    def submit(self):
        submit.main([*self._script_args(), "--no-wait"])

    def run_tool(self):
        with open(self.command_line_path) as fh:
            command_line = fh.read()
        subprocess.run(command_line, shell=True, check=True)

    def finish(self):
        finish.main(self._script_args())

    def published_statuses(self):
        statuses = []
        with kombu.Connection(self.message_queue_url) as connection:
            queue = self._status_queue(connection.default_channel)
            while True:
                message = queue.get(no_ack=True)
                if message is None:
                    break
                payload = message.decode()
                assert payload["job_id"] == JOB_ID
                statuses.append(payload["status"])
        return statuses

    def _script_args(self):
        return [
            "--base64", to_base64_json(self.launch_params),
            "--app_conf_base64", to_base64_json(self.app_conf),
        ]


@pytest.mark.timeout(60)
def test_no_wait_submit_publishes_running(tmp_path):
    with files_server("/") as server:
        job = SequentialCoexecution(tmp_path, server.application_url)
        job.submit()
        assert os.path.exists(job.command_line_path)
        assert job.published_statuses() == ["running"]


@pytest.mark.timeout(60)
def test_sequential_coexecution_publishes_running_then_complete(tmp_path):
    with files_server("/") as server:
        job = SequentialCoexecution(tmp_path, server.application_url)
        job.submit()
        job.run_tool()
        job.finish()
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
        job.submit()
        assert not os.path.exists(job.command_line_path)
        assert job.published_statuses() == ["failed"]
