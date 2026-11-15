""" CLI related utilities for submitting Pulsar jobs.
"""
import json
import logging
import time
from typing import Callable

from pulsar.client.util import from_base64_json
from pulsar.main import (
    load_pulsar_app,
    PulsarManagerConfigBuilder,
)
from pulsar.manager_endpoint_util import submit_job
from pulsar.managers.status import (
    FAILED,
    is_job_done,
    LOST,
    PREPROCESSING,
    StateLiteral,
)

log = logging.getLogger(__name__)

DEFAULT_POLL_TIME = 2
DEFAULT_LAUNCH_POLL_TIME = 0.5

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
FAILED_STATUSES = (FAILED, LOST)


def add_common_submit_args(arg_parser):
    arg_parser.add_argument("--file", default=None)
    arg_parser.add_argument("--base64", default=None)
    PulsarManagerConfigBuilder.populate_options(arg_parser)


def run_server_for_job(args):
    """Submit a job and return the process exit code.

    Without ``--wait`` the exit code is non-zero when the job could not be
    submitted or its inputs staged. The failure has been published as a
    ``failed`` status by then, unless the job config could not be read. The
    non-zero exit lets a sequential coexecution environment such as TES stop
    the task, instead of leaving the tool container waiting for a command line
    that is never written.

    With ``--wait`` it is always zero, as before. Kubernetes runs this in a
    Job, which replaces a failed pod (``backoffLimit`` defaults to 6) and so
    would run the job again after its final status was published.
    """
    wait = args.wait
    config_builder = PulsarManagerConfigBuilder(args)
    manager, app = manager_from_args(config_builder)
    try:
        job_config = _load_job_config(args)
        submit_job(manager, job_config)
        if wait:
            log.info("Co-execution job setup, now waiting for job completion and postprocessing.")
            wait_for_job(manager, job_config)
            log.info("Leaving finish_execution and shutting down app")
        else:
            job_status = wait_for_launch(manager, job_config)
    except BaseException:
        if wait:
            message = "Failure submitting or waiting on job."
        else:
            message = "Failure submitting job."
        log.exception(message)
        job_status = FAILED
    finally:
        app.shutdown()
    if wait:
        return EXIT_SUCCESS
    return _exit_code_for_status(job_status)


def run_server_for_job_finish(args):
    """Finish a job and return the process exit code.

    Non-zero when finishing failed or the job ended failed, for instance
    because its outputs could not be staged back. Only sequential
    coexecution runs ``pulsar-finish``.
    """
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
        job_status = wait_for_job(manager, job_config)
        log.info("Leaving finish_execution and shutting down app")
    except BaseException:
        log.exception("Failure finishing job.")
        job_status = FAILED
    finally:
        app.shutdown()
    return _exit_code_for_status(job_status)


def _exit_code_for_status(job_status):
    if job_status in FAILED_STATUSES:
        log.error("Job ended with status [%s].", job_status)
        return EXIT_FAILURE
    return EXIT_SUCCESS


def wait_for_job(manager, job_config, poll_time=DEFAULT_POLL_TIME):
    """Poll until the job is done and return its final status."""
    return _wait_for_status(manager, job_config.get('job_id'), is_job_done, poll_time)


def wait_for_launch(manager, job_config, poll_time=DEFAULT_LAUNCH_POLL_TIME):
    """Wait until the job has staged its inputs and launched, or failed to.

    The stateful manager publishes ``running`` from ``get_status``, the first
    time it sees the launched job running. Without a waiting submit, the app
    shuts down while inputs are still staging, so nothing polls the job and
    ``running`` is never published.

    Returns the first status after preprocessing.
    """
    return _wait_for_status(manager, job_config.get('job_id'), lambda status: status != PREPROCESSING, poll_time)


def _wait_for_status(manager, job_id, until: Callable[[StateLiteral], bool], poll_time):
    while True:
        status = manager.get_status(job_id)
        if until(status):
            return status
        time.sleep(poll_time)


def _load_job_config(args):
    if args.base64:
        base64_job_config = args.base64
        job_config = from_base64_json(base64_job_config)
    else:
        with open(args.file) as fh:
            job_config = json.load(fh)
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
