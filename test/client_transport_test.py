import contextlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import mock
from uuid import uuid4

import pytest
import requests as requests_module
from simplejobfiles.app import JobFilesApp
from webtest import TestApp

from pulsar.client.exceptions import PulsarClientTransportError
from pulsar.client.transport import (
    curl as curl_transport,
    get_transport,
    requests as requests_transport,
)
from pulsar.client.transport.curl import (
    get_file,
    post_file,
    PycurlTransport,
)
from pulsar.client.transport.requests import (
    get_file as requests_get_file,
    post_file as requests_post_file,
)
from pulsar.client.transport.standard import UrllibTransport
from pulsar.client.transport.transient import is_transient_http_error
from pulsar.client.transport.tus import find_tus_endpoint
from pulsar.managers.util.retry import RetryActionExecutor
from .test_utils import (
    files_server,
    server_for_test_app,
    skip_unless_module,
    temp_directory,
)


def test_urllib_transports():
    _test_transport(UrllibTransport())


@skip_unless_module("pycurl")
def test_pycurl_transport():
    _test_transport(PycurlTransport())


def test_curl_object_is_closed():
    curl = mock.Mock()
    with mock.patch.object(curl_transport, "_new_curl_object", return_value=curl):
        with curl_transport._curl_object_for_url("https://example.org") as opened:
            assert opened is curl

    curl.close.assert_called_once_with()


def test_curl_object_is_closed_on_error():
    curl = mock.Mock()
    with mock.patch.object(curl_transport, "_new_curl_object", return_value=curl):
        try:
            with curl_transport._curl_object_for_url("https://example.org"):
                raise RuntimeError("test error")
        except RuntimeError:
            pass

    curl.close.assert_called_once_with()


def test_requests_download_response_is_closed(tmp_path):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"downloaded"]
    with mock.patch.object(requests_transport.requests, "get", return_value=response):
        requests_transport.get_file("https://example.org", tmp_path / "output")

    response.__exit__.assert_called_once()


def test_requests_download_response_is_closed_on_error(tmp_path):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.raise_for_status.side_effect = requests_module.HTTPError("test error")
    with mock.patch.object(requests_transport.requests, "get", return_value=response):
        try:
            requests_transport.get_file("https://example.org", tmp_path / "output")
        except requests_module.HTTPError:
            pass

    response.__exit__.assert_called_once()


@contextlib.contextmanager
def path_to_get_fixture(directory):
    path = Path(directory, f"test_for_GET_{uuid4()!s}")
    path.write_text(" Test123 ")
    path.chmod(0o755)
    yield path
    os.remove(path)


def _test_transport(transport):
    with files_server() as (server, directory):
        server_url = server.application_url
        with path_to_get_fixture(directory) as path:
            request_url = f"{server_url}?path={path}"

            # Testing simple get
            response = transport.execute(request_url, data=None)
            assert response.find(b"Test123") >= 0

        with path_to_get_fixture(directory) as path:
            request_url = f"{server_url}?path={path}"

            # Testing writing to output file
            temp_file = NamedTemporaryFile(delete=True)
            output_path = temp_file.name
            temp_file.close()
            response = transport.execute(request_url, data=None, output_path=output_path)
            assert open(output_path).read().find("Test123") >= 0


@skip_unless_module("pycurl")
def test_curl_put_get():
    with files_server() as (server, directory), path_to_get_fixture(directory) as path:
        server_url = server.application_url
        path = Path(directory, f"test_for_curl_io_{uuid4()!s}")
        request_url = f"{server_url}?path={path!s}"

        input = os.path.join(directory, f"test_for_curl_io_input_{uuid4()!s}")
        output = os.path.join(directory, f"test_for_curl_io_output_{uuid4()!s}")
        open(input, "w").write("helloworld")

        post_file(request_url, input)
        get_file(request_url, output)
        assert open(output).read() == "helloworld"


def test_urllib_status_code():
    """The urllib transport must surface the HTTP status code on the raised
    PulsarClientTransportError so retry classifiers can read it."""
    with files_server() as (server, directory):
        server_url = server.application_url
        absent_path = os.path.join(directory, f"test_for_GET_absent_{uuid4()!s}")
        request_url = f"{server_url}?path={absent_path}"
        try:
            UrllibTransport().execute(request_url, data=None)
        except PulsarClientTransportError as exc:
            assert isinstance(exc.transport_code, int) and exc.transport_code >= 400, (
                f"transport_code should hold the HTTP status, got {exc.transport_code!r}"
            )
        else:
            raise AssertionError("urllib transport did not raise on missing file")


