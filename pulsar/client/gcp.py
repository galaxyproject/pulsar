"""Container coexecution through Google Cloud Batch."""

import logging
import uuid
from typing import (
    Any,
    cast,
    Dict,
    Optional,
)

from pulsar.managers import status as manager_status
from pulsar.managers.util.gcp_util import (
    batch_v1,
    cancel_gcp_job,
    delete_gcp_job,
    ensure_client as ensure_gcp_client,
    gcp_client,
    GcpAlreadyExists,
    get_gcp_job,
)
from .coexecution import (
    BaseMessageCoexecutionJobClient,
    BasePollingCoexecutionJobClient,
    CoexecutionLaunchMixin,
    ExecutionType,
)
from .container_job_config import CoexecutionContainerCommand
from .gcp_job_config import (
    container_command_to_gcp_runnable,
    gcp_job_id_prefix,
    gcp_job_name,
    gcp_job_request,
    gcp_job_template,
    gcp_kill_action,
    parse_gcp_job_params,
)
from .util import ExternalId

log = logging.getLogger(__name__)


class LaunchesGcpContainersMixin(CoexecutionLaunchMixin):
    ensure_library_available = ensure_gcp_client
    # https://cloud.google.com/php/docs/reference/cloud-batch/latest/V1.Runnable.Barrier
    # can we do barriers here to allow sequential? It would allow separate containers for startup
    # and shutdown that don't run parallel to the job?
    execution_type = ExecutionType.PARALLEL
    job_id_prefix: str
    kill_action: str

    def default_staging_directory(self, destination_params):
        ssd_name = destination_params.get("ssd_name", "pulsar_staging")
        return f"/mnt/disks/{ssd_name}"

    def _setup_gcp_batch_client_properties(self, destination_params):
        self.job_id_prefix = gcp_job_id_prefix(destination_params)
        self.kill_action = gcp_kill_action(destination_params)

    def _launch_containers(
        self,
        pulsar_submit_container: CoexecutionContainerCommand,
        tool_container: Optional[CoexecutionContainerCommand],
        pulsar_finish_container: Optional[CoexecutionContainerCommand]
    ) -> ExternalId:
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

        client = gcp_client(gcp_job_params.credentials_file)
        job_name = self._default_job_name
        try:
            client.create_job(gcp_job_request(gcp_job_params, job, job_name))
        except GcpAlreadyExists:
            # A job with this name exists already: this Galaxy job was resubmitted
            # or a job with the same id was retained from an earlier run. Leave that
            # job alone and launch under a unique name. Galaxy records the returned
            # name and hands it back as external_id on later polls and kills.
            default_job_name = job_name
            job_name = gcp_job_name(self.job_id_prefix, self.job_id, suffix=uuid.uuid4().hex[:8])
            log.info("GCP Batch job %s already exists, launching job %s as %s", default_job_name, self.job_id, job_name)
            client.create_job(gcp_job_request(gcp_job_params, job, job_name))
        return ExternalId(job_name)

    @property
    def _default_job_name(self) -> str:
        """The name a job is launched under unless it collides with an existing job."""
        return gcp_job_name(self.job_id_prefix, self.job_id)

    @property
    def _job_name(self) -> str:
        """The Batch job name to poll or kill: the one Galaxy recorded at launch, else the default."""
        return self.external_id or self._default_job_name

    @property
    def _gcp_job_params(self):
        gcp_job_params = parse_gcp_job_params(self.destination_params)
        return gcp_job_params

    def kill(self):
        gcp_job_params = self._gcp_job_params
        job_name = self._job_name
        action = cancel_gcp_job if self.kill_action == "cancel" else delete_gcp_job
        try:
            action(gcp_job_params.project_id, gcp_job_params.region, job_name, gcp_job_params.credentials_file)
        except Exception:
            log.warning("Failed to %s GCP Batch job %s", self.kill_action, job_name, exc_info=True)


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
