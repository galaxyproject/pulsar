import os
from unittest import mock

import pytest

from pulsar.client import action_mapper
from pulsar.client.action_mapper import (
    DICTIFIABLE_ACTION_CLASSES,
    from_dict,
    MessageAction,
    RemoteCopyAction,
    RemoteObjectStoreCopyAction,
    RemoteTransferAction,
    RemoteTransferTusAction,
    RsyncTransferAction,
    ScpTransferAction,
)
from .test_utils import files_server

SOURCE = {"path": "/out.dat"}
URL = "http://galaxy.test/api/jobs/1/files?job_key=k&path=/out.dat"
DICTIFIABLE_ACTIONS = [
    RemoteCopyAction(SOURCE),
    RemoteTransferAction(SOURCE, url=URL),
    RemoteTransferTusAction(SOURCE, url=URL),
    MessageAction("contents"),
    RsyncTransferAction(SOURCE, ssh_user="u", ssh_host="h", ssh_port=22, ssh_key="k"),
    ScpTransferAction(SOURCE, ssh_user="u", ssh_host="h", ssh_port=22, ssh_key="k"),
    RemoteObjectStoreCopyAction(SOURCE),
]


def test_every_dictifiable_action_is_round_tripped_below():
    assert {type(action) for action in DICTIFIABLE_ACTIONS} == set(DICTIFIABLE_ACTION_CLASSES)


@pytest.mark.parametrize("action", DICTIFIABLE_ACTIONS, ids=lambda action: type(action).__name__)
def test_action_survives_being_rebuilt_from_its_dict(action):
    as_dict = action.to_dict()
    if getattr(action, "inject_ssh_properties", False):
        # The key is never serialized; Pulsar adds it back from the staging config.
        as_dict["ssh_key"] = action.ssh_key
    rebuilt = from_dict(as_dict)
    assert type(rebuilt) is type(action)
    assert rebuilt.to_dict() == action.to_dict()


def test_tus_action_rebuilt_from_launch_config_uploads_with_tus(tmp_path):
    """The Pulsar server rebuilds staging actions from their serialized form, so a
    TUS action must still upload through TUS rather than a multipart POST."""
    url = "http://galaxy.test/api/jobs/1/files?job_key=k&path=/out.dat"
    action = from_dict(RemoteTransferTusAction({"path": "/out.dat"}, url=url).to_dict())
    local_path = tmp_path / "out.dat"
    local_path.write_bytes(b"123456")

    with mock.patch.object(action_mapper, "tus_upload_file") as tus_upload, \
            mock.patch.object(action_mapper, "post_file") as post:
        action.write_from_path(str(local_path))

    tus_upload.assert_called_once_with(url, str(local_path))
    post.assert_not_called()


def test_write_to_file():
    with files_server() as (server, directory):
        from_path = os.path.join(directory, "remote_get")
        open(from_path, "wb").write(b"123456")

        to_path = os.path.join(directory, "local_get")
        url = server.application_url + "?path=%s" % from_path
        RemoteTransferAction({"path": to_path}, url=url).write_to_path(to_path)

        assert open(to_path, "rb").read() == b"123456"


def test_write_from_file():
    with files_server() as (server, directory):
        from_path = os.path.join(directory, "local_post")
        open(from_path, "wb").write(b"123456")

        to_path = os.path.join(directory, "remote_post")
        url = server.application_url + "?path=%s" % to_path
        RemoteTransferAction({"path": to_path}, url=url).write_from_path(from_path)

        posted_contents = open(to_path, "rb").read()
        assert posted_contents == b"123456", posted_contents
