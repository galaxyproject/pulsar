import os
import re
import tempfile
from collections import deque
from types import SimpleNamespace
from unittest.mock import (
    patch,
    PropertyMock,
)

import pytest

from pulsar import __version__ as pulsar_version
from pulsar.client.client import JobClient
from pulsar.client.coexecution_manager import CoexecutionPollingJobClientManager
from pulsar.client.container_job_config import CoexecutionContainerCommand
from pulsar.client.decorators import (
    MAX_RETRY_COUNT,
    retry,
)
from pulsar.client.gcp import (
    GcpMessageCoexecutionJobClient,
    GcpPollingCoexecutionJobClient,
    LaunchesGcpContainersMixin,
)
from pulsar.client.manager import HttpPulsarInterface
from pulsar.client.tes import TesPollingCoexecutionJobClient
from pulsar.client.transport import UrllibTransport
from pulsar.managers.util.gcp_util import GcpAlreadyExists


def test_with_retry():
    i = []

    @retry()
    def func():
        i.append(0)
        raise Exception
    exception_raised = False
    try:
        func()
    except Exception:
        exception_raised = True
    assert exception_raised
    assert len(i) == MAX_RETRY_COUNT, len(i)


class FakeResponse:
    """ Object meant to simulate a Response object as returned by
    urllib.open """

    def __init__(self, body):
        self.body = body
        self.first_read = True

    def read(self, bytes=1024):
        if self.first_read:
            result = self.body
        else:
            result = b""
        self.first_read = False
        return result


class TestTransport(UrllibTransport):
    """ Implements mock of HTTP transport layer for TestClient tests."""

    def __init__(self, test_client):
        self.test_client = test_client

    def _url_open(self, request, data):
        (checker, response) = self.test_client.expects.pop()
        checker(request, data)
        return FakeResponse(response)


class TestClient(JobClient):
    """ A dervative of the Client class that replaces the url_open
    method so that requests can be inspected and responses faked."""

    def __init__(self):
        JobClient.__init__(self, {}, "543", HttpPulsarInterface({"url": "http://test:803/"}, TestTransport(self)))
        self.expects = deque()

    def expect_open(self, checker, response):
        self.expects.appendleft((checker, response))


class RequestChecker:
    """ Class that tests request objects produced by the Client class.
    """
    def __init__(self, action, args=None, data=None):
        if args is None:
            args = {}
        args['job_id'] = "543"
        self.action = action
        self.expected_args = args
        self.data = data
        self.called = False

    def check_url(self, opened_url):
        expected_url_prefix = "http://test:803/%s?" % self.action
        assert opened_url.startswith(expected_url_prefix)
        url_suffix = opened_url[len(expected_url_prefix):]
        actual_args = dict([key_val_combo.split("=") for key_val_combo in url_suffix.split("&")])
        statement = f"Expected args {self.expected_args}, obtained {actual_args}"
        assert self.expected_args == actual_args, statement

    def check_data(self, data):
        if data is None:
            assert self.data is None
        elif type(data) in (bytes, str):
            assert self.data == data
        else:
            data_read = data.read(1024)
            assert data_read == self.data, f"data_read {data_read} is not expected data {self.data}"

    def __call__(self, request, data=None):
        self.called = True
        self.check_url(request.get_full_url())
        self.check_data(data)

    def assert_called(self):
        assert self.called


def test_setup():
    """ Test the setup method of Client """
    client = TestClient()
    request_checker = RequestChecker("jobs", {"use_metadata": "true"})
    response_json = b'{"working_directory":"C:\\\\home\\\\dir","outputs_directory" : "C:\\\\outputs","path_separator" : "\\\\"}'
    client.expect_open(request_checker, response_json)
    setup_response = client.setup()
    request_checker.assert_called()
    assert setup_response['working_directory'] == "C:\\home\\dir"
    assert setup_response['outputs_directory'] == "C:\\outputs"
    assert setup_response['path_separator'] == '\\'
    assert setup_response['pulsar_version_source'] == "remote"


def test_local_setup_reports_version_came_from_client():
    job_config = _jobs_directory_client().setup()
    assert job_config["pulsar_version"] == pulsar_version
    assert job_config["pulsar_version_source"] == "client"


def test_local_setup_reports_declared_remote_version():
    job_config = _jobs_directory_client(remote_pulsar_version="0.15.2").setup()
    assert job_config["pulsar_version"] == "0.15.2"
    assert job_config["pulsar_version_source"] == "destination"


def test_local_setup_knows_version_of_published_staging_image():
    job_config = _jobs_directory_client(pulsar_container_image="galaxy/pulsar-pod-staging:0.15.0.2").setup()
    assert job_config["pulsar_version"] == "0.15.0.dev1"
    assert job_config["pulsar_version_source"] == "container_image"


def test_local_setup_prefers_declared_version_over_staging_image():
    job_config = _jobs_directory_client(
        pulsar_container_image="galaxy/pulsar-pod-staging:0.15.0.2", remote_pulsar_version="0.16.0"
    ).setup()
    assert job_config["pulsar_version"] == "0.16.0"
    assert job_config["pulsar_version_source"] == "destination"


