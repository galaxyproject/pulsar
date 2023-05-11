from collections import deque
import os

from .test_utils import TempDirectoryTestCase
from pulsar.client.test.test_common import write_config
from pulsar.client import submit_job, ClientJobDescription
from pulsar.client import ClientOutputs
from galaxy.tool_util.deps.dependencies import DependenciesDescription
from galaxy.tool_util.deps.requirements import ToolRequirement

TEST_REQUIREMENT_1 = ToolRequirement("test1", "1.0")
TEST_REQUIREMENT_2 = ToolRequirement("test2", "1.0")
TEST_ENV_1 = dict(name="x", value="y")
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
        self.job_config = dict(
            configs_directory="/pulsar/staging/1/configs",
            working_directory="/pulsar/staging/1/working",
            outputs_directory="/pulsar/staging/1/outputs",
            system_properties=dict(
                separator="\\",
            ),
        )

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
        self.client.set_action_map_config(dict(paths=[
            dict(path=self.temp_directory, path_types="*any*")
        ]))
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
        self.client.set_action_map_config(dict(paths=[
            dict(path=self.temp_directory, path_types="*any*"),
        ]), by_path=False)
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
            message = "Excepected command line {}, got {}".format(self.expected_command_line, command_line)
            assert self.expected_command_line == command_line, message
        assert dependencies_description.requirements == [TEST_REQUIREMENT_1, TEST_REQUIREMENT_2]
        assert token_endpoint == TEST_TOKEN_ENDPOINT
        assert env == [TEST_ENV_1]

    def expect_command_line(self, expected_command_line):
        self.expected_command_line = expected_command_line

    def put_file(self, path, type, name, contents, action_type='transfer'):
        self.put_files.append((path, type, name, contents))
        return {"path": self.put_paths.popleft()}