def test_curl_status_code():
    with files_server() as (server, directory):
        server_url = server.application_url
        path = os.path.join(directory, f"test_for_GET_absent_{uuid4()!s}")
        request_url = f"{server_url}?path={path}"
        try:
            get_file(request_url, os.path.join(directory, "test"))
        except PulsarClientTransportError as exc:
            assert isinstance(exc.transport_code, int) and exc.transport_code >= 400, (
                f"transport_code should hold the HTTP status, got {exc.transport_code!r}"
            )
        else:
            raise AssertionError("curl get_file did not raise on missing file")

        post_request_url = "{}?path={}".format(server_url, "/usr/bin/cow")
        try:
            post_file(post_request_url, os.path.join(directory, "test"))
        except PulsarClientTransportError as exc:
            assert isinstance(exc.transport_code, int) and exc.transport_code >= 400, (
                f"transport_code should hold the HTTP status, got {exc.transport_code!r}"
            )
        else:
            raise AssertionError("curl post_file did not raise on error response")


class _FlakyApp:
    """WSGI middleware that returns ``status`` for the first ``fail_count``
    requests, then delegates to the wrapped app."""

    def __init__(self, app, fail_count, status="502 Bad Gateway"):
        self.app = app
        self.fail_count = fail_count
        self.status = status
        self.attempts = 0

    def __call__(self, environ, start_response):
        self.attempts += 1
        if self.attempts <= self.fail_count:
            start_response(self.status, [("Content-Type", "text/html")])
            return [b"<html><body><h1>" + self.status.encode() + b"</h1></body></html>"]
        return self.app(environ, start_response)


def test_requests_status_code():
    with files_server() as (server, directory):
        server_url = server.application_url
        absent_path = os.path.join(directory, f"test_for_GET_absent_{uuid4()!s}")
        request_url = f"{server_url}?path={absent_path}"
        # Use a uuid in the output name: in CI, `directory` is the shared
        # /tmp served by the simplejobfiles container, so a fixed name like
        # "test" can collide with leftovers from prior runs and break the
        # "no file written on error" assertion below.
        output_path = os.path.join(directory, f"out_{uuid4()}")
        try:
            requests_get_file(request_url, output_path)
        except requests_module.HTTPError:
            pass
        else:
            raise AssertionError("requests get_file did not raise on missing file")
        assert not os.path.exists(output_path), "requests get_file created file on error response"


@skip_unless_module("requests_toolbelt")
def test_requests_post_status_code():
    with files_server() as (server, directory):
        server_url = server.application_url
        # /usr/bin/cow is read-only territory — the server will reject the upload.
        post_request_url = "{}?path={}".format(server_url, "/usr/bin/cow")
        source_file = os.path.join(directory, f"src_{uuid4()}")
        Path(source_file).write_text("payload")
        try:
            requests_post_file(post_request_url, source_file)
        except requests_module.HTTPError:
            pass
        else:
            raise AssertionError("requests post_file did not raise on error response")


def test_requests_transient_failure_recovers_with_retry():
    """Issue #443: a transient nginx 502 must surface as an exception so the
    surrounding RetryActionExecutor can retry and eventually succeed."""
    fail_count = 2
    with temp_directory() as directory:
        served = Path(directory) / f"served_{uuid4()}"
        served.write_text("recovered_content")

        flaky = _FlakyApp(JobFilesApp(directory), fail_count=fail_count)
        with server_for_test_app(TestApp(flaky)) as server:
            request_url = f"{server.application_url}?path={served!s}"
            output_path = os.path.join(directory, "downloaded")

            executor = RetryActionExecutor(
                max_retries=fail_count + 1,
                interval_start=0.01,
                interval_step=0.01,
                interval_max=0.05,
            )
            executor.execute(
                lambda: requests_get_file(request_url, output_path),
                "transient-test",
            )

            assert flaky.attempts == fail_count + 1
            assert open(output_path).read() == "recovered_content"


def test_requests_persistent_failure_exhausts_retries():
    """If 502s never resolve, the retry layer must give up with HTTPError —
    not a silent success leaving an HTML-corrupted file behind."""
    max_retries = 2
    with temp_directory() as directory:
        served = Path(directory) / f"served_{uuid4()}"
        served.write_text("never_served")

        flaky = _FlakyApp(JobFilesApp(directory), fail_count=10)
        with server_for_test_app(TestApp(flaky)) as server:
            request_url = f"{server.application_url}?path={served!s}"
            output_path = os.path.join(directory, "downloaded")

            executor = RetryActionExecutor(
                max_retries=max_retries,
                interval_start=0.01,
                interval_step=0.01,
                interval_max=0.05,
            )
            try:
                executor.execute(
                    lambda: requests_get_file(request_url, output_path),
                    "exhaust-test",
                )
            except requests_module.HTTPError:
                pass
            else:
                raise AssertionError("HTTPError should have propagated after retry exhaustion")

            assert flaky.attempts == max_retries + 1
            assert not os.path.exists(output_path), "no file should have been written"