def test_local_setup_unknown_staging_image_reports_client_version():
    job_config = _jobs_directory_client(pulsar_container_image="example/custom-pulsar:latest").setup()
    assert job_config["pulsar_version_source"] == "client"


def test_local_setup_rejects_unquoted_remote_version():
    # YAML reads an unquoted 0.20 as 0.2, so the declared version is already lost.
    with pytest.raises(ValueError, match="remote_pulsar_version must be a string"):
        _jobs_directory_client(remote_pulsar_version=0.2)


def test_local_setup_rejects_malformed_remote_version():
    # Galaxy compares it as a version, so catch a typo here with a clear message.
    with pytest.raises(ValueError, match="remote_pulsar_version must be a version"):
        _jobs_directory_client(remote_pulsar_version="latest")


def _jobs_directory_client(**destination_params):
    interface = HttpPulsarInterface({"url": "http://test:803/"}, TestTransport(None))
    return JobClient({"jobs_directory": "/pulsar/staging", **destination_params}, "543", interface)


def test_launch():
    """ Test the launch method of client. """
    client = TestClient()
    request_checker = RequestChecker("jobs/543/submit", {"command_line": "python"})
    client.expect_open(request_checker, 'OK')
    client.launch("python")
    request_checker.assert_called()


def __test_upload(upload_type):
    client = TestClient()
    (temp_fileno, temp_file_path) = tempfile.mkstemp()
    temp_file = os.fdopen(temp_fileno, 'w')
    try:
        temp_file.write("Hello World!")
    finally:
        temp_file.close()
    request_checker = RequestChecker("jobs/543/files", {"name": os.path.basename(temp_file_path), "type": upload_type}, b"Hello World!")
    client.expect_open(request_checker, b'{"path" : "C:\\\\tools\\\\foo"}')

    if upload_type == 'tool':
        upload_result = client.put_file(temp_file_path, 'tool')
    else:
        upload_result = client.put_file(temp_file_path, 'input')

    request_checker.assert_called()
    assert upload_result["path"] == "C:\\tools\\foo"


def test_upload_tool():
    __test_upload("tool")


def test_upload_input():
    __test_upload("input")


def test_upload_config():
    client = TestClient()
    (temp_fileno, temp_file_path) = tempfile.mkstemp()
    temp_file = os.fdopen(temp_fileno, 'w')
    try:
        temp_file.write("Hello World!")
    finally:
        temp_file.close()
    modified_contents = b"Hello World! <Modified>"
    request_checker = RequestChecker("jobs/543/files", {"name": os.path.basename(temp_file_path), "type": "config"}, modified_contents)
    client.expect_open(request_checker, b'{"path" : "C:\\\\tools\\\\foo"}')
    upload_result = client.put_file(temp_file_path, 'config', contents=modified_contents)
    request_checker.assert_called()
    assert upload_result["path"] == "C:\\tools\\foo"


def test_download_output():
    """ Test the download output method of Client. """
    client = TestClient()
    temp_file = tempfile.NamedTemporaryFile()
    temp_file.close()
    request_checker = RequestChecker("jobs/543/files", {"name": os.path.basename(temp_file.name), "type": "output"})
    client.expect_open(request_checker, b"test output contents")
    client._fetch_output(temp_file.name)

    with open(temp_file.name) as f:
        contents = f.read(1024)
        assert contents == "test output contents", "Unexpected contents %s" % contents


def test_get_status_queued():
    client = TestClient()
    request_checker = RequestChecker("jobs/543/status")
    client.expect_open(request_checker, b'{"complete": "false", "status" : "queued"}')
    assert client.get_status() == "queued"
    request_checker.assert_called()


def test_kill():
    client = TestClient()
    request_checker = RequestChecker("jobs/543/cancel")
    client.expect_open(request_checker, 'OK')
    client.kill()
    request_checker.assert_called()


def test_clean():
    client = TestClient()
    request_checker = RequestChecker("jobs/543")
    client.expect_open(request_checker, 'OK')
    client.clean()
    request_checker.assert_called()


def _tes_client_stub(job_id="543", external_id=None):
    client = object.__new__(TesPollingCoexecutionJobClient)
    client.job_id = job_id
    client.external_id = external_id
    return client


class RecordingTesClient:
    def __init__(self):
        self.cancelled = []
        self.polled = []

    def cancel_task(self, task_id):
        self.cancelled.append(task_id)

    def get_task(self, task_id, view):
        self.polled.append((task_id, view))
        return SimpleNamespace(state=None)


def test_client_reads_external_id():
    interface = HttpPulsarInterface({"url": "http://test:803/"}, TestTransport(None))
    client = JobClient({"external_id": "tes-task-abc"}, "543", interface)
    assert client.external_id == "tes-task-abc"
    assert JobClient({}, "543", interface).external_id is None


def test_tes_task_id_falls_back_to_galaxy_job_id():
    client = _tes_client_stub()
    assert client._tes_task_id == "543"


