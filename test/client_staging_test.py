import os
import stat
import time
from collections import deque
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import pytest
import requests
from galaxy.tool_util.deps.dependencies import DependenciesDescription
from galaxy.tool_util.deps.requirements import ToolRequirement

from pulsar.client import client as client_module
from pulsar.client.client import JobClient
from pulsar.client.exceptions import PulsarClientTransportError
from pulsar.client.manager import build_client_manager
from pulsar.client.staging.down import (
    finish_job,
    ResultsCollector,
)
from pulsar.client.staging.models import (
    ClientJobDescription,
    ClientOutputs,
    PulsarOutputs,
)
from pulsar.client.staging.up import submit_job
from pulsar.client.test.test_common import write_config
from .test_utils import (
    server_for_test_app,
    TempDirectoryTestCase,
    test_pulsar_app,
    wait_for,
)

TEST_REQUIREMENT_1 = ToolRequirement("test1", "1.0")
TEST_REQUIREMENT_2 = ToolRequirement("test2", "1.0")
TEST_ENV_1 = {"name": "x", "value": "y"}
TEST_TOKEN_ENDPOINT = "endpoint"


class TestStager(TempDirectoryTestCase):

    def setUp(self):
        super().setUp()
        from .test_utils import get_test_tool
        self.tool = get_test_tool()
        self.client = MockClient(self.temp_directory, self.tool)
        inputs = self.__setup_inputs()
        self.client_job_description = ClientJobDescription(
            tool=self.tool,
            command_line="run_test.exe",
            config_files=[],
            input_files=inputs,
            client_outputs=ClientOutputs("/galaxy/database/working_directory/1", []),
            working_directory="/galaxy/database/working_directory/1",
            dependencies_description=DependenciesDescription(requirements=[TEST_REQUIREMENT_1, TEST_REQUIREMENT_2]),
            env=[TEST_ENV_1],
            rewrite_paths=False,
        )
        self.job_config = {
            "configs_directory": "/pulsar/staging/1/configs",
            "working_directory": "/pulsar/staging/1/working",
            "outputs_directory": "/pulsar/staging/1/outputs",
            "system_properties": {
                "separator": "\\",
            },
        }

    def __setup_inputs(self):
        files_directory = os.path.join(self.temp_directory, "files")
        os.makedirs(files_directory)
        self.input1 = os.path.join(files_directory, "dataset_1.dat")
        self.input1_files_path = os.path.join(files_directory, "dataset_1_files")
        os.makedirs(self.input1_files_path)
        open(self.input1, "wb").write(b"012345")
        self.input2 = os.path.join(files_directory, "dataset_2.dat")
        open(self.input2, "wb").write(b"6789")
        return [self.input1, self.input2]

    def test_tool_file_rewrite(self):
        self.client_job_description.rewrite_paths = True
        tool_dir = os.path.abspath(self.tool.tool_dir)
        command_line = "python %s/tool1_wrapper.py" % tool_dir
        self.client_job_description.command_line = command_line
        rewritten_command_line = "python /pulsar/staging/1/tools/tool1_wrapper.py"
        self.client.expect_put_paths(["/pulsar/staging/1/tools/tool1_wrapper.py"])
        self.client.expect_command_line(rewritten_command_line)
        self._submit()
        uploaded_file1 = self.client.put_files[0]
        assert uploaded_file1[1] == "tool"
        self.assertEqual(uploaded_file1[0], "%s/tool1_wrapper.py" % tool_dir)

    def test_input_extra_rewrite(self):
        self.client_job_description.rewrite_paths = True
        extra_file = os.path.join(self.input1_files_path, "moo", "cow.txt")
        os.makedirs(os.path.dirname(extra_file))
        open(extra_file, "w").write("Hello World!")
        command_line = "test.exe %s" % extra_file
        self.client_job_description.command_line = command_line
        self.client.expect_command_line("test.exe /pulsar/staging/1/inputs/dataset_1_files/moo/cow.txt")
        self.client.expect_put_paths(["/pulsar/staging/1/inputs/dataset_1_files/moo/cow.txt"])
        self._submit()
        uploaded_file1 = self.client.put_files[0]
        assert uploaded_file1[1] == "input"
        assert uploaded_file1[0] == extra_file

    def test_unstructured_rewrite(self):
        self.client_job_description.rewrite_paths = True
        self.client.set_action_map_config({"paths": [
            {"path": self.temp_directory, "path_types": "*any*"}
        ]})
        local_unstructured_file = os.path.join(self.temp_directory, "A_RANDOM_FILE")
        open(local_unstructured_file, "wb").write(b"Hello World!")
        command_line = "foo.exe %s" % local_unstructured_file
        self.client_job_description.command_line = command_line
        self.client.expect_put_paths(["/pulsar/staging/1/other/A_RANDOM_FILE"])
        self.client.expect_command_line("foo.exe /pulsar/staging/1/other/A_RANDOM_FILE")
        self._submit()
        uploaded_file1 = self.client.put_files[0]
        assert uploaded_file1[1] == "unstructured"
        self.assertEqual(uploaded_file1[0], local_unstructured_file)

    def test_file_actions_by_dict(self):
        self.client_job_description.rewrite_paths = True
        self.client.set_action_map_config({"paths": [
            {"path": self.temp_directory, "path_types": "*any*"},
        ]}, by_path=False)
        local_unstructured_file = os.path.join(self.temp_directory, "A_RANDOM_FILE")
        open(local_unstructured_file, "wb").write(b"Hello World!")
        command_line = "foo.exe %s" % local_unstructured_file
        self.client_job_description.command_line = command_line
        self.client.expect_put_paths(["/pulsar/staging/1/other/A_RANDOM_FILE"])
        self.client.expect_command_line("foo.exe /pulsar/staging/1/other/A_RANDOM_FILE")
        self._submit()
        uploaded_file1 = self.client.put_files[0]
        assert uploaded_file1[1] == "unstructured"
        self.assertEqual(uploaded_file1[0], local_unstructured_file)

    def test_submit_no_rewrite(self):
        # Expect no rewrite of paths
        command_line_template = "run_test.exe --input1=%s --input2=%s"
        command_line = command_line_template % (self.input1, self.input2)
        self.client_job_description.command_line = command_line
        self.client.expect_command_line(command_line)
        self._submit()
        self._assert_inputs_uploaded()

    def test_submit_rewrite(self):
        self.client_job_description.rewrite_paths = True
        command_line_template = "run_test.exe --input1=%s --input2=%s"
        self.client_job_description.command_line = command_line_template % (self.input1, self.input2)
        rewritten_paths = (
            '/pulsar/staging/1/inputs/dataset_1.dat',
            '/pulsar/staging/1/inputs/dataset_2.dat',
        )
        self.client.expect_command_line(command_line_template % rewritten_paths)
        self._submit()
        self._assert_inputs_uploaded()

    def _assert_inputs_uploaded(self):
        # Expect both files staged
        uploaded_file1 = self.client.put_files[0]
        assert uploaded_file1[1] == "input"
        assert uploaded_file1[0] == self.input1
        uploaded_file2 = self.client.put_files[1]
        assert uploaded_file2[1] == "input"
        assert uploaded_file2[0] == self.input2

    def _submit(self):
        return submit_job(self.client, self.client_job_description, self.job_config)


