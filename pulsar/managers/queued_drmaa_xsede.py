import logging
from subprocess import (
    CalledProcessError,
    check_call,
    PIPE,
    Popen,
)

from .queued_drmaa import DrmaaQueueManager

log = logging.getLogger(__name__)


class XsedeDrmaaQueueManager(DrmaaQueueManager):
    """
    DRMAA backed queue manager for XSEDE (to run the XSEDE job/user reporting
    script after submission).

    TODO: A generalized callback framework for executing things at various
    points in the job lifecycle.
    """
    manager_type = "queued_drmaa_xsede"

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
        super().launch(
            job_id,
            command_line,
            submit_params=submit_params,
            dependencies_description=dependencies_description,
            env=env,
            setup_params=setup_params,
        )
        try:
            check_call([
                'gateway_submit_attributes',
                '-gateway_user',
                submit_params.get('user_email', 'unknown@galaxyproject.org'),
                '-submit_time',
                check_output(['date', '+%F %T %:z']).strip(),
                '-jobid',
                self._external_ids[job_id]
            ])
        except (OSError, CalledProcessError):
            log.exception('Failed to call gateway_submit_attributes:')


def check_output(args):
    """Pipe-safe (and 2.6 compatible) version of subprocess.check_output
    """
    proc = Popen(args, stdout=PIPE)
    out = proc.communicate()[0]
    if proc.returncode:
        raise CalledProcessError(proc.returncode, args, output=out)
    return out
