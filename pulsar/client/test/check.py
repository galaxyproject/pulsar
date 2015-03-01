# -*- coding: utf-8 -*-
import shutil
import tempfile
import os
import optparse
import traceback
import re
import threading
import time
from io import open

from pulsar.client import submit_job
from pulsar.client import finish_job
from pulsar.client import PulsarOutputs
from pulsar.client import ClientOutputs
from pulsar.client import build_client_manager
from pulsar.client import ClientJobDescription
from galaxy.tools.deps.dependencies import DependenciesDescription
from galaxy.tools.deps.requirements import ToolRequirement
from .test_common import write_config

TEST_SCRIPT = b"""
import sys
from os import getenv
from os import makedirs
from os import listdir
from os.path import join
from os.path import basename
from os.path import dirname

config_input = open(sys.argv[1], 'r')
input_input = open(sys.argv[2], 'r')
input_extra = open(sys.argv[8], 'r')
output = open(sys.argv[3], 'w')
output2 = open(sys.argv[5], 'w')
output2_contents = sys.argv[6]
output3 = open(sys.argv[7], 'w')
version_output = open(sys.argv[9], 'w')
index_path = sys.argv[10]
assert len(listdir(dirname(index_path))) == 2
assert len(listdir(join(dirname(dirname(index_path)), "seq"))) == 1
output4_index_path = open(sys.argv[11], 'w')
try:
    assert input_input.read() == "Hello world input!!@!"
    assert input_extra.read() == "INPUT_EXTRA_CONTENTS"
    contents = config_input.read(1024)
    output.write(contents)
    open("workdir_output", "w").write("WORK DIR OUTPUT")
    open("env_test", "w").write(getenv("TEST_ENV", "DEFAULT"))
    open("rewrite_action_test", "w").write(sys.argv[12])
    output2.write(output2_contents)
    with open("galaxy.json", "w") as f: f.write("GALAXY_JSON")
    output3.write(getenv("MOO", "moo_default"))
    output1_extras_path = "%s_files" % sys.argv[3][0:-len(".dat")]
    makedirs(output1_extras_path)
    open(join(output1_extras_path, "extra"), "w").write("EXTRA_OUTPUT_CONTENTS")
    version_output.write("1.0.1")
    output4_index_path.write(index_path)
finally:
    output.close()
    config_input.close()
    output2.close()
    output3.close()
    version_output.close()
    output4_index_path.close()
"""

EXPECTED_OUTPUT = b"hello world output"
EXAMPLE_UNICODE_TEXT = u'єχαмρℓє συтρυт'
TEST_REQUIREMENT = ToolRequirement(name="dep1", version="1.1", type="package")
TEST_DEPENDENCIES = DependenciesDescription(requirements=[TEST_REQUIREMENT])


class MockTool(object):

    def __init__(self, tool_dir):
        self.id = "client_test"
        self.version = "1.0"
        self.tool_dir = tool_dir


