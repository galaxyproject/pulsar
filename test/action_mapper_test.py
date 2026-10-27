from galaxy.util.bunch import Bunch

from pulsar.client.action_mapper import (
    FileActionMapper,
)


def test_endpoint_validation():
    client = _min_client("remote_transfer")
    mapper = FileActionMapper(client)
    exception_found = False
    try:
        mapper.action({'path': '/opt/galaxy/tools/filters/catWrapper.py'}, 'input')
    except Exception as e:
        exception_found = True
        assert "files_endpoint" in str(e)
    assert exception_found


def test_source_url_is_used_for_remote_transfer():
    # Galaxy may hand out its own URL per input; no files_endpoint is then needed.
    mapper = FileActionMapper(_min_client("remote_transfer"))
    url = "https://galaxy.test/api/jobs/1/staging/inputs/dataset/3?exp=1&sig=abc"
    action = mapper.action({'path': '/galaxy/files/dataset_3.dat', 'url': url}, 'input')
    assert action.url == url
    assert action.to_dict()["url"] == url


def test_ssh_key_validation():
    client = _min_client("remote_rsync_transfer")
    mapper = FileActionMapper(client)
    exception_found = False
    try:
        mapper.action({'path': '/opt/galaxy/tools/filters/catWrapper.py'}, 'input')
    except Exception as e:
        exception_found = True
        assert "ssh_key" in str(e)
    assert exception_found


def test_ssh_key_defaults():
    client = _client("remote_rsync_transfer")
    mapper = FileActionMapper(client)
    action = mapper.action({'path': '/opt/galaxy/tools/filters/catWrapper.py'}, 'input')
    action.to_dict()


def _min_client(default_action):
    """Minimal client, missing properties for certain actions."""
    mock_client = Bunch(
        default_file_action=default_action,
        action_config_path=None,
        files_endpoint=None,
        ssh_key=None,
    )
    return mock_client


def _client(default_action):
    mock_client = Bunch(
        default_file_action=default_action,
        action_config_path=None,
        files_endpoint="http://localhost",
        ssh_key="12345",
    )
    return mock_client