def test_tes_poll_and_cancel_use_recorded_external_id():
    client = _tes_client_stub(external_id="tes-task-abc")
    tes_client = RecordingTesClient()
    with patch.object(
        TesPollingCoexecutionJobClient,
        "_tes_client",
        new_callable=PropertyMock,
        return_value=tes_client,
    ), patch("pulsar.client.tes.tes_state_to_pulsar_status", return_value="running"), patch(
        "pulsar.client.tes.tes_state_is_complete", return_value=False
    ):
        client.kill()
        client.raw_check_complete()

    assert tes_client.cancelled == ["tes-task-abc"]
    assert tes_client.polled == [("tes-task-abc", "FULL")]


def _gcp_client(job_id="543", **destination_params):
    """Build a GCP client the way Galaxy does for every submit, poll and stop."""
    destination_params.setdefault("project_id", "moo")
    return CoexecutionPollingJobClientManager().get_client(destination_params, job_id)


class RecordingBatchClient:
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.created = []

    def create_job(self, request):
        if request.job_id in self.existing:
            raise GcpAlreadyExists(f"job {request.job_id} already exists")
        self.created.append(request.job_id)
        return request.job


def _launch_gcp_containers(client, batch_client):
    pulsar_container = CoexecutionContainerCommand("galaxy/pulsar-pod-staging:0.15.0.0", "pulsar-submit", ["--base64", "e30="], "/")
    with patch("pulsar.client.gcp.gcp_client", return_value=batch_client):
        return client._launch_containers(pulsar_container, None, None)


def test_gcp_job_name_is_the_same_for_every_client():
    first = _gcp_client()
    second = _gcp_client()
    assert isinstance(first, GcpPollingCoexecutionJobClient)
    assert first._job_name == second._job_name == "pulsar-543"


@pytest.mark.parametrize(("destination_params", "expected"), [
    ({"galaxy_instance_id": "main"}, "pulsar-main-543"),
    ({"job_id_prefix": "My_Galaxy"}, "my-galaxy-543"),
    ({"job_id_prefix": "jhu", "galaxy_instance_id": "main"}, "jhu-543"),
])
def test_gcp_job_name_prefix(destination_params, expected):
    assert _gcp_client(**destination_params)._job_name == expected


def test_gcp_job_name_prefers_recorded_external_id():
    client = _gcp_client(external_id="pulsar-543-0badf00d")
    assert client._job_name == "pulsar-543-0badf00d"


def test_gcp_launch_records_job_name_as_external_id():
    batch_client = RecordingBatchClient()
    external_id = _launch_gcp_containers(_gcp_client(), batch_client)
    assert external_id.external_id == "pulsar-543"
    assert batch_client.created == ["pulsar-543"]


def test_gcp_launch_uses_unique_name_when_job_exists():
    batch_client = RecordingBatchClient(existing=["pulsar-543"])
    external_id = _launch_gcp_containers(_gcp_client(), batch_client)
    assert re.fullmatch(r"pulsar-543-[0-9a-f]{8}", external_id.external_id)
    assert batch_client.created == [external_id.external_id]
    assert _gcp_client(external_id=external_id.external_id)._job_name == external_id.external_id


def test_gcp_kill_deletes_job_by_default():
    with patch("pulsar.client.gcp.delete_gcp_job") as delete_gcp_job, patch("pulsar.client.gcp.cancel_gcp_job") as cancel_gcp_job:
        _gcp_client(external_id="pulsar-543-0badf00d").kill()
    delete_gcp_job.assert_called_once_with("moo", "us-central1", "pulsar-543-0badf00d", None)
    cancel_gcp_job.assert_not_called()


def test_gcp_kill_cancels_job_when_configured():
    with patch("pulsar.client.gcp.delete_gcp_job") as delete_gcp_job, patch("pulsar.client.gcp.cancel_gcp_job") as cancel_gcp_job:
        _gcp_client(gcp_kill_action="cancel", credentials_file="creds.json").kill()
    cancel_gcp_job.assert_called_once_with("moo", "us-central1", "pulsar-543", "creds.json")
    delete_gcp_job.assert_not_called()


def test_gcp_kill_logs_failures_with_the_exception(caplog):
    with patch("pulsar.client.gcp.delete_gcp_job", side_effect=RuntimeError("boom")):
        _gcp_client().kill()
    (record,) = [r for r in caplog.records if r.levelname == "WARNING"]
    assert "pulsar-543" in record.getMessage()
    assert record.exc_info[0] is RuntimeError


def test_gcp_clients_share_kill():
    assert GcpMessageCoexecutionJobClient.kill is LaunchesGcpContainersMixin.kill
    assert GcpPollingCoexecutionJobClient.kill is LaunchesGcpContainersMixin.kill


def test_gcp_message_client_kill_deletes_batch_job():
    client_manager = SimpleNamespace(manager_name="_default_")
    client = GcpMessageCoexecutionJobClient({"project_id": "moo"}, "543", client_manager)
    with patch("pulsar.client.gcp.delete_gcp_job") as delete_gcp_job:
        client.kill()
    delete_gcp_job.assert_called_once_with("moo", "us-central1", "pulsar-543", None)
