"""Placeholder AWS Batch coexecution clients."""

from .coexecution import (
    BasePollingCoexecutionJobClient,
    CoexecutionLaunchMixin,
    ExecutionType,
)


class LaunchesAwsBatchContainersMixin(CoexecutionLaunchMixin):
    """..."""
    execution_type = ExecutionType.SEQUENTIAL


class AwsBatchPollingCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesAwsBatchContainersMixin):
    """A client that co-executes pods via AWS Batch and doesn't depend on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        raise NotImplementedError()


class AwsBatchMessageCoexecutionJobClient(BasePollingCoexecutionJobClient, LaunchesAwsBatchContainersMixin):
    """A client that co-executes pods via AWS Batch and depends on amqp for status updates."""

    def __init__(self, destination_params, job_id, client_manager):
        super().__init__(destination_params, job_id, client_manager)
        raise NotImplementedError()
