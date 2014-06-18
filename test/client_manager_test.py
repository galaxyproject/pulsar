from os import environ

from pulsar.client.manager import ClientManager


def test_environment_variables_config():
    environ['PULSAR_CACHE_TRANSFERS'] = '1'
    client_manager = ClientManager()
    assert __produces_caching_client(client_manager)

    environ['PULSAR_CACHE_TRANSFERS'] = '0'
    client_manager = ClientManager()
    assert not __produces_caching_client(client_manager)

    environ['PULSAR_CACHE_TRANSFERS'] = '1'
    environ['PULSAR_CACHE_THREADS'] = '4'
    client_manager = ClientManager()
    client_manager.client_cacher.num_transfer_threads == 4


def test_kwds_config():
    client_manager = ClientManager(cache=True, transfer_threads=3)
    assert __produces_caching_client(client_manager)
    assert client_manager.client_cacher.num_transfer_threads == 3

    client_manager = ClientManager(cache=False)
    assert not __produces_caching_client(client_manager)


def __produces_caching_client(client_manager):
    return client_manager.client_class.__name__.find('Caching') > 0
