from collections import deque
import os
from .test_utils import TempDirectoryTestCase
from lwr.lwr_client import submit_job, ClientJobDescription
from galaxy.tools.deps.requirements import ToolRequirement

TEST_REQUIREMENT_1 = ToolRequirement("test1", "1.0")
TEST_REQUIREMENT_2 = ToolRequirement("test2", "1.0")


class TestStager(TempDirectoryTestCase):

    def setUp(self):
        super(TestStager, self).setUp()
        from .test_utils import get_test_tool
        tool = get_test_tool()
        self.client = MockClient(tool)
        inputs = self.__setup_inputs()
        self.client_job_description = ClientJobDescription(
            tool=tool,
            command_line="run_test.exe",
            config_files=[],
            input_files=inputs,
            output_files=[],
            working_directory="/galaxy/database/working_directory/1",
            requirements=[TEST_REQUIREMENT_1, TEST_REQUIREMENT_2],
            rewrite_paths=False,
        )
        self.job_config = dict(
            working_directory="/lwr/staging/1/working",
            outputs_directory="/lwr/staging/1/outputs",
            system_properties=dict(
                separator="\\",
            ),
        )

    def __setup_inputs(self):
        files_directory = os.path.join(self.temp_directory, "files")
        os.makedirs(files_directory)
        self.input1 = os.path.join(files_directory, "dataset_1.dat")
        open(self.input1, "wb").write(u"012345")
        self.input2 = os.path.join(files_directory, "dataset_2.dat")
        open(self.input2, "wb").write(u"6789")
        return [self.input1, self.input2]

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
            '/lwr/staging/1/inputs/dataset_1.dat',
            '/lwr/staging/1/inputs/dataset_2.dat',
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


class MockClient(object):

    def __init__(self, tool):
        self.default_file_action = "transfer"
        self.action_config_path = None
        self.expected_tool = tool
        self.job_id = "1234"
        self.expected_command_line = None
        self.put_paths = deque([
            '/lwr/staging/1/inputs/dataset_1.dat',
            '/lwr/staging/1/inputs/dataset_2.dat',
        ])
        self.put_files = []

    def setup(self, tool_id, tool_version):
        assert tool_id == self.expected_tool.id
        assert tool_version == self.expected_tool.version
        return {}

    def launch(self, command_line, requirements):
        if self.expected_command_line is not None:
            message = "Excepected command line %s, got %s" % (self.expected_command_line, command_line)
            assert self.expected_command_line == command_line, message
        assert requirements == [TEST_REQUIREMENT_1, TEST_REQUIREMENT_2]

    def expect_command_line(self, expected_command_line):
        self.expected_command_line = expected_command_line

    def put_file(self, path, type, name, contents):
        self.put_files.append((path, type, name, contents))
        return {"path": self.put_paths.popleft()}