def run(options):
    try:
        temp_directory = tempfile.mkdtemp()
        temp_index_dir = os.path.join(temp_directory, "idx", "bwa")
        temp_index_dir_sibbling = os.path.join(temp_directory, "idx", "seq")
        temp_shared_dir = os.path.join(temp_directory, "shared", "test1")
        temp_work_dir = os.path.join(temp_directory, "w")
        temp_tool_dir = os.path.join(temp_directory, "t")

        __makedirs([temp_tool_dir, temp_work_dir, temp_index_dir, temp_index_dir_sibbling, temp_shared_dir])

        temp_input_path = os.path.join(temp_directory, "dataset_0.dat")
        temp_input_extra_path = os.path.join(temp_directory, "dataset_0_files", "input_subdir", "extra")
        temp_index_path = os.path.join(temp_index_dir, "human.fa")

        temp_config_path = os.path.join(temp_work_dir, "config.txt")
        temp_tool_path = os.path.join(temp_directory, "t", "script.py")
        temp_output_path = os.path.join(temp_directory, "dataset_1.dat")
        temp_output2_path = os.path.join(temp_directory, "dataset_2.dat")
        temp_output3_path = os.path.join(temp_directory, "dataset_3.dat")
        temp_output4_path = os.path.join(temp_directory, "dataset_4.dat")
        temp_version_output_path = os.path.join(temp_directory, "GALAXY_VERSION_1234")
        temp_output_workdir_destination = os.path.join(temp_directory, "dataset_77.dat")
        temp_output_workdir = os.path.join(temp_work_dir, "env_test")

        temp_output_workdir_destination2 = os.path.join(temp_directory, "dataset_78.dat")
        temp_output_workdir2 = os.path.join(temp_work_dir, "rewrite_action_test")

        __write_to_file(temp_input_path, b"Hello world input!!@!")
        __write_to_file(temp_input_extra_path, b"INPUT_EXTRA_CONTENTS")
        __write_to_file(temp_config_path, EXPECTED_OUTPUT)
        __write_to_file(temp_tool_path, TEST_SCRIPT)
        __write_to_file(temp_index_path, b"AGTC")
        # Implicit files that should also get transferred since depth > 0
        __write_to_file("%s.fai" % temp_index_path, b"AGTC")
        __write_to_file(os.path.join(temp_index_dir_sibbling, "human_full_seqs"), b"AGTC")

        empty_input = u"/foo/bar/x"

        test_unicode = getattr(options, "test_unicode", False)  # TODO Switch this in integration tests
        cmd_text = EXAMPLE_UNICODE_TEXT if test_unicode else "Hello World"
        command_line_params = (
            temp_tool_path,
            temp_config_path,
            temp_input_path,
            temp_output_path,
            empty_input,
            temp_output2_path,
            cmd_text,
            temp_output3_path,
            temp_input_extra_path,
            temp_version_output_path,
            temp_index_path,
            temp_output4_path,
            temp_shared_dir,
        )
        assert os.path.exists(temp_index_path)
        command_line = u'python %s "%s" "%s" "%s" "%s" "%s" "%s" "%s" "%s" "%s" "%s" "%s" "%s"' % command_line_params
        config_files = [temp_config_path]
        input_files = [temp_input_path, empty_input]
        output_files = [
            temp_output_path,
            temp_output2_path,
            temp_output3_path,
            temp_output4_path,
            temp_output_workdir_destination,
            temp_output_workdir_destination2
        ]
        client, client_manager = __client(temp_directory, options)
        waiter = Waiter(client, client_manager)
        client_outputs = ClientOutputs(
            working_directory=temp_work_dir,
            work_dir_outputs=[
                (temp_output_workdir, temp_output_workdir_destination),
                (temp_output_workdir2, temp_output_workdir_destination2),
            ],
            output_files=output_files,
            version_file=temp_version_output_path,
        )

        job_description = ClientJobDescription(
            command_line=command_line,
            tool=MockTool(temp_tool_dir),
            config_files=config_files,
            input_files=input_files,
            client_outputs=client_outputs,
            working_directory=temp_work_dir,
            **__extra_job_description_kwargs(options)
        )
        submit_job(client, job_description)
        result_status = waiter.wait()

        __finish(options, client, client_outputs, result_status)
        __assert_contents(temp_output_path, EXPECTED_OUTPUT, result_status)
        __assert_contents(temp_output2_path, cmd_text, result_status)
        __assert_contents(os.path.join(temp_work_dir, "galaxy.json"), b"GALAXY_JSON", result_status)
        __assert_contents(os.path.join(temp_directory, "dataset_1_files", "extra"), b"EXTRA_OUTPUT_CONTENTS", result_status)
        if getattr(options, "test_rewrite_action", False):
            __assert_contents(temp_output_workdir_destination2, os.path.join(temp_directory, "shared2", "test1"), result_status)
        if job_description.env:
            __assert_contents(temp_output_workdir_destination, b"TEST_ENV_VALUE", result_status)
        __assert_contents(temp_version_output_path, b"1.0.1", result_status)
        if job_description.dependencies_description:
            __assert_contents(temp_output3_path, "moo_override", result_status)
        else:
            __assert_contents(temp_output3_path, "moo_default", result_status)
        if client.default_file_action != "none":
            rewritten_index_path = open(temp_output4_path, 'r', encoding='utf-8').read()
            # Path written to this file will differ between Windows and Linux.
            assert re.search(r"123456[/\\]unstructured[/\\]\w+[/\\]bwa[/\\]human.fa", rewritten_index_path) is not None
        __exercise_errors(options, client, temp_output_path, temp_directory)
        client_manager.shutdown()
    except BaseException:
        if not options.suppress_output:
            traceback.print_exc()
        raise
    finally:
        shutil.rmtree(temp_directory)


class Waiter(object):

    def __init__(self, client, client_manager):
        self.client = client
        self.client_manager = client_manager
        self.async = hasattr(client_manager, 'ensure_has_status_update_callback')
        self.__setup_callback()

    def __setup_callback(self):
        if self.async:
            self.event = threading.Event()

            def on_update(message):
                if message["status"] in ["complete", "cancelled"]:
                    self.final_status = message
                    self.event.set()

            self.client_manager.ensure_has_status_update_callback(on_update)

    def wait(self, seconds=5):
        final_status = None
        if not self.async:
            i = 0
            # Wait for seconds * 2 half second intervals
            while i < (seconds * 2):
                complete_response = self.client.raw_check_complete()
                if complete_response["status"] in ["complete", "cancelled"]:
                    final_status = complete_response
                    break
                time.sleep(.5)
                i = i + 1
        else:
            self.event.wait(seconds)
            if self.event.is_set():
                final_status = self.final_status
        if not final_status:
            raise Exception("Job not completed properly")

        return final_status


