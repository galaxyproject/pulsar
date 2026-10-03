import pytest

from pulsar.client import build_client_manager as build_compatible_client_manager
from pulsar.client.client import MessageJobClient
from pulsar.client.coexecution_manager import (
    build_client_manager,
    CoexecutionMessageQueueClientManager,
    CoexecutionPollingJobClientManager,
)
from pulsar.client.gcp import (
    GcpMessageCoexecutionJobClient,
    GcpPollingCoexecutionJobClient,
)
from pulsar.client.kubernetes import (
    K8sMessageCoexecutionJobClient,
    K8sPollingCoexecutionJobClient,
)
from pulsar.client.manager import (
    build_client_manager as build_standard_client_manager,
    MessageQueueClientManager,
)
from pulsar.client.tes import (
    TesMessageCoexecutionJobClient,
    TesPollingCoexecutionJobClient,
)


@pytest.mark.parametrize(('options', 'destination', 'message_class', 'polling_class'), [
    ({'k8s_enabled': True}, {'k8s_enabled': True}, K8sMessageCoexecutionJobClient, K8sPollingCoexecutionJobClient),
    ({'tes_enabled': True}, {'tes_url': 'http://tes.example'}, TesMessageCoexecutionJobClient, TesPollingCoexecutionJobClient),
    ({'gcp_batch_enabled': True}, {'project_id': 'test-project'}, GcpMessageCoexecutionJobClient, GcpPollingCoexecutionJobClient),
])
@pytest.mark.parametrize('factory', [build_client_manager, build_compatible_client_manager])
@pytest.mark.parametrize('messaging', [True, False])
def test_factory_selects_backend_and_status_transport(options, destination, message_class, polling_class, messaging, factory):
    if messaging:
        manager = factory(amqp_url='memory://', **options)
        expected_manager = CoexecutionMessageQueueClientManager
        expected_client = message_class
    else:
        manager = factory(**options)
        expected_manager = CoexecutionPollingJobClientManager
        expected_client = polling_class
    try:
        client = manager.get_client(dict(destination), 'job-123')
        assert isinstance(manager, expected_manager)
        assert isinstance(client, expected_client)
        assert client.job_id == 'job-123'
        assert client.job_directory
    finally:
        manager.shutdown()


def test_coexecution_factory_keeps_ordinary_amqp_destinations():
    manager = build_client_manager(amqp_url='memory://')
    try:
        client = manager.get_client({'jobs_directory': '/jobs'}, 'job-123')
        assert isinstance(client, MessageJobClient)
    finally:
        manager.shutdown()


@pytest.mark.parametrize('factory', [build_client_manager, build_compatible_client_manager])
def test_coexecution_factory_accepts_legacy_positional_configuration(factory):
    manager = factory(None, None, None, None, None, None, 'memory://', False, False, False)
    try:
        assert isinstance(manager, CoexecutionMessageQueueClientManager)
        client = manager.get_client({'jobs_directory': '/jobs'}, 'job-123')
        assert isinstance(client, MessageJobClient)
    finally:
        manager.shutdown()


def test_standard_factory_uses_standard_manager():
    manager = build_standard_client_manager(amqp_url='memory://')
    try:
        assert type(manager) is MessageQueueClientManager
        with pytest.raises(ValueError, match=r'pulsar\.client\.coexecution_manager'):
            manager.get_client({'tes_url': 'http://tes.example'}, 'job-123')
    finally:
        manager.shutdown()


def test_backend_selection_keeps_kubernetes_precedence():
    manager = build_client_manager(k8s_enabled=True)
    client = manager.get_client({
        'k8s_enabled': True,
        'tes_url': 'http://tes.example',
        'project_id': 'test-project',
    }, 'job-123')
    assert isinstance(client, K8sPollingCoexecutionJobClient)
