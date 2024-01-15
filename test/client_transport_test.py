import os
import contextlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from pulsar.client.transport.standard import UrllibTransport
from pulsar.client.transport.curl import PycurlTransport
from pulsar.client.transport.curl import post_file
from pulsar.client.transport.curl import get_file
from pulsar.client.transport.tus import find_tus_endpoint
from pulsar.client.transport import get_transport

from .test_utils import files_server
from .test_utils import skip_unless_module


def test_urllib_transports():
    _test_transport(UrllibTransport())


@skip_unless_module("pycurl")
def test_pycurl_transport():
    _test_transport(PycurlTransport())


@contextlib.contextmanager
def path_to_get_fixture(directory):
    path = Path(directory, f"test_for_GET_{str(uuid4())}")
    path.write_text(" Test123 ")
    path.chmod(0o755)
    yield path
    os.remove(path)


def _test_transport(transport):
    with files_server() as (server, directory):
        server_url = server.application_url
        with path_to_get_fixture(directory) as path:
            request_url = "{}?path={}".format(server_url, path)

            # Testing simple get
            response = transport.execute(request_url, data=None)
            assert response.find(b"Test123") >= 0

        with path_to_get_fixture(directory) as path:
            request_url = "{}?path={}".format(server_url, path)

            # Testing writing to output file
            temp_file = NamedTemporaryFile(delete=True)
            output_path = temp_file.name
            temp_file.close()
            response = transport.execute(request_url, data=None, output_path=output_path)
            assert open(output_path).read().find("Test123") >= 0


@skip_unless_module("pycurl")
def test_curl_put_get():
    with files_server() as (server, directory):
        with path_to_get_fixture(directory) as path:
            server_url = server.application_url
            path = Path(directory, f"test_for_curl_io_{str(uuid4())}")
            request_url = "{}?path={}".format(server_url, str(path))

            input = os.path.join(directory, f"test_for_curl_io_input_{str(uuid4())}")
            output = os.path.join(directory, f"test_for_curl_io_output_{str(uuid4())}")
            open(input, "w").write("helloworld")

            post_file(request_url, input)
            get_file(request_url, output)
            assert open(output).read() == "helloworld"


def test_curl_status_code():
    with files_server() as (server, directory):
        server_url = server.application_url
        path = os.path.join(directory, f"test_for_GET_absent_{str(uuid4())}")
        request_url = "{}?path={}".format(server_url, path)
        # Verify curl doesn't just silently swallow errors.
        exception_raised = False
        try:
            get_file(request_url, os.path.join(directory, "test"))
        except Exception:
            exception_raised = True
        assert exception_raised

        post_request_url = "{}?path={}".format(server_url, "/usr/bin/cow")
        exception_raised = False
        try:
            post_file(post_request_url, os.path.join(directory, "test"))
        except Exception:
            exception_raised = True
        assert exception_raised


@skip_unless_module("pycurl")
def test_curl_problems():
    with files_server() as (server, directory):
        server_url = server.application_url
        path = os.path.join(directory, f"test_for_GET_invalidinput_{str(uuid4())}")
        request_url = "{}?path={}".format(server_url, path)
        exception_raised = False
        try:
            # Valid destination but the file to post doesn't exist.
            post_file(request_url, os.path.join(directory, f"test-{str(uuid4())}"))
        except Exception:
            exception_raised = True
        assert exception_raised


def test_find_tus_endpoint():
    galaxy_endpoint = "http://subdomain.galaxy.org/prefix/api/jobs/1231sdfsq23e/files?job_key=34"
    tus_endpoint = find_tus_endpoint(galaxy_endpoint)
    assert tus_endpoint == "http://subdomain.galaxy.org/prefix/api/job_files/resumable_upload?job_key=34"


def test_get_transport():
    assert type(get_transport(None, FakeOsModule("1"))) == PycurlTransport
    assert type(get_transport(None, FakeOsModule("TRUE"))) == PycurlTransport
    assert type(get_transport(None, FakeOsModule("0"))) == UrllibTransport
    assert type(get_transport('urllib', FakeOsModule("TRUE"))) == UrllibTransport
    assert type(get_transport('curl', FakeOsModule("TRUE"))) == PycurlTransport


class FakeOsModule:

    def __init__(self, env_val):
        self.env_val = env_val

    def getenv(self, key, default):
        return self.env_val
