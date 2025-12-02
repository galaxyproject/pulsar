"""
"""

from abc import (
    ABCMeta,
    abstractmethod,
)
from typing import Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from galaxy.tools.deps.dependencies import DependencyDescription
    from pulsar.managers.status import StateLiteral

PULSAR_UNKNOWN_RETURN_CODE = "__unknown__"


class ManagerInterface:
    """
    Defines the interface to various job managers.
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def setup_job(
        self, input_job_id: str, tool_id: Optional[str], tool_version: Optional[str]
    ) -> str:
        """
        Setup a job directory for specified input (galaxy) job id, tool id,
        and tool version.
        """

    @abstractmethod
    def clean(self, job_id: str) -> None:
        """
        Delete job directory and clean up resources associated with job with
        id `job_id`.
        """

    @abstractmethod
    def launch(
        self,
        job_id: str,
        command_line: str,
        submit_params: Dict[str, str] = {},
        dependencies_description: Optional["DependencyDescription"] = None,
        env: List[Dict[str, str]] = [],
        setup_params: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Called to indicate that the client is ready for this job with specified
        job id and command line to be executed (i.e. run or queue this job
        depending on implementation).
        """

    @abstractmethod
    def get_status(self, job_id: str) -> "StateLiteral":
        """
        Return status of job as string, currently supported statuses include
        'cancelled', 'running', 'queued', and 'complete'.
        """

    @abstractmethod
    def return_code(self, job_id: str) -> Union[int, bytes]:
        """
        Return integer indicating return code of specified execution or
        PULSAR_UNKNOWN_RETURN_CODE.
        """

    @abstractmethod
    def stdout_contents(self, job_id: str) -> bytes:
        """
        After completion, return contents of stdout of the tool script.
        """

    @abstractmethod
    def stderr_contents(self, job_id: str) -> bytes:
        """
        After completion, return contents of stderr of the tool script.
        """

    @abstractmethod
    def job_stdout_contents(self, job_id: str) -> bytes:
        """
        After completion, return contents of stdout of the job as produced by the job runner.
        """

    @abstractmethod
    def job_stderr_contents(self, job_id: str) -> bytes:
        """
        After completion, return contents of stderr of the job as produced by the job runner.
        """

    @abstractmethod
    def kill(self, job_id: str) -> None:
        """
        End or cancel execution of the specified job.
        """

    # TODO return type? Is this implemented anywhere, should be or? Found it only in ManagerProxy
    @abstractmethod
    def job_directory(self, job_id: str):
        """Return a JobDirectory abstraction describing the state of the
        job working directory.
        """


class ManagerProxy:
    """
    Subclass to build override proxy a manager and override specific
    functionality.
    """

    def __init__(self, manager):
        self._proxied_manager = manager

    def setup_job(self, *args, **kwargs) -> str:
        return self._proxied_manager.setup_job(*args, **kwargs)

    def clean(self, *args, **kwargs) -> None:
        return self._proxied_manager.clean(*args, **kwargs)

    def launch(self, *args, **kwargs) -> None:
        return self._proxied_manager.launch(*args, **kwargs)

    def get_status(self, *args, **kwargs) -> "StateLiteral":
        return self._proxied_manager.get_status(*args, **kwargs)

    def return_code(self, *args, **kwargs) -> Union[int, bytes]:
        return self._proxied_manager.return_code(*args, **kwargs)

    def stdout_contents(self, *args, **kwargs) -> bytes:
        return self._proxied_manager.stdout_contents(*args, **kwargs)

    def stderr_contents(self, *args, **kwargs) -> bytes:
        return self._proxied_manager.stderr_contents(*args, **kwargs)

    def job_stdout_contents(self, *args, **kwargs) -> bytes:
        return self._proxied_manager.job_stdout_contents(*args, **kwargs)

    def job_stderr_contents(self, *args, **kwargs) -> bytes:
        return self._proxied_manager.job_stderr_contents(*args, **kwargs)

    def kill(self, *args, **kwargs) -> None:
        return self._proxied_manager.kill(*args, **kwargs)

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """Optional."""
        try:
            shutdown_method = self._proxied_manager.shutdown
        except AttributeError:
            return
        shutdown_method(timeout)

    def job_directory(self, *args, **kwargs):
        return self._proxied_manager.job_directory(*args, **kwargs)

    def system_properties(self):
        return self._proxied_manager.system_properties()

    @property
    def object_store(self):
        return self._proxied_manager.object_store

    def __str__(self):
        return "ManagerProxy[manager=%s]" % str(self._proxied_manager)
