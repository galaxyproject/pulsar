"""

Managers

:mod:`lwr.managers.base` Module
-------------------------------

.. automodule:: lwr.managers.base
    :members:
    :undoc-members:
    :show-inheritance:

:mod:`lwr.managers.drmaa` Module
--------------------------------

.. automodule:: lwr.managers.drmaa
    :members:
    :undoc-members:
    :show-inheritance:

:mod:`lwr.managers.pbs` Module
------------------------------

.. automodule:: lwr.managers.pbs
    :members:
    :undoc-members:
    :show-inheritance:

:mod:`lwr.managers.queued` Module
---------------------------------

.. automodule:: lwr.managers.queued
    :members:
    :undoc-members:
    :show-inheritance:


"""
from abc import ABCMeta, abstractmethod

LWR_UNKNOWN_RETURN_CODE = '__unknown__'


class ManagerInterface(object):
    """
    Defines the interface to various job managers.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def setup_job(self, input_job_id, tool_id, tool_version):
        """
        Setup a job directory for specified input (galaxy) job id, tool id,
        and tool version.
        """

    @abstractmethod
    def clean(self, job_id):
        """
        Delete job directory and clean up resources associated with job with
        id `job_id`.
        """

    @abstractmethod
    def launch(self, job_id, command_line, submit_params={}):
        """
        Called to indicate that the client is ready for this job with specified
        job id and command line to be executed (i.e. run or queue this job
        depending on implementation).
        """

    @abstractmethod
    def get_status(self, job_id):
        """
        Return status of job as string, currently supported statuses include
        'cancelled', 'running', 'queued', and 'complete'.
        """

    @abstractmethod
    def return_code(self, job_id):
        """
        Return integer indicating return code of specified execution or
        LWR_UNKNOWN_RETURN_CODE.
        """

    @abstractmethod
    def stdout_contents(self, job_id):
        """
        After completion, return contents of stdout associated with specified
        job.
        """

    @abstractmethod
    def stderr_contents(self, job_id):
        """
        After completion, return contents of stderr associated with specified
        job.
        """

    @abstractmethod
    def kill(self, job_id):
        """
        End or cancel execution of the specified job.
        """

    @abstractmethod
    def job_directory(self, job_id):
        """ Return a JobDirectory abstraction describing the state of the
        job working directory.
        """


class ManagerProxy(object):
    """
    Subclass to build override proxy a manager and override specific
    functionality.
    """

    def __init__(self, manager):
        self._proxied_manager = manager

    def setup_job(self, *args, **kwargs):
        return self._proxied_manager.setup_job(*args, **kwargs)

    def clean(self, *args, **kwargs):
        return self._proxied_manager.clean(*args, **kwargs)

    def launch(self, *args, **kwargs):
        return self._proxied_manager.launch(*args, **kwargs)

    def get_status(self, *args, **kwargs):
        return self._proxied_manager.get_status(*args, **kwargs)

    def return_code(self, *args, **kwargs):
        return self._proxied_manager.return_code(*args, **kwargs)

    def stdout_contents(self, *args, **kwargs):
        return self._proxied_manager.stdout_contents(*args, **kwargs)

    def stderr_contents(self, *args, **kwargs):
        return self._proxied_manager.stderr_contents(*args, **kwargs)

    def kill(self, *args, **kwargs):
        return self._proxied_manager.kill(*args, **kwargs)

    def shutdown(self):
        """ Optional. """
        try:
            shutdown_method = self._proxied_manager.shutdown
        except AttributeError:
            return
        shutdown_method()

    def job_directory(self, *args, **kwargs):
        return self._proxied_manager.job_directory(*args, **kwargs)

    def system_properties(self):
        return self._proxied_manager.system_properties()


def job_complete_dict(complete_status, manager, job_id):
    return_code = manager.return_code(job_id)
    stdout_contents = manager.stdout_contents(job_id)
    stderr_contents = manager.stderr_contents(job_id)
    job_directory = manager.job_directory(job_id)
    return dict(
        complete="true",  # Is this still used or is it legacy.
        status=complete_status,
        returncode=return_code,
        stdout=stdout_contents,
        stderr=stderr_contents,
        working_directory_contents=job_directory.working_directory_contents(),
        outputs_directory_contents=job_directory.outputs_directory_contents(),
        system_properties=manager.system_properties(),
    )
