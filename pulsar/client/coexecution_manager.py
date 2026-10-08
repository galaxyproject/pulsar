"""Client factories with explicitly imported container coexecution backends."""

from typing import (
    ClassVar,
    Mapping,
    Type,
)

from .client import BaseJobClient
from .gcp import (
    GcpMessageCoexecutionJobClient,
    GcpPollingCoexecutionJobClient,
)
from .kubernetes import (
    K8sMessageCoexecutionJobClient,
    K8sPollingCoexecutionJobClient,
)
from .manager import (
    build_client_manager as build_standard_client_manager,
    ClientManagerInterface,
    MessageQueueClientManager,
    PollingJobClientManager,
)
from .tes import (
    TesMessageCoexecutionJobClient,
    TesPollingCoexecutionJobClient,
)


class CoexecutionMessageQueueClientManager(MessageQueueClientManager):
    coexecution_clients: ClassVar[Mapping[str, Type[BaseJobClient]]] = {
        "k8s": K8sMessageCoexecutionJobClient,
        "tes": TesMessageCoexecutionJobClient,
        "gcp": GcpMessageCoexecutionJobClient,
    }


class CoexecutionPollingJobClientManager(PollingJobClientManager):
    coexecution_clients: ClassVar[Mapping[str, Type[BaseJobClient]]] = {
        "k8s": K8sPollingCoexecutionJobClient,
        "tes": TesPollingCoexecutionJobClient,
        "gcp": GcpPollingCoexecutionJobClient,
    }


def build_client_manager(*args, **kwargs) -> ClientManagerInterface:
    """Build a manager supporting Kubernetes, TES, and Google Cloud Batch.

    Accepts the same configuration as ``pulsar.client.manager.build_client_manager``.
    """
    return build_standard_client_manager(
        *args,
        message_queue_client_manager_class=CoexecutionMessageQueueClientManager,
        polling_job_client_manager_class=CoexecutionPollingJobClientManager,
        **kwargs,
    )
