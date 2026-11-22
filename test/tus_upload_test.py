import threading
import time
from contextlib import contextmanager
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.parse import (
    parse_qs,
    urlparse,
)

import pytest
import requests

from pulsar.client.staging.down import _allow_collect_failure
from pulsar.client.transport import tus
from pulsar.client.transport.transient import http_status_code

TUS_PATH = "/api/job_files/resumable_upload"


class _TusHandler(BaseHTTPRequestHandler):
    # HTTP/1.1 so the server keeps connections open between requests.
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _record(self):
        state = self.server.state  # type: ignore[attr-defined]
        # self.headers looks names up case-insensitively, as HTTP requires.
        state["requests"].append((self.command, urlparse(self.path).path, self.client_address, self.headers))
        return state

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def _respond(self, status, headers=None):
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        state = self._record()
        body = self._body()
        path = urlparse(self.path).path
        if path == TUS_PATH:
            upload_id = f"upload{len(state['uploads'])}"
            state["uploads"][upload_id] = {
                "length": int(self.headers["Upload-Length"]),
                "data": b"",
            }
            self._respond(201, {"Location": f"{TUS_PATH}/{upload_id}", "Tus-Resumable": "1.0.0"})
        else:
            state["completed"].append(parse_qs(body.decode())["session_id"][0])
            self._respond(200)

    def do_HEAD(self):
        state = self._record()
        if state["head_failures"]:
            self._respond(*state["head_failures"].pop(0))
            return
        upload = state["uploads"][urlparse(self.path).path.rsplit("/", 1)[1]]
        self._respond(200, {
            "Upload-Offset": str(len(upload["data"])),
            "Upload-Length": str(upload["length"]),
            "Tus-Resumable": "1.0.0",
        })

    def do_PATCH(self):
        state = self._record()
        body = self._body()
        # A queued failure for this PATCH, else the persistent one, else success.
        failure = state["patch_failures"].pop(0) if state["patch_failures"] else state["patch_response"]
        if isinstance(failure, tuple):
            self._respond(*failure)
            return
        upload = state["uploads"][urlparse(self.path).path.rsplit("/", 1)[1]]
        if failure != "disconnect":
            upload["data"] += body
        if failure == "accept_then_stall":
            # Hold the response past the client's timeout.
            time.sleep(1)
        if failure in ("disconnect", "accept_then_disconnect"):
            # Drop the connection without a response, as a proxy timing out would.
            self.close_connection = True
            return
        self._respond(204, {"Upload-Offset": str(len(upload["data"])), "Tus-Resumable": "1.0.0"})


@contextmanager
def _tus_server(patch_response=None, patch_failures=(), head_failures=()):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TusHandler)
    server.daemon_threads = True
    state = {
        "requests": [],
        "uploads": {},
        "completed": [],
        "patch_response": patch_response,
        "patch_failures": list(patch_failures),
        "head_failures": list(head_failures),
    }
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/api/jobs/1/files?job_key=k&path=/out.dat", state
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(tus, "PULSAR_TUS_RETRY_DELAY", 0)


def test_tus_upload_reuses_one_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(tus, "PULSAR_TUS_CHUNK_SIZE", 1000)
    content = bytes(range(256)) * 20  # 5120 bytes -> 6 chunks
    path = tmp_path / "out.dat"
    path.write_bytes(content)

    with _tus_server() as (url, state):
        tus.tus_upload_file(url, str(path))

    assert state["uploads"] == {"upload0": {"length": len(content), "data": content}}
    assert state["completed"] == ["upload0"]
    requests_made = state["requests"]
    assert [method for method, _, _, _ in requests_made] == ["POST"] + ["PATCH"] * 6 + ["POST"]
    create_headers = requests_made[0][3]
    assert create_headers["Tus-Resumable"] == "1.0.0"
    assert create_headers["Upload-Length"] == str(len(content))
    for i, (_, _, _, headers) in enumerate(requests_made[1:7]):
        assert headers["Tus-Resumable"] == "1.0.0"
        assert headers["Content-Type"] == "application/offset+octet-stream"
        assert headers["Upload-Offset"] == str(i * 1000)
    client_addresses = {address for _, _, address, _ in requests_made}
    assert len(client_addresses) == 1, f"expected one connection, got {len(client_addresses)}: {client_addresses}"


