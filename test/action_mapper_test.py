import pytest
from galaxy.util.bunch import Bunch

from pulsar.client import action_mapper
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


def test_destination_keys_are_derived_from_the_actions():
    """Nothing hard-codes the destination settings - the actions declare them."""
    expected = set()
    for action_class in action_mapper.ACTION_CLASSES:
        expected.update(action_class.destination_defaults)
    assert set(action_mapper.destination_keys()) == expected
    # The five that used to be hard-coded in the mapper.
    assert set(action_mapper.destination_keys()) == {
        "files_endpoint", "ssh_key", "ssh_user", "ssh_host", "ssh_port",
    }


def test_to_dict_keeps_the_wire_format():
    """``to_dict`` output is sent to Pulsar - the keys may not drift."""
    mapper = FileActionMapper(_client("remote_transfer"))
    as_dict = mapper.to_dict()
    assert set(as_dict) == {
        "default_action", "files_endpoint", "ssh_key", "ssh_user",
        "ssh_port", "ssh_host", "paths",
    }
    assert as_dict["default_action"] == "remote_transfer"
    assert as_dict["files_endpoint"] == "http://localhost"
    # Unset settings are still emitted, as they always were.
    assert as_dict["ssh_user"] is None


def test_action_can_add_a_destination_setting_without_touching_the_mapper():
    """The point of the exercise: a new action declares what it needs."""

    class _TokenAction(action_mapper.BaseAction):
        action_type = "test_token"
        staging = action_mapper.STAGING_ACTION_REMOTE
        destination_defaults = ("auth_token",)

    action_mapper.ACTION_CLASSES.append(_TokenAction)
    action_mapper.actions[_TokenAction.action_type] = _TokenAction
    try:
        client = Bunch(
            default_file_action="test_token",
            action_config_path=None,
            auth_token="s3cret",
        )
        mapper = FileActionMapper(client)
        action = mapper.action({"path": "/data/1.dat"}, "input")
        assert action.auth_token == "s3cret"
    finally:
        action_mapper.ACTION_CLASSES.remove(_TokenAction)
        del action_mapper.actions[_TokenAction.action_type]


def test_path_mapping_still_beats_the_destination_default():
    """Destination settings are defaults - a per-path value wins."""
    config = {
        "default_action": "none",
        "ssh_key": "destination-key",
        "ssh_user": "destination-user",
        "paths": [
            {
                "path": "/data",
                "action": "remote_rsync_transfer",
                "ssh_user": "path-user",
            }
        ],
    }
    mapper = FileActionMapper(config=config)
    action = mapper.action({"path": "/data/1.dat"}, "input")
    assert action.ssh_user == "path-user"
    assert action.ssh_key == "destination-key"


def test_remote_transfer_url_is_built_from_the_files_endpoint():
    mapper = FileActionMapper(_client("remote_transfer"))
    action = mapper.action({"path": "/data/1.dat"}, "input")
    assert action.url.startswith("http://localhost?")
    assert "path=%2Fdata%2F1.dat" in action.url
    assert "file_type=input" in action.url


def test_remote_transfer_url_appends_to_an_existing_query_string():
    client = _client("remote_transfer")
    client.files_endpoint = "http://localhost?job_key=k"
    mapper = FileActionMapper(client)
    action = mapper.action({"path": "/data/1.dat"}, "input")
    assert action.url.startswith("http://localhost?job_key=k&")


@pytest.mark.xfail(
    reason="Pre-existing: to_dict() omits ssh_key but from_dict() requires it. "
           "Whether the key belongs in the staging manifest at all is an open question.",
    strict=True,
)
def test_pubkey_action_round_trips_through_a_dict():
    action = action_mapper.RsyncTransferAction(
        {"path": "/data/1.dat"}, ssh_user="u", ssh_host="h", ssh_port="22", ssh_key="KEY"
    )
    action_mapper.from_dict(action.to_dict())
