"""Container coexecution through Google Cloud Batch."""

import logging
from typing import (
    Any,
    cast,
    Dict,
    Optional,
)

from pulsar.managers import status as manager_status
from pulsar.managers.util.gcp_util import (
    batch_v1,
    delete_gcp_job,
    ensure_client as ensure_gcp_client,
    gcp_client,
    get_gcp_job,
)
from pulsar.managers.util.job_name import produce_unique_k8s_job_name
from .coexecution import (
    BaseMessageCoexecutionJobClient,
    BasePollingCoexecutionJobClient,
    CoexecutionLaunchMixin,
    ExecutionType,
)
from .container_job_config import CoexecutionContainerCommand
from .gcp_job_config import (
    container_command_to_gcp_runnable,
    gcp_galaxy_instance_id,
    gcp_job_request,
    gcp_job_template,
    parse_gcp_job_params,
)

log = logging.getLogger(__name__)


class LaunchesGcpContainersMixin(CoexecutionLaunchMixin):
    ensure_library_available = ensure_gcp_client
    # https://cloud.google.com/php/docs/reference/cloud-batch/latest/V1.Runnable.Barrier
    # can we do barriers here to allow sequential? It would allow separate containers for startup
    # and shutdown that don't run parallel to the job?
    execution_type = ExecutionType.PARALLEL

    def default_staging_directory(self, destination_params):
        ssd_name = destination_params.get("ssd_name", "pulsar_staging")
        return f"/mnt/disks/{ssd_name}"

    def _setup_gcp_batch_client_properties(self, destination_params):
        self.instance_id = gcp_galaxy_instance_id(destination_params)

    def _launch_containers(
        self,
        pulsar_submit_container: CoexecutionContainerCommand,
        tool_container: Optional[CoexecutionContainerCommand],
        pulsar_finish_container: Optional[CoexecutionContainerCommand]
    ) -> None:
        assert pulsar_finish_container is None
        gcp_job_params = self._gcp_job_params
        job = gcp_job_template(gcp_job_params)

        # Parse docker_extra_volumes (comma-separated Docker -v style strings)
        # into a list for GCP Batch Runnable.Container.volumes
        extra_volumes = []
        raw = self.destination_params.get("docker_extra_volumes", "")
        if raw:
            extra_volumes = [v.strip() for v in raw.split(",") if v.strip()]

        # Order matters: GCP Batch runs runnables sequentially. A background
        # runnable starts and immediately yields to the next runnable. We need:
        #   1. Tool (background) — starts polling for command_line file
        #   2. Sidecar (foreground) — stages inputs, writes command_line, polls
        #      for return_code, collects outputs, sends AMQP callback
        # The sidecar must be foreground so it survives after the tool finishes
        # (GCP Batch kills background runnables when all foreground ones exit).
        if tool_container:
            tool_runnable = container_command_to_gcp_runnable("tool-container", tool_container)
            tool_runnable.background = True
            if extra_volumes:
                tool_runnable.container.volumes = extra_volumes
            job.task_groups[0].task_spec.runnables.append(tool_runnable)

        runnable = container_command_to_gcp_runnable("pulsar-container", pulsar_submit_container)
        if extra_volumes:
            runnable.container.volumes = extra_volumes
        job.task_groups[0].task_spec.runnables.append(runnable)

        job_name = self._job_name
        create_request = gcp_job_request(gcp_job_params, job, job_name)
        client = gcp_client(gcp_job_params.credentials_file)
        job = client.create_job(create_request)

    @property
    def _job_name(self):
        # currently just _k8s_job_prefix... which might be fine?
        job_id = self.job_id
        job_name = produce_unique_k8s_job_name(app_prefix="pulsar", job_id=job_id, instance_id=self.instance_id)
        return job_name

    @property
    def _gcp_job_params(self):
        gcp_job_params = parse_gcp_job_params(self.destination_params)
        return gcp_job_params


