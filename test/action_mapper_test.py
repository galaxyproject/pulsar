from galaxy.util.bunch import Bunch
from pulsar.client.action_mapper import (
    FileActionMapper,
)


def test_endpoint_validation():
    client = _client("remote_transfer")
    mapper = FileActionMapper(client)
    exception_found = False
    try:
        mapper.action('/opt/galaxy/tools/filters/catWrapper.py', 'input')
    except Exception as e:
        exception_found = True
        assert "files_endpoint" in e.message
    assert exception_found


def test_ssh_key_validation():
    client = _client("remote_rsync_transfer")
    mapper = FileActionMapper(client)
    exception_found = False
    try:
        action = mapper.action('/opt/galaxy/tools/filters/catWrapper.py', 'input')
    except Exception as e:
        exception_found = True
        assert "ssh_key" in e.message
    assert exception_found


def _client(default_action):
    mock_client = Bunch(
        default_file_action=default_action,
        action_config_path=None,
        files_endpoint=None,
    )
    return mock_client