class MockClient:

    def __init__(self, temp_directory, tool):
        self.temp_directory = temp_directory
        self.job_directory = None
        self.default_file_action = "transfer"
        self.action_config_path = None
        self.files_endpoint = None
        self.token_endpoint = TEST_TOKEN_ENDPOINT
        self.expected_tool = tool
        self.job_id = "1234"
        self.expected_command_line = None
        self.expect_put_paths([
            '/pulsar/staging/1/inputs/dataset_1.dat',
            '/pulsar/staging/1/inputs/dataset_2.dat',
        ])
        self.put_files = []

    def set_action_map_config(self, config, by_path=True):
        if by_path:
            self.action_config_path = write_config(self, config, name="actions.yaml")
        else:
            self.file_actions = config

    def expect_put_paths(self, paths):
        self.put_paths = deque(paths)

    def setup(self, tool_id, tool_version, use_metadata=False):
        assert tool_id == self.expected_tool.id
        assert tool_version == self.expected_tool.version
        return {}

    def launch(self, command_line, dependencies_description, job_config={}, remote_staging={}, env=[], dynamic_file_sources=None,
               token_endpoint=None):
        if self.expected_command_line is not None:
            message = f"Excepected command line {self.expected_command_line}, got {command_line}"
            assert self.expected_command_line == command_line, message
        assert dependencies_description.requirements == [TEST_REQUIREMENT_1, TEST_REQUIREMENT_2]
        assert token_endpoint == TEST_TOKEN_ENDPOINT
        assert env == [TEST_ENV_1]

    def expect_command_line(self, expected_command_line):
        self.expected_command_line = expected_command_line

    def put_file(self, path, type, name, contents, action_type='transfer'):
        self.put_files.append((path, type, name, contents))
        return {"path": self.put_paths.popleft()}


