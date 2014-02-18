""" Composite actions over managers shared between HTTP endpoint (routes.py)
and message queue.
"""
from lwr.lwr_client.setup_handler import build_job_config
from galaxy.tools.deps.requirements import ToolRequirement


def job_complete_dict(complete_status, manager, job_id):
    """ Build final dictionary describing completed job for consumption by
    LWR client.
    """
    return_code = manager.return_code(job_id)
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
    setup_params = job_config.get('setup_params')
    remote_staging = job_config.get('remote_staging', {})
    requirements = job_config.get('requirements', [])
    submit_params = job_config.get('submit_params', {})

    if setup_params:
        input_job_id = setup_params.get("job_id", job_id)
        tool_id = setup_params.get("tool_id", None)
        tool_version = setup_params.get("tool_version", None)
        setup_job(manager, input_job_id, tool_id, tool_version)

    if remote_staging:
        manager.handle_remote_staging(job_id, remote_staging)

    requirements = [ToolRequirement.from_dict(r) for r in requirements]
    manager.launch(job_id, command_line, submit_params, requirements)


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
