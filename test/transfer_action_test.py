import os

from .test_utils import files_server
from pulsar.client.action_mapper import (
    JsonTransferAction,
    RemoteTransferAction,
)


def test_write_to_path_json():
    with files_server() as (server, directory):
        from_path = os.path.join(directory, "remote_get")

        to_path = os.path.join(directory, "local_get")
        url = server.application_url + "?path=%s" % from_path
        action = JsonTransferAction({"path": to_path}, url=url)
        action.write_to_path(to_path)
        assert action.path == to_path
        assert action.url == url
        assert action.finalize() == {"path": to_path, "url": url}


def test_write_from_file_json():
    with files_server() as (server, directory):
        from_path = os.path.join(directory, "local_post")
        to_path = os.path.join(directory, "remote_post")
        url = server.application_url + "?path=%s" % to_path
        action = JsonTransferAction({"path": to_path}, url=url)
        action.write_from_path(from_path)
        assert action.path == to_path
        assert action.url == url
        assert action.finalize() == {"path": to_path, "url": url}


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
