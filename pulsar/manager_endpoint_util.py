""" Composite actions over managers shared between HTTP endpoint (routes.py)
and message queue.
"""
from pulsar.client.setup_handler import build_job_config
from pulsar.managers import status
from pulsar.managers import PULSAR_UNKNOWN_RETURN_CODE
from galaxy.tools.deps import dependencies
import os


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
    stdout_contents = manager.stdout_contents(job_id)
    stderr_contents = manager.stderr_contents(job_id)
    job_directory = manager.job_directory(job_id)
    return dict(
        job_id=job_id,
        complete="true",  # Is this still used or is it legacy.
        status=complete_status,
        returncode=return_code,
        stdout=stdout_contents,
        stderr=stderr_contents,
        working_directory=job_directory.working_directory(),
        working_directory_contents=job_directory.working_directory_contents(),
        outputs_directory_contents=job_directory.outputs_directory_contents(),
        system_properties=manager.system_properties(),
    )


def submit_job(manager, job_config):
    """ Launch new job from specified config. May have been previously 'setup'
    if 'setup_params' in job_config is empty.
    """
    # job_config is raw dictionary from JSON (from MQ or HTTP endpoint).
    job_id = job_config.get('job_id')
    command_line = job_config.get('command_line')
    # Replace the string PULSAR_PATH (given by galaxy) with the actual path,
    # which prevents the need for pulsar specific configuration in galaxy, when
    # using MQs
    PULSAR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    command_line = command_line.replace('PULSAR_PATH', PULSAR_PATH)

    setup_params = job_config.get('setup_params')
    remote_staging = job_config.get('remote_staging', {})
    dependencies_description = job_config.get('dependencies_description', None)
    env = job_config.get('env', [])
    submit_params = job_config.get('submit_params', {})

    if setup_params:
        input_job_id = setup_params.get("job_id", job_id)
        tool_id = setup_params.get("tool_id", None)
        tool_version = setup_params.get("tool_version", None)
        setup_job(manager, input_job_id, tool_id, tool_version)

    if remote_staging:
        manager.handle_remote_staging(job_id, remote_staging)

    dependencies_description = dependencies.DependenciesDescription.from_dict(dependencies_description)
    return manager.launch(
        job_id,
        command_line,
        submit_params,
        dependencies_description=dependencies_description,
        env=env
    )


def setup_job(manager, job_id, tool_id, tool_version):
    """ Setup new job from these inputs and return dict summarizing state
    (used to configure command line).
    """
    job_id = manager.setup_job(job_id, tool_id, tool_version)
    return build_job_config(
        job_id=job_id,
        job_directory=manager.job_directory(job_id),
        system_properties=manager.system_properties(),
        tool_id=tool_id,
        tool_version=tool_version,
    )