@pytest.mark.parametrize("failure, resume_offset", [
    ((502,), 1000),
    ((409,), 1000),
    ("disconnect", 1000),
    # The server stored the chunk but the response was lost: don't send it again.
    ("accept_then_disconnect", 2000),
    ("accept_then_stall", 2000),
])
def test_tus_upload_resumes_failed_chunk(tmp_path, monkeypatch, failure, resume_offset):
    monkeypatch.setattr(tus, "PULSAR_TUS_CHUNK_SIZE", 1000)
    monkeypatch.setattr(tus, "PULSAR_TUS_TIMEOUT", 0.2)
    content = bytes(range(256)) * 20
    path = tmp_path / "out.dat"
    path.write_bytes(content)

    with _tus_server(patch_failures=[None, failure]) as (url, state):
        tus.tus_upload_file(url, str(path))

    assert state["uploads"]["upload0"]["data"] == content
    assert state["completed"] == ["upload0"]
    methods = [method for method, _, _, _ in state["requests"]]
    head_index = methods.index("HEAD")
    assert methods[:head_index] == ["POST", "PATCH", "PATCH"]
    assert methods.count("HEAD") == 1
    assert state["requests"][head_index + 1][3]["Upload-Offset"] == str(resume_offset)
    if failure == (502,):
        # An error response leaves the connection open, so it is still reused.
        assert len({address for _, _, address, _ in state["requests"]}) == 1


def test_tus_upload_retry_budget_is_per_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(tus, "PULSAR_TUS_CHUNK_SIZE", 1000)
    monkeypatch.setattr(tus, "PULSAR_TUS_RETRIES", 1)
    content = bytes(range(256)) * 20
    path = tmp_path / "out.dat"
    path.write_bytes(content)

    # Every chunk fails once; one retry each is enough.
    with _tus_server(patch_failures=[(502,), None] * 6) as (url, state):
        tus.tus_upload_file(url, str(path))

    assert state["uploads"]["upload0"]["data"] == content
    assert [method for method, _, _, _ in state["requests"]].count("HEAD") == 6


def test_tus_upload_failed_head_uses_up_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(tus, "PULSAR_TUS_RETRIES", 3)
    path = tmp_path / "out.dat"
    path.write_bytes(b"123456")

    with _tus_server(patch_failures=[(502,)], head_failures=[(502,)] * 10) as (url, state), \
            pytest.raises(requests.HTTPError, match=r"HEAD .* status 502"):
        tus.tus_upload_file(url, str(path))

    assert [method for method, _, _, _ in state["requests"]] == ["POST", "PATCH", "HEAD", "HEAD", "HEAD"]


def test_tus_upload_does_not_retry_client_errors(tmp_path):
    path = tmp_path / "out.dat"
    path.write_bytes(b"123456")

    with _tus_server((403,)) as (url, state), pytest.raises(requests.HTTPError, match="status 403"):
        tus.tus_upload_file(url, str(path))

    assert [method for method, _, _, _ in state["requests"]] == ["POST", "PATCH"]


def test_tus_upload_empty_file_still_creates_upload(tmp_path):
    path = tmp_path / "empty.dat"
    path.write_bytes(b"")

    with _tus_server() as (url, state):
        tus.tus_upload_file(url, str(path))

    assert state["uploads"] == {"upload0": {"length": 0, "data": b""}}
    assert state["completed"] == ["upload0"]
    assert [method for method, _, _, _ in state["requests"]] == ["POST", "POST"]


@pytest.mark.parametrize("patch_response, status, match", [
    ((500,), 500, "status 500"),
    ((204, {"Upload-Offset": "garbage"}), 204, "Upload-Offset 'garbage'"),
    ((204, {"Upload-Offset": "0"}), 204, "Upload-Offset '0'"),
    ((204, {"Upload-Offset": "999"}), 204, "Upload-Offset '999'"),
])
def test_tus_upload_failure_fails_stage_out(tmp_path, monkeypatch, patch_response, status, match):
    monkeypatch.setattr(tus, "PULSAR_TUS_RETRIES", 2)
    path = tmp_path / "out.dat"
    path.write_bytes(b"123456")

    with _tus_server(patch_response) as (url, state), pytest.raises(requests.HTTPError, match=match) as exc_info:
        tus.tus_upload_file(url, str(path))

    assert state["completed"] == []
    # Transient errors are retried, the others are not.
    expected_methods = ["POST", "PATCH", "HEAD", "PATCH", "HEAD", "PATCH"] if status == 500 else ["POST", "PATCH"]
    assert [method for method, _, _, _ in state["requests"]] == expected_methods
    assert http_status_code(exc_info.value) == status
    # Even for a working-directory output, stage-out must fail the job rather
    # than downgrade the failure to a warning.
    assert not _allow_collect_failure("output_workdir", exc_info.value)
