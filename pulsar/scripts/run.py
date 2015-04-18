""" CLI related utilities for submitting Pulsar jobs.
"""
import fnmatch
import sys
import uuid

from pulsar.main import ArgumentParser
from pulsar.scripts.submit_util import (
    add_common_submit_args,
    run_server_for_job,
)

from pulsar.client.test.check import (
    HELP_URL,
    HELP_PRIVATE_TOKEN,
    HELP_TRANSPORT,
    HELP_SUPPRESS_OUTPUT,
    HELP_DISABLE_CLEANUP,
    HELP_JOB_ID,
    extract_client_options,
    client_info,
    Waiter,
)
from pulsar.client import ClientJobDescription
from pulsar.client import ClientOutputs
from pulsar.client import PulsarOutputs
from pulsar.client import submit_job
from pulsar.client import finish_job
from pulsar.client.util import json_dumps

HELP_AMQP_URL = "Communicate with Pulsar listining on a message queue at this URL."
HELP_SERVER = "Run a Pulsar server locally instead of contacting a remote one."
HELP_COMMAND = "Shell command to execute on Pulsar server."
HELP_WORKING_DIRECTORY = "Local working directory (will be translated to a new directory)."
HELP_OUTPUT = "Output glob to collect from job (relative to remote working directory)."
HELP_OUTPUT_PATTERN = "Output pattern to collect from job (relative to remote working directory)."

DEFAULT_CLIENT_URL = 'http://localhost:8913/'


def main(argv=None):
    mod_docstring = sys.modules[__name__].__doc__
    arg_parser = ArgumentParser(description=mod_docstring)
    add_common_submit_args(arg_parser)
    arg_parser.add_argument('--url', default=DEFAULT_CLIENT_URL, help=HELP_URL)
    arg_parser.add_argument('--amqp_url', default=DEFAULT_CLIENT_URL, help=HELP_AMQP_URL)
    arg_parser.add_argument('--private_token', default=None, help=HELP_PRIVATE_TOKEN)
    # TODO: choices...
    arg_parser.add_argument('--default_file_action', default="none")
    arg_parser.add_argument('--file_action_config', default=None)
    arg_parser.add_argument('--transport', default=None, choices=["urllib", "curl"], help=HELP_TRANSPORT)  # set to curl to use pycurl
    arg_parser.add_argument('--suppress_output', default=False, action="store_true", help=HELP_SUPPRESS_OUTPUT)
    arg_parser.add_argument('--disable_cleanup', dest="cleanup", default=True, action="store_false", help=HELP_DISABLE_CLEANUP)
    arg_parser.add_argument('--server', default=False, action="store_true", help=HELP_SERVER)
    arg_parser.add_argument('--job_id', default=None, help=HELP_JOB_ID)
    arg_parser.add_argument('--command', help=HELP_COMMAND)
    arg_parser.add_argument('--working_directory', default=".", help=HELP_WORKING_DIRECTORY)
    arg_parser.add_argument('--result_json', default=None)
    arg_parser.add_argument('--output', default=[], action="append", help=HELP_OUTPUT)
    arg_parser.add_argument('--output_pattern', default=[], action="append", help=HELP_OUTPUT_PATTERN)

    args = arg_parser.parse_args(argv)
    if args.server:
        return run_server_for_job(args)
    else:
        failed = _run_client_for_job(args)
        if failed:
            return 1
        else:
            return 0


def _run_client_for_job(args):
    if args.job_id is None:
        args.job_id = str(uuid.uuid4())
    output_patterns = []
    output_patterns.extend(args.output_pattern)
    for output in args.output:
        output_patterns.append(fnmatch.translate(output))

    client_options = extract_client_options(args)
    client, client_manager = client_info(args, client_options)
    try:
        working_directory = args.working_directory
        client_outputs = ClientOutputs(
            working_directory=working_directory,
            dynamic_outputs=output_patterns,
        )
        job_description = ClientJobDescription(
            command_line=args.command,
            working_directory=working_directory,
            client_outputs=client_outputs,
        )
        submit_job(client, job_description)
        waiter = Waiter(client, client_manager)
        result_status = waiter.wait()
        pulsar_outputs = PulsarOutputs.from_status_response(result_status)
        if args.result_json:
            open(args.result_json, "w").write(json_dumps(result_status))
        finish_args = dict(
            client=client,
            job_completed_normally=True,
            cleanup_job=args.cleanup,
            client_outputs=client_outputs,
            pulsar_outputs=pulsar_outputs,
        )
        failed = finish_job(**finish_args)
        return failed
    finally:
        client_manager.shutdown()


if __name__ == "__main__":
    main()