def __assert_contents(path, expected_contents, pulsar_state):
    if not os.path.exists(path):
        raise AssertionError("File %s not created. Final Pulsar response state [%s]" % (path, pulsar_state))
    file = open(path, 'r', encoding="utf-8")
    try:
        contents = file.read()
        if contents != expected_contents:
            message = "File (%s) contained invalid contents [%s]." % (path, contents)
            message = "%s Expected contents [%s]. Final Pulsar response state [%s]" % (message, expected_contents, pulsar_state)
            raise AssertionError(message)
    finally:
        file.close()


def __exercise_errors(options, client, temp_output_path, temp_directory):
    """
    Exercise error conditions.

    TODO: Improve. Something should be checked here.
    """
    if getattr(options, 'test_errors', False):
        try:
            client._fetch_output(temp_output_path + "x")
        except BaseException:
            if not options.suppress_output:
                traceback.print_exc()


def __client(temp_directory, options):
    default_file_action = getattr(options, "default_file_action", None)
    unstructured_action = default_file_action or "transfer"
    path_defs = [
        dict(path=os.path.join(temp_directory, "idx"), path_types="unstructured", depth=2, action=unstructured_action),
    ]
    if getattr(options, "test_rewrite_action", False):
        rewrite_def = dict(
            path=os.path.join(temp_directory, "shared"),
            path_types="unstructured",
            action="rewrite",
            source_directory=os.path.join(temp_directory, "shared"),
            destination_directory=os.path.join(temp_directory, "shared2")
        )
        path_defs.append(rewrite_def)
    client_options = {
        "url": getattr(options, "url", None),
        "private_token": getattr(options, "private_token", None),
        "file_action_config": write_config(temp_directory, dict(paths=path_defs)),
    }
    if default_file_action:
        client_options["default_file_action"] = default_file_action
    if hasattr(options, "jobs_directory"):
        client_options["jobs_directory"] = getattr(options, "jobs_directory")
    if hasattr(options, "files_endpoint"):
        client_options["files_endpoint"] = getattr(options, "files_endpoint")
    user = getattr(options, 'user', None)
    if user:
        client_options["submit_user"] = user
    client_manager = __client_manager(options)
    client = client_manager.get_client(client_options, "123456")
    return client, client_manager


def __client_manager(options):
    manager_args = {}
    simple_client_manager_options = ['cache', 'job_manager', 'file_cache']
    for client_manager_option in simple_client_manager_options:
        if getattr(options, client_manager_option, None):
            manager_args[client_manager_option] = getattr(options, client_manager_option)
    if getattr(options, 'transport', None):
        manager_args['transport'] = options.transport
    if getattr(options, 'manager_url', None):
        manager_args['amqp_url'] = options.manager_url
    return build_client_manager(**manager_args)


def __write_to_file(path, contents):
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(path, "wb") as file:
        file.write(contents)


def __makedirs(directories):
    for directory in directories:
        os.makedirs(directory)


def __extra_job_description_kwargs(options):
    dependencies_description = None
    test_requirement = getattr(options, "test_requirement", False)
    if test_requirement:
        requirements = [TEST_REQUIREMENT]
        dependencies_description = DependenciesDescription(requirements=requirements)
    test_env = getattr(options, "test_env", False)
    env = []
    if test_env:
        env.append(dict(name="TEST_ENV", value="TEST_ENV_VALUE"))
    return dict(dependencies_description=dependencies_description, env=env)


def __finish(options, client, client_outputs, result_status):
    pulsar_outputs = PulsarOutputs.from_status_response(result_status)
    cleanup_job = 'always'
    if not getattr(options, 'cleanup', True):
        cleanup_job = 'never'
    finish_args = dict(
        client=client,
        job_completed_normally=True,
        cleanup_job=cleanup_job,  # Default should 'always' if overridden via options.
        client_outputs=client_outputs,
        pulsar_outputs=pulsar_outputs,
    )
    failed = finish_job(**finish_args)
    if failed:
        failed_message_template = "Failed to complete job correctly, final status %s, finish exceptions %s."
        failed_message = failed_message_template % (result_status, failed)
        assert False, failed_message


def main():
    """ Exercises a running Pulsar with the Pulsar client. """
    parser = optparse.OptionParser()
    parser.add_option('--url', dest='url', default='http://localhost:8913/')
    parser.add_option('--private_token', default=None)
    parser.add_option('--transport', default=None)  # set to curl to use pycurl
    parser.add_option('--cache', default=False, action="store_true")
    parser.add_option('--test_errors', default=False, action="store_true")
    parser.add_option('--suppress_output', default=False, action="store_true")
    parser.add_option('--disable_cleanup', dest="cleanup", default=True, action="store_false")
    (options, args) = parser.parse_args()
    run(options)

if __name__ == "__main__":
    main()