@pytest.mark.parametrize("file_action, interface", [
    ("copy", "embedded"),
    ("transfer", "embedded"),
    ("transfer", "http"),
    ("remote_copy", "embedded"),
    ("hardlink", "embedded"),
    ("remote_hardlink", "embedded"),
])
def test_staged_tool_files_keep_executable_bit(tmp_path, file_action, interface):
    # Stage the tool directory the way Galaxy's Pulsar runners do with
    # rewrite_parameters: true.
    tool_dir = tmp_path / "tool"
    tool_dir.mkdir()
    helper = tool_dir / "helper.sh"
    helper.write_text("#!/bin/sh\necho ran > helper_ran\n")
    # Group and others can read but not execute, so widening would show.
    helper.chmod(0o744)
    data = tool_dir / "data.txt"
    data.write_text("data\n")
    data.chmod(0o644)
    tool = SimpleNamespace(id="tool1", version="1.0", tool_dir=str(tool_dir))
    client_job_description = ClientJobDescription(
        tool=tool,
        command_line=f"{helper} < {data}",
        working_directory=str(tmp_path / "working"),
        rewrite_paths=True,
    )
    with _pulsar_client(interface, {"default_file_action": file_action}) as (client, manager):
        submit_job(client, client_job_description)
        job_directory = manager.job_directory("1")

        # remote_copy stages the files in the background, before the command runs.
        wait_for(client.get_status, "the job to complete", until=lambda status: status == "complete", timeout=30)
        staged_helper = job_directory.calculate_path("helper.sh", "tool")
        staged_data = job_directory.calculate_path("data.txt", "tool")
        assert os.stat(staged_helper).st_mode & stat.S_IXUSR
        assert not os.stat(staged_data).st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        assert os.path.exists(os.path.join(job_directory.working_directory(), "helper_ran"))
        # Hardlink actions share the source inode, which must stay untouched.
        assert stat.S_IMODE(helper.stat().st_mode) == 0o744
        client.clean()


@contextmanager
def _pulsar_client(interface, destination_params):
    """Yield a client for job "1" and the Pulsar manager it talks to."""
    if interface == "embedded":
        with test_pulsar_app(web=False) as app:
            client = build_client_manager(pulsar_app=app, cache=False).get_client(destination_params, "1")
            yield client, app.only_manager
    else:
        with test_pulsar_app() as test_app, server_for_test_app(test_app) as server:
            destination_params = dict(destination_params, url=server.application_url)
            client = build_client_manager(cache=False).get_client(destination_params, "1")
            yield client, test_app.app.pulsar_app.only_manager


def _results_collector_with_failing_collect(exc):
    """Build a minimal ResultsCollector whose output collection raises ``exc``."""
    output_collector = SimpleNamespace(collect_output=lambda *a, **k: (_ for _ in ()).throw(exc))
    client_outputs = SimpleNamespace(output_files=[])
    pulsar_outputs = SimpleNamespace(
        working_directory_contents=[], metadata_directory_contents=[], job_directory_contents=[]
    )
    return ResultsCollector(output_collector, action_mapper=None, client_outputs=client_outputs, pulsar_outputs=pulsar_outputs)


def _http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


def test_collect_output_tolerates_403_without_failing_job():
    """A 403 means Galaxy authoritatively refused the upload (e.g. the output
    dataset was purged mid-job). Even for a normally-fatal output type this
    must not fail the job — _collect_output returns without raising, so the
    exception tracker records no failure."""
    rc = _results_collector_with_failing_collect(_http_error(403))
    action = SimpleNamespace(url="http://galaxy.test/api/jobs/1/files?path=/x&file_type=output")
    assert rc._collect_output("output", action, "out1") is False


def test_collect_output_reraises_non_403_for_fatal_output_type():
    rc = _results_collector_with_failing_collect(_http_error(500))
    action = SimpleNamespace(url="http://galaxy.test/api/jobs/1/files?path=/x&file_type=output")
    with pytest.raises(requests.HTTPError):
        rc._collect_output("output", action, "out1")


def test_collect_output_reraises_infra_oserror_for_workdir_output():
    """An infrastructure OSError (e.g. disk full) collecting a working-directory
    output must fail the job rather than be downgraded to an allowed failure."""
    rc = _results_collector_with_failing_collect(OSError("No space left on device"))
    action = SimpleNamespace(path="/pulsar/working/out.dat")
    with pytest.raises(OSError):
        rc._collect_output("output_workdir", action, "out1")


