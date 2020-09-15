import os
from tempfile import NamedTemporaryFile

from pulsar.client.transport.standard import UrllibTransport
from pulsar.client.transport.curl import PycurlTransport
from pulsar.client.transport.curl import post_file
from pulsar.client.transport.curl import get_file
from pulsar.client.transport import get_transport

from .test_utils import files_server
from .test_utils import skip_unless_module


def test_urllib_transports():
    _test_transport(UrllibTransport())


@skip_unless_module("pycurl")
def test_pycurl_transport():
    _test_transport(PycurlTransport())


def _test_transport(transport):
    with files_server(allow_multiple_downloads=True) as (server, directory):
        path = os.path.join(directory, "test_for_GET")
        open(path, "w").write(" Test123 ")

        server_url = server.application_url
        request_url = u"%s?path=%s" % (server_url, path)

        # Testing simple get
        response = transport.execute(request_url, data=None)
        assert response.find(b"Test123") >= 0

        # Testing writing to output file
        temp_file = NamedTemporaryFile(delete=True)
        output_path = temp_file.name
        temp_file.close()
        response = transport.execute(request_url, data=None, output_path=output_path)
        assert open(output_path, 'r').read().find("Test123") >= 0


@skip_unless_module("pycurl")
def test_curl_put_get():
    with files_server() as (server, directory):
        server_url = server.application_url
        path = os.path.join(directory, "test_for_GET")
        request_url = u"%s?path=%s" % (server_url, path)

        input = os.path.join(directory, "input")
        output = os.path.join(directory, "output")
        open(input, "w").write(u"helloworld")

        post_file(request_url, input)
        get_file(request_url, output)
        assert open(output, "r").read() == u"helloworld"


def test_curl_status_code():
    with files_server() as (server, directory):
        server_url = server.application_url
        path = os.path.join(directory, "test_for_GET")
        request_url = u"%s?path=%s" % (server_url, path)
        # Verify curl doesn't just silently swallow errors.
        exception_raised = False
        try:
            get_file(request_url, os.path.join(directory, "test"))
        except Exception:
            exception_raised = True
        assert exception_raised

        post_request_url = u"%s?path=%s" % (server_url, "/usr/bin/cow")
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
        path = os.path.join(directory, "test_for_GET")
        request_url = u"%s?path=%s" % (server_url, path)
        exception_raised = False
        try:
            # Valid destination but the file to post doesn't exist.
            post_file(request_url, os.path.join(directory, "test"))
        except Exception:
            exception_raised = True
        assert exception_raised


def test_get_transport():
    assert type(get_transport(None, FakeOsModule("1"))) == PycurlTransport
    assert type(get_transport(None, FakeOsModule("TRUE"))) == PycurlTransport
    assert type(get_transport(None, FakeOsModule("0"))) == UrllibTransport
    assert type(get_transport('urllib', FakeOsModule("TRUE"))) == UrllibTransport
    assert type(get_transport('curl', FakeOsModule("TRUE"))) == PycurlTransport


class FakeOsModule(object):

    def __init__(self, env_val):
        self.env_val = env_val

    def getenv(self, key, default):
        return self.env_val