def test_permanent_4xx_fails_fast_under_executor():
    """A 404 must NOT be retried — retrying client errors wastes time and
    delays job failure. The executor's should_retry predicate (default
    is_transient_http_error) should let the HTTPError bubble on first hit."""
    max_retries = 5
    with temp_directory() as directory:
        flaky = _FlakyApp(JobFilesApp(directory), fail_count=10, status="404 Not Found")
        with server_for_test_app(TestApp(flaky)) as server:
            request_url = "{}?path={}".format(server.application_url, str(Path(directory) / "x"))
            output_path = os.path.join(directory, "downloaded")

            executor = RetryActionExecutor(
                max_retries=max_retries,
                interval_start=0.01,
                interval_step=0.01,
                interval_max=0.05,
                should_retry=is_transient_http_error,
            )
            try:
                executor.execute(
                    lambda: requests_get_file(request_url, output_path),
                    "permanent-404-test",
                )
            except requests_module.HTTPError:
                pass
            else:
                raise AssertionError("404 HTTPError should have propagated immediately")

            assert flaky.attempts == 1, (
                f"4xx must not be retried, but the server saw {flaky.attempts} attempts"
            )


@skip_unless_module("pycurl")
def test_curl_problems():
    with files_server() as (server, directory):
        server_url = server.application_url
        path = os.path.join(directory, f"test_for_GET_invalidinput_{uuid4()!s}")
        request_url = f"{server_url}?path={path}"
        exception_raised = False
        try:
            # Valid destination but the file to post doesn't exist.
            post_file(request_url, os.path.join(directory, f"test-{uuid4()!s}"))
        except Exception:
            exception_raised = True
        assert exception_raised


def test_find_tus_endpoint():
    galaxy_endpoint = "http://subdomain.galaxy.org/prefix/api/jobs/1231sdfsq23e/files?job_key=34"
    tus_endpoint = find_tus_endpoint(galaxy_endpoint)
    assert tus_endpoint == "http://subdomain.galaxy.org/prefix/api/job_files/resumable_upload?job_key=34"


def test_get_transport():
    assert type(get_transport(None, FakeOsModule("1"))) is PycurlTransport
    assert type(get_transport(None, FakeOsModule("TRUE"))) is PycurlTransport
    assert type(get_transport(None, FakeOsModule("0"))) is UrllibTransport
    assert type(get_transport('urllib', FakeOsModule("TRUE"))) is UrllibTransport
    assert type(get_transport('curl', FakeOsModule("TRUE"))) is PycurlTransport


class FakeOsModule:

    def __init__(self, env_val):
        self.env_val = env_val

    def getenv(self, key, default):
        return self.env_val


@skip_unless_module("pycurl")
def test_curl_post_file_converts_connection_error():
    """A connection-level pycurl failure in post_file must surface as a
    structured PulsarClientTransportError, not a raw pycurl.error. Callers
    classify transport failures by that type; a bare pycurl.error is invisible
    to them."""
    import pycurl

    curl = mock.Mock()
    curl.perform.side_effect = pycurl.error(pycurl.E_COULDNT_CONNECT, "Couldn't connect to server")
    with NamedTemporaryFile() as f:
        with mock.patch.object(curl_transport, "_new_curl_object", return_value=curl):
            with pytest.raises(PulsarClientTransportError) as exc_info:
                curl_transport.post_file("http://galaxy.test/api/jobs/1/files", f.name)
    assert exc_info.value.code == PulsarClientTransportError.CONNECTION_REFUSED
    assert exc_info.value.transport_code == pycurl.E_COULDNT_CONNECT


@skip_unless_module("pycurl")
def test_curl_get_file_converts_connection_error(tmp_path):
    """Same conversion on the download half of staging."""
    import pycurl

    curl = mock.Mock()
    curl.perform.side_effect = pycurl.error(pycurl.E_OPERATION_TIMEDOUT, "Operation timed out")
    with mock.patch.object(curl_transport, "_new_curl_object", return_value=curl):
        with mock.patch.object(curl_transport, "get_size", return_value=-1):
            with pytest.raises(PulsarClientTransportError) as exc_info:
                curl_transport.get_file("http://galaxy.test/files/out.dat", str(tmp_path / "out.dat"))
    assert exc_info.value.code == PulsarClientTransportError.TIMEOUT


def test_post_file_missing_file_raises_file_not_found():
    """A missing local file is FileNotFoundError, matching the requests transport
    and the builtin. Staging policy keys on FileNotFoundError to decide what
    stays recoverable, so a bare Exception here is not interchangeable."""
    with pytest.raises(FileNotFoundError):
        curl_transport.post_file("http://galaxy.test/api/jobs/1/files", "/does/not/exist")
