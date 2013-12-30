# -*- coding: utf-8 -*-
import shutil
import tempfile
import os
import optparse
import traceback
from io import open

from lwr.lwr_client import submit_job
from lwr.lwr_client import finish_job
from lwr.lwr_client import LwrOutputs
from lwr.lwr_client import GalaxyOutputs
from lwr.lwr_client import ClientManager
from lwr.lwr_client import ClientJobDescription
from galaxy.tools.deps.requirements import ToolRequirement

TEST_SCRIPT = b"""
import sys
from os import getenv
from os import makedirs
from os.path import join
from os.path import basename

config_input = open(sys.argv[1], 'r')
input_input = open(sys.argv[2], 'r')
input_extra = open(sys.argv[8], 'r')
output = open(sys.argv[3], 'w')
output2 = open(sys.argv[5], 'w')
output2_contents = sys.argv[6]
output3 = open(sys.argv[7], 'w')
version_output = open(sys.argv[9], 'w')
try:
    assert input_input.read() == "Hello world input!!@!"
    assert input_extra.read() == "INPUT_EXTRA_CONTENTS"
    contents = config_input.read(1024)
    output.write(contents)
    open("workdir_output", "w").write("WORK DIR OUTPUT")
    output2.write(output2_contents)
    with open("galaxy.json", "w") as f: f.write("GALAXY_JSON")
    output3.write(getenv("MOO", "moo_default"))
    output1_extras_path = "%s_files" % sys.argv[3][0:-len(".dat")]
    makedirs(output1_extras_path)
    open(join(output1_extras_path, "extra"), "w").write("EXTRA_OUTPUT_CONTENTS")
    version_output.write("1.0.1")
finally:
    output.close()
    config_input.close()
    output2.close()
    output3.close()
    version_output.close()
"""

EXPECTED_OUTPUT = b"hello world output"
EXAMPLE_UNICODE_TEXT = u'єχαмρℓє συтρυт'
TEST_REQUIREMENT = ToolRequirement(name="dep1", version="1.1", type="package")


class MockTool(object):

    def __init__(self, tool_dir):
        self.id = "client_test"
        self.version = "1.0"
        self.tool_dir = tool_dir


def run(options):
    try:
        temp_directory = tempfile.mkdtemp()
        temp_work_dir = os.path.join(temp_directory, "w")
        temp_tool_dir = os.path.join(temp_directory, "t")

        __makedirs([temp_tool_dir, temp_work_dir])

        temp_input_path = os.path.join(temp_directory, "dataset_0.dat")
        temp_input_extra_path = os.path.join(temp_directory, "dataset_0_files", "input_subdir", "extra")
        temp_config_path = os.path.join(temp_work_dir, "config.txt")
        temp_tool_path = os.path.join(temp_directory, "t", "script.py")
        temp_output_path = os.path.join(temp_directory, "dataset_1.dat")
        temp_output2_path = os.path.join(temp_directory, "dataset_2.dat")
        temp_output3_path = os.path.join(temp_directory, "dataset_3.dat")
        temp_version_output_path = os.path.join(temp_directory, "GALAXY_VERSION_1234")

        __write_to_file(temp_input_path, b"Hello world input!!@!")
        __write_to_file(temp_input_extra_path, b"INPUT_EXTRA_CONTENTS")
        __write_to_file(temp_config_path, EXPECTED_OUTPUT)
        __write_to_file(temp_tool_path, TEST_SCRIPT)

        empty_input = u"/foo/bar/x"
        command_line_params = (
            temp_tool_path,
            temp_config_path,
            temp_input_path,
            temp_output_path,
            empty_input,
            temp_output2_path,
            EXAMPLE_UNICODE_TEXT,
            temp_output3_path,
            temp_input_extra_path,
            temp_version_output_path,
        )
        command_line = u'python %s "%s" "%s" "%s" "%s" "%s" "%s" "%s" "%s" "%s"' % command_line_params
        config_files = [temp_config_path]
        input_files = [temp_input_path, empty_input]
        output_files = [temp_output_path, temp_output2_path, temp_output3_path]
        client = __client(options)
        requirements = []
        test_requirement = options.get("test_requirement", False)
        if test_requirement:
            requirements.append(TEST_REQUIREMENT)

        job_description = ClientJobDescription(
            command_line=command_line,
            tool=MockTool(temp_tool_dir),
            config_files=config_files,
            input_files=input_files,
            output_files=output_files,
            working_directory=temp_work_dir,
            requirements=requirements,
            version_file=None,
        )
        submit_job(client, job_description)
        result_status = client.wait()
        lwr_outputs = LwrOutputs(result_status)
        galaxy_outputs = GalaxyOutputs(
            working_directory=temp_work_dir,
            work_dir_outputs=[],
            output_files=output_files,
            version_file=None,
        )
        finish_args = dict(
            client=client,
            job_completed_normally=True,
            cleanup_job='never',
            galaxy_outputs=galaxy_outputs,
            lwr_outputs=lwr_outputs,
        )
        failed = finish_job(**finish_args)
        if failed:
            raise Exception("Failed to finish job correctly - %s" % result_status)
        __check_outputs(temp_output_path, temp_output2_path)
        __assert_contents(os.path.join(temp_work_dir, "galaxy.json"), b"GALAXY_JSON")
        __assert_contents(os.path.join(temp_directory, "dataset_1_files", "extra"), b"EXTRA_OUTPUT_CONTENTS")
        __assert_contents(temp_version_output_path, b"1.0.1")
        if test_requirement:
            __assert_contents(temp_output3_path, "moo_override")
        else:
            __assert_contents(temp_output3_path, "moo_default")
        __exercise_errors(options, client, temp_output_path, temp_directory)
    except BaseException:
        if not options.suppress_output:
            traceback.print_exc()
        raise
    finally:
        shutil.rmtree(temp_directory)


