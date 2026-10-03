"""Container coexecution through GA4GH TES."""

import logging
from typing import (
    Any,
    Dict,
    Optional,
)

from pulsar.managers import status as manager_status
from pulsar.managers.util.job_name import produce_unique_k8s_job_name
from pulsar.managers.util.tes import (
    ensure_tes_client,
    tes_galaxy_instance_id,
    TesClient,
    TesExecutor,
    TesState,
    TesTask,
)
from .client import CONTAINER_STAGING_DIRECTORY
from .coexecution import (
    BaseMessageCoexecutionJobClient,
    BasePollingCoexecutionJobClient,
    CoexecutionLaunchMixin,
    ExecutionType,
)
from .container_job_config import CoexecutionContainerCommand
from .tes_job_config import (
    parse_tes_job_params,
    tes_client_from_params,
    tes_resources,
)
from .util import ExternalId

log = logging.getLogger(__name__)


def tes_state_to_pulsar_status(state: Optional[TesState]) -> str:
    state = state or TesState.UNKNOWN
    state_map = {
        TesState.UNKNOWN: manager_status.FAILED,
        TesState.INITIALIZING: manager_status.PREPROCESSING,
        TesState.RUNNING: manager_status.RUNNING,
        TesState.PAUSED: manager_status.RUNNING,
        TesState.COMPLETE: manager_status.COMPLETE,
        TesState.EXECUTOR_ERROR: manager_status.FAILED,
        TesState.SYSTEM_ERROR: manager_status.FAILED,
        TesState.CANCELED: manager_status.CANCELLED,
    }
    if state not in state_map:
        log.warning(f"Unknown tes state encountered [{state}]")
        return manager_status.FAILED
    else:
        return state_map[state]


def tes_state_is_complete(state: Optional[TesState]) -> bool:
    state = state or TesState.UNKNOWN
    state_map = {
        TesState.UNKNOWN: True,
        TesState.INITIALIZING: False,
        TesState.RUNNING: False,
        TesState.PAUSED: False,
        TesState.COMPLETE: True,
        TesState.EXECUTOR_ERROR: True,
        TesState.SYSTEM_ERROR: True,
        TesState.CANCELED: True,
    }
    if state not in state_map:
        log.warning(f"Unknown tes state encountered [{state}]")
        return True
    else:
        return state_map[state]


class LaunchesTesContainersMixin(CoexecutionLaunchMixin):
    """"""
    ensure_library_available = ensure_tes_client
    execution_type = ExecutionType.SEQUENTIAL

    def default_staging_directory(self, destination_params):
        return CONTAINER_STAGING_DIRECTORY

    def _launch_containers(
        self,
        pulsar_submit_container: CoexecutionContainerCommand,
        tool_container: Optional[CoexecutionContainerCommand],
        pulsar_finish_container: Optional[CoexecutionContainerCommand]
    ) -> ExternalId:
        volumes = [
            CONTAINER_STAGING_DIRECTORY,
        ]
        pulsar_container_executor = self._container_to_executor(pulsar_submit_container)
        executors = [pulsar_container_executor]
        if tool_container:
            tool_container_executor = self._container_to_executor(tool_container)
            executors.append(tool_container_executor)

            assert pulsar_finish_container
            pulsar_finish_executor = self._container_to_executor(pulsar_finish_container)
            executors.append(pulsar_finish_executor)

        name = self._tes_job_name
        tes_task = TesTask(
            name=name,
            executors=executors,
            volumes=volumes,
            resources=tes_resources(self._tes_job_params)
        )
        created_task = self._tes_client.create_task(tes_task)
        return ExternalId(created_task.id)

    def _container_to_executor(self, container: CoexecutionContainerCommand) -> TesExecutor:
        if container.ports:
            raise Exception("exposing container ports not possible via TES")
        return TesExecutor(
            image=container.image,
            command=[container.command, *container.args],
            workdir=container.working_directory,
        )

    @property
    def _tes_client(self) -> TesClient:
        return tes_client_from_params(self._tes_job_params)

    @property
    def _tes_job_name(self):
        # currently just _k8s_job_prefix... which might be fine?
        job_id = self.job_id
        job_name = produce_unique_k8s_job_name(app_prefix="pulsar", job_id=job_id, instance_id=self.instance_id)
        return job_name

    @property
    def _tes_task_id(self):
        """Return the provider-assigned TES id when Galaxy recorded one."""
        return self.external_id or self.job_id

    def _setup_tes_client_properties(self, destination_params):
        self.instance_id = tes_galaxy_instance_id(destination_params)

    def kill(self):
        self._tes_client.cancel_task(self._tes_task_id)

    def clean(self):
        pass

    def raw_check_complete(self) -> Dict[str, Any]:
        tes_task: TesTask = self._tes_client.get_task(self._tes_task_id, "FULL")
        tes_state = tes_task.state
        return {
            "status": tes_state_to_pulsar_status(tes_state),
            "complete": "true" if tes_state_is_complete(tes_state) else "false",  # Ancient John, what were you thinking?
        }

    @property
    def _tes_job_params(self):
        tes_job_params = parse_tes_job_params(self.destination_params)
        return tes_job_params


class TesPollingCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesTesContainersMixin):
    """A client that co-executes pods via GA4GH TES and depends on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_tes_client_properties(destination_params)


class TesMessageCoexecutionJobClient(BaseMessageCoexecutionJobClient, LaunchesTesContainersMixin):
    """A client that co-executes pods via GA4GH TES and doesn't depend on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_tes_client_properties(destination_params)
