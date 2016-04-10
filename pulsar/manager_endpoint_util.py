""" Composite actions over managers shared between HTTP endpoint (routes.py)
and message queue.
"""

import logging
import os

from pulsar import __version__ as pulsar_version
from pulsar.client.setup_handler import build_job_config
from pulsar.managers import status
from pulsar.managers import PULSAR_UNKNOWN_RETURN_CODE
from galaxy.tools.deps import dependencies

log = logging.getLogger(__name__)


def status_dict(manager, job_id):
    job_status = manager.get_status(job_id)
    return full_status(manager, job_status, job_id)


def full_status(manager, job_status, job_id):
    if job_status in [status.COMPLETE, status.CANCELLED]:
        full_status = __job_complete_dict(job_status, manager, job_id)
    else:
        full_status = {"complete": "false", "status": job_status, "job_id": job_id}
    return full_status


def __job_complete_dict(complete_status, manager, job_id):
    """ Build final dictionary describing completed job for consumption by
    Pulsar client.
    """
    return_code = manager.return_code(job_id)
    if return_code == PULSAR_UNKNOWN_RETURN_CODE:
        return_code = None
    stdout_contents = manager.stdout_contents(job_id).decode("utf-8")
    stderr_contents = manager.stderr_contents(job_id).decode("utf-8")
    job_directory = manager.job_directory(job_id)
    as_dict = dict(
        job_id=job_id,
        complete="true",  # Is this still used or is it legacy.
        status=complete_status,
        returncode=return_code,
        stdout=stdout_contents,
        stderr=stderr_contents,
        working_directory=job_directory.working_directory(),
        metadata_directory=job_directory.metadata_directory(),
        working_directory_contents=job_directory.working_directory_contents(),
        metadata_directory_contents=job_directory.metadata_directory_contents(),
        outputs_directory_contents=job_directory.outputs_directory_contents(),
        system_properties=manager.system_properties(),
        pulsar_version=pulsar_version,
    )
    return as_dict


def submit_job(manager, job_config):
    """ Launch new job from specified config. May have been previously 'setup'
    if 'setup_params' in job_config is empty.
    """
    # job_config is raw dictionary from JSON (from MQ or HTTP endpoint).
    job_id = job_config.get('job_id')
    command_line = job_config.get('command_line')

    setup_params = job_config.get('setup_params', {})
    force_setup = job_config.get('setup')
    remote_staging = job_config.get('remote_staging', {})
    dependencies_description = job_config.get('dependencies_description', None)
    env = job_config.get('env', [])
    submit_params = job_config.get('submit_params', {})
    job_config = None
    if setup_params or force_setup:
        input_job_id = setup_params.get("job_id", job_id)
        tool_id = setup_params.get("tool_id", None)
        tool_version = setup_params.get("tool_version", None)
        use_metadata = setup_params.get("use_metadata", False)
        job_config = setup_job(
            manager,
            input_job_id,
            tool_id,
            tool_version,
            use_metadata
        )

    if job_config is not None:
        job_directory = job_config["job_directory"]
        jobs_directory = os.path.abspath(os.path.join(job_directory, os.pardir))
        command_line = command_line.replace('__PULSAR_JOBS_DIRECTORY__', jobs_directory)

    # TODO: Handle __PULSAR_JOB_DIRECTORY__ config files, metadata files, etc...
    manager.handle_remote_staging(job_id, remote_staging)

    dependencies_description = dependencies.DependenciesDescription.from_dict(dependencies_description)
    return manager.launch(
        job_id,
        command_line,
        submit_params,
        dependencies_description=dependencies_description,
        env=env,
    )


def setup_job(manager, job_id, tool_id, tool_version, use_metadata=False):
    """ Setup new job from these inputs and return dict summarizing state
    (used to configure command line).
    """
    job_id = manager.setup_job(job_id, tool_id, tool_version)
    if use_metadata:
        manager.enable_metadata_directory(job_id)
    return build_job_config(
        job_id=job_id,
        job_directory=manager.job_directory(job_id),
        system_properties=manager.system_properties(),
        tool_id=tool_id,
        tool_version=tool_version
    )