def test_collect_output_tolerates_missing_workdir_output():
    """A missing from_work_dir output (FileNotFoundError) is an expected,
    recoverable condition for a working-directory output, so it is an allowed
    failure and must not raise."""
    rc = _results_collector_with_failing_collect(FileNotFoundError("out.dat"))
    action = SimpleNamespace(path="/pulsar/working/out.dat")
    assert rc._collect_output("output_workdir", action, "out1") is None


def test_collect_output_reraises_transport_error_for_workdir_output():
    """A transport failure staging out a working-directory output must fail the
    job. Downgrading it is how a successful job ends up green in Galaxy with
    zero-length outputs. PulsarClientTransportError is not an OSError, so it has
    to be recognized explicitly."""
    rc = _results_collector_with_failing_collect(
        PulsarClientTransportError(
            code=PulsarClientTransportError.NOT_200, transport_code=500, transport_message="POST failed"
        )
    )
    action = SimpleNamespace(url="http://galaxy.test/api/jobs/1/files?path=/x&file_type=output")
    with pytest.raises(PulsarClientTransportError):
        rc._collect_output("output_workdir", action, "out1")


def test_collect_output_tolerates_403_transport_error_for_workdir_output():
    """The 403 carve-out is keyed on the status code, not the exception class, so
    it applies to a transport error carrying 403 just as it does to a
    requests.HTTPError."""
    rc = _results_collector_with_failing_collect(
        PulsarClientTransportError(code=PulsarClientTransportError.NOT_200, transport_code=403)
    )
    action = SimpleNamespace(url="http://galaxy.test/api/jobs/1/files?path=/x&file_type=output")
    assert rc._collect_output("output_workdir", action, "out1") is False



def _finish_job_with_copied_workdir_output(tmp_path, source_contents, **destination_params):
    """Collect one from_work_dir output with the copy action, as an embedded
    runner does. Returns the collection failures and the Galaxy output path."""
    working_directory = tmp_path / "pulsar" / "working"
    working_directory.mkdir(parents=True)
    if source_contents is not None:
        (working_directory / "out.txt").write_text(source_contents)
    output_file = tmp_path / "galaxy" / "dataset_1.dat"
    galaxy_working_directory = tmp_path / "galaxy" / "working"
    client = JobClient({"default_file_action": "copy", **destination_params}, "1", None)
    client_outputs = ClientOutputs(
        working_directory=str(galaxy_working_directory),
        output_files=[str(output_file)],
        work_dir_outputs=[(str(galaxy_working_directory / "out.txt"), str(output_file))],
    )
    pulsar_outputs = PulsarOutputs(["out.txt"], [], [], [])

    def output_path(name, job_id, path_type):
        return {"path": str(working_directory / name)}

    with mock.patch.object(client, "_output_path", side_effect=output_path):
        failures = finish_job(client, "never", True, client_outputs, pulsar_outputs)
    return failures, output_file


def test_collect_workdir_output_retries_until_source_is_visible(tmp_path):
    """The handler's NFS client may not yet see a file the compute node just
    wrote. A missing source is retried, so the output is collected rather than
    left empty."""
    real_copy = client_module.copy
    attempts = []

    def copy_visible_on_second_attempt(source, destination):
        attempts.append(source)
        if len(attempts) == 1:
            raise FileNotFoundError(2, "No such file or directory", source)
        real_copy(source, destination)

    with mock.patch.object(client_module, "copy", side_effect=copy_visible_on_second_attempt), \
            mock.patch.object(time, "sleep") as sleep:
        failures, output_file = _finish_job_with_copied_workdir_output(tmp_path, "tool output")

    assert failures == []
    assert output_file.read_text() == "tool output"
    assert len(attempts) == 2
    sleep.assert_called_once_with(client_module.OUTPUT_COLLECTION_RETRY_SLEEP)


def test_collect_workdir_output_never_visible_is_allowed_failure(tmp_path, caplog):
    """A from_work_dir output still missing after all retries is a tool failure:
    it is downgraded to a warning naming the source, not a job failure."""
    with mock.patch.object(time, "sleep") as sleep:
        # Galaxy's XML job configuration passes destination params as strings.
        failures, output_file = _finish_job_with_copied_workdir_output(
            tmp_path, None, output_collection_retries="2"
        )

    assert failures == []
    assert not output_file.exists()
    assert sleep.call_count == 2
    warning = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warning) == 1
    assert str(tmp_path / "pulsar" / "working" / "out.txt") in warning[0]
    assert str(output_file) in warning[0]
