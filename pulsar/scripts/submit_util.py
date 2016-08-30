""" CLI related utilities for submitting Pulsar jobs.
"""
import json
import logging
import time

from pulsar.client.util import from_base64_json
from pulsar.main import (
    load_pulsar_app,
    PulsarManagerConfigBuilder
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
    config_builder = PulsarManagerConfigBuilder(args)
    manager, app = manager_from_args(config_builder)
    try:
        job_config = _load_job_config(args)
        submit_job(manager, job_config)
        wait_for_job(manager, job_config)
    except BaseException:
        log.exception("Failure submitting or waiting on job.")
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
        job_config = json.load(open(args.file, "r"))
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
