""" CLI related utilities for submitting Pulsar jobs.
"""
import json
import logging
import time

from pulsar.client import ClientJobDescription, ClientOutputs, ClientInput
from pulsar.client import submit_job as submit_client_job
from pulsar.client.manager import build_client_manager
from pulsar.client.util import from_base64_json
from pulsar.main import (
    load_pulsar_app,
    PulsarManagerConfigBuilder,
)
from pulsar.manager_endpoint_util import submit_job
from pulsar.managers.status import is_job_done

log = logging.getLogger(__name__)

DEFAULT_POLL_TIME = 2


def add_common_submit_args(arg_parser):
    arg_parser.add_argument("--file", default=None)
    arg_parser.add_argument("--base64", default=None)
    PulsarManagerConfigBuilder.populate_options(arg_parser)


def run_server_for_job(args):
    wait = args.wait
    config_builder = PulsarManagerConfigBuilder(args)
    manager, app = manager_from_args(config_builder)
    try:
        job_config = _load_job_config(args)
        submit_job(manager, job_config)
        if wait:
            log.info("Co-execution job setup, now waiting for job completion and postprocessing.")
            if args.build_client_manager:
                client_manager = build_client_manager(arc_enabled=True)
                client = client_manager.get_client({"arc_url": "http://localhost:8082", "jobs_directory": app.staging_directory}, job_id=job_config["job_id"], default_file_action=job_config["remote_staging"]["action_mapper"]["default_action"], files_endpoint=job_config["remote_staging"]["action_mapper"]["files_endpoint"])
                # FIXME: we can probably only test the input staging here, so adjust tests accordingly
                client_inputs = [
                    ClientInput(path=action_source["path"], input_type="input_path")
                    for action_source in job_config["remote_staging"]["client_inputs"]
                ]
                client_outputs = ClientOutputs.from_dict(job_config["remote_staging"]["client_outputs"])
                job_description = ClientJobDescription(
                    command_line=job_config["command_line"],
                    working_directory=client_outputs.working_directory,
                    client_inputs=client_inputs,
                    client_outputs=client_outputs,
                )
                job_config["working_directory"] = client_outputs.working_directory
                submit_client_job(client, job_description)
            wait_for_job(manager, job_config)
            log.info("Leaving finish_execution and shutting down app")
    except BaseException:
        if wait:
            message = "Failure submitting or waiting on job."
        else:
            message = "Failure submitting job."
        log.exception(message)
    finally:
        app.shutdown()


def run_server_for_job_finish(args):
    config_builder = PulsarManagerConfigBuilder(args)
    manager, app = manager_from_args(config_builder)
    try:
        # We only need the job config so there should be an option to just
        # send that I think.
        job_config = _load_job_config(args)
        job_id = job_config.get('job_id')
        log.info("Informing Pulsar app the target job has completed")
        manager._proxied_manager.finish_execution(job_id)
        log.info("Waiting for job to complete")
        wait_for_job(manager, job_config)
        log.info("Leaving finish_execution and shutting down app")
    except BaseException:
        log.exception("Failure finishing job.")
    finally:
        app.shutdown()


def wait_for_job(manager, job_config, poll_time=DEFAULT_POLL_TIME):
    job_id = job_config.get('job_id')
    while True:
        status = manager.get_status(job_id)
        if is_job_done(status):
            break
        time.sleep(poll_time)


def _load_job_config(args):
    if args.base64:
        base64_job_config = args.base64
        job_config = from_base64_json(base64_job_config)
    else:
        job_config = json.load(open(args.file))
    return job_config


def manager_from_args(config_builder):
    manager_name = config_builder.manager

    pulsar_app = load_pulsar_app(
        config_builder,
        # Set message_queue_consume so this Pulsar app doesn't try to consume
        # setup/kill messages and only publishes status updates to configured
        # queue.
        message_queue_consume=False,
    )
    manager = pulsar_app.managers[manager_name]
    return manager, pulsar_app