def __check_outputs(temp_output_path, temp_output2_path):
    """
    Verified the correct outputs were written (i.e. job ran properly).
    """
    __assert_contents(temp_output_path, EXPECTED_OUTPUT)
    __assert_contents(temp_output2_path, EXAMPLE_UNICODE_TEXT)


def __assert_contents(path, expected_contents):
    file = open(path, 'r', encoding="utf-8")
    try:
        contents = file.read()
        assert contents == expected_contents, "Invalid contents: %s" % contents
    finally:
        file.close()


def __exercise_errors(options, client, temp_output_path, temp_directory):
    """
    Exercise error conditions.

    TODO: Improve. Something should be checked here.
    """
    if getattr(options, 'test_errors', False):
        try:
            client.fetch_output(temp_output_path + "x")
        except BaseException:
            if not options.suppress_output:
                traceback.print_exc()


def __client(options):
    client_options = {"url": getattr(options, "url", None), "private_token": getattr(options, "private_token", None)}
    if hasattr(options, "default_file_action"):
        client_options["default_file_action"] = getattr(options, "default_file_action")
    user = getattr(options, 'user', None)
    if user:
        client_options["submit_user"] = user
    client = __client_manager(options).get_client(client_options, "123456")
    return client


def __client_manager(options):
    manager_args = {}
    simple_client_manager_options = ['cache', 'job_manager', 'file_cache']
    for client_manager_option in simple_client_manager_options:
        if getattr(options, client_manager_option, None):
            manager_args[client_manager_option] = getattr(options, client_manager_option)
    if getattr(options, 'transport', None):
        manager_args['transport_type'] = options.transport
    return ClientManager(**manager_args)


def __write_to_file(path, contents):
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(path, "wb") as file:
        file.write(contents)


def __makedirs(directories):
    for directory in directories:
        os.makedirs(directory)


def main():
    """ Exercises a running lwr server application with the lwr client. """
    parser = optparse.OptionParser()
    parser.add_option('--url', dest='url', default='http://localhost:8913/')
    parser.add_option('--private_token', default=None)
    parser.add_option('--transport', default=None)  # set to curl to use pycurl
    parser.add_option('--cache', default=False, action="store_true")
    parser.add_option('--test_errors', default=False, action="store_true")
    parser.add_option('--suppress_output', default=False, action="store_true")
    (options, args) = parser.parse_args()
    run(options)

if __name__ == "__main__":
    main()