class GcpMessageCoexecutionJobClient(BaseMessageCoexecutionJobClient, LaunchesGcpContainersMixin):
    """A client that co-executes pods via GCP and depends on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_gcp_batch_client_properties(destination_params)


class GcpPollingCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesGcpContainersMixin):
    """A client that co-executes pods via GCP and doesn't depend on amqp."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        self._setup_gcp_batch_client_properties(destination_params)

    def kill(self):
        gcp_job_params = self._gcp_job_params
        delete_gcp_job(gcp_job_params.project_id, gcp_job_params.region, self._job_name, gcp_job_params.credentials_file)

    def clean(self):
        pass

    def full_status(self):
        status = self.raw_check_complete()
        return status

    def raw_check_complete(self) -> Dict[str, Any]:
        gcp_job_params = self._gcp_job_params
        job = get_gcp_job(gcp_job_params.project_id, gcp_job_params.region, self._job_name, gcp_job_params.credentials_file)
        status = job.status
        state = status.state
        return {
            "status": gcp_state_to_pulsar_status(state),
            "complete": "true" if gcp_state_is_complete(state) else "false",  # Ancient John, what were you thinking?
        }


def gcp_state_to_pulsar_status(state: Optional["batch_v1.JobStatus.State"]) -> str:
    state = state or cast(batch_v1.JobStatus.State, batch_v1.JobStatus.State.STATE_UNSPECIFIED)
    # STATE_UNSPECIFIED	Job state unspecified.
    # QUEUED	Job is admitted (validated and persisted) and waiting for resources.
    # SCHEDULED	Job is scheduled to run as soon as resource allocation is ready. The resource
    #           allocation may happen at a later time but with a high chance to succeed.
    # RUNNING	Resource allocation has been successful. At least one Task in the Job is RUNNING.
    # SUCCEEDED	All Tasks in the Job have finished successfully.
    # FAILED	At least one Task in the Job has failed.
    # DELETION_IN_PROGRESS	The Job will be deleted, but has not been deleted yet. Typically this is because resources
    #                       used by the Job are still being cleaned up.
    # CANCELLATION_IN_PROGRESS	The Job cancellation is in progress, this is because the resources used by the Job are
    #                           still being cleaned up.
    # CANCELLED The Job has been cancelled, the task executions were stopped and the resources were cleaned up.
    state_map = {
        batch_v1.JobStatus.State.STATE_UNSPECIFIED: manager_status.FAILED,
        batch_v1.JobStatus.State.QUEUED: manager_status.PREPROCESSING,
        batch_v1.JobStatus.State.RUNNING: manager_status.RUNNING,
        batch_v1.JobStatus.State.SCHEDULED: manager_status.COMPLETE,
        batch_v1.JobStatus.State.FAILED: manager_status.FAILED,
        batch_v1.JobStatus.State.DELETION_IN_PROGRESS: manager_status.FAILED,
        batch_v1.JobStatus.State.CANCELLATION_IN_PROGRESS: manager_status.CANCELLED,
        batch_v1.JobStatus.State.CANCELLED: manager_status.CANCELLED,
    }
    if state not in state_map:
        log.warning(f"Unknown tes state encountered [{state}]")
        return manager_status.FAILED
    else:
        return state_map[state]


def gcp_state_is_complete(state: Optional["batch_v1.JobStatus.State"]) -> bool:
    state = state or cast(batch_v1.JobStatus.State, batch_v1.JobStatus.State.STATE_UNSPECIFIED)
    state_map = {
        batch_v1.JobStatus.State.STATE_UNSPECIFIED: True,
        batch_v1.JobStatus.State.QUEUED: False,
        batch_v1.JobStatus.State.RUNNING: False,
        batch_v1.JobStatus.State.SCHEDULED: True,
        batch_v1.JobStatus.State.FAILED: True,
        batch_v1.JobStatus.State.DELETION_IN_PROGRESS: True,
        batch_v1.JobStatus.State.CANCELLATION_IN_PROGRESS: True,
        batch_v1.JobStatus.State.CANCELLED: True,
    }
    if state not in state_map:
        log.warning(f"Unknown gcp state encountered [{state}]")
        return True
    else:
        return state_map[state]
