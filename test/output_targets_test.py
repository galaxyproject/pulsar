"""Uploading a job's outputs to targets Galaxy issues (remote object store staging).

A fake Galaxy issues the targets and stands in for the object store they point at:
single PUTs, or multipart uploads completed through Galaxy.
"""
import json
import os
from typing import (
    Any,
    Dict,
    List,
    Optional,
)
from urllib.parse import parse_qs

import pytest
from webtest import TestApp

from pulsar.managers.base import JobDirectory
from pulsar.managers.staging.output_targets import (
    MANIFEST_NAME,
    OutputStagingError,
    upload_outputs,
)
from pulsar.managers.staging.post import postprocess
from pulsar.managers.util.retry import RetryActionExecutor
from .test_utils import (
    server_for_test_app,
    temp_directory,
)


class FakeGalaxy:
    """Issues output targets and receives the uploads made to them."""

    def __init__(
        self,
        part_size: Optional[int] = None,
        failing_puts: int = 0,
        put_status: str = "502 Bad Gateway",
        prefix: str = "",
        relative_urls: bool = False,
    ):
        self.part_size = part_size
        # Galaxy may answer with URLs relative to the targets URL for uploads it handles itself.
        self.prefix = prefix
        self.relative_urls = relative_urls
        self.failing_puts = failing_puts
        self.put_status = put_status
        self.targets_requests: List[Dict[str, Any]] = []
        self.objects: Dict[str, bytes] = {}
        self.parts: Dict[str, Dict[int, bytes]] = {}
        self.completions: Dict[str, List[Dict[str, Any]]] = {}
        self.put_environs: List[Dict[str, Any]] = []
        self.targets_override: Optional[List[Dict[str, Any]]] = None

    def __call__(self, environ, start_response):
        method, path = environ["REQUEST_METHOD"], environ["PATH_INFO"]
        length = environ.get("CONTENT_LENGTH")
        body = environ["wsgi.input"].read(int(length)) if length else b""
        base = "" if self.relative_urls else f"http://{environ['HTTP_HOST']}{self.prefix}/"
        if not path.startswith(self.prefix):
            return _respond(start_response, "404 Not Found", b"")
        path = path[len(self.prefix):]
        if method == "POST" and path == "/targets":
            request = json.loads(body)
            self.targets_requests.append(request)
            targets = self.targets_override
            if targets is None:
                targets = [self._target(base, str(i), f["size"]) for i, f in enumerate(request["files"])]
            return _respond(start_response, "200 OK", json.dumps({"targets": targets}).encode(), "application/json")
        if method == "PUT" and path.startswith("/objects/"):
            self.put_environs.append({k: v for k, v in environ.items() if k.startswith(("HTTP_", "CONTENT_"))})
            if self.failing_puts:
                self.failing_puts -= 1
                return _respond(start_response, self.put_status, b"no")
            key = path[len("/objects/"):]
            part = parse_qs(environ.get("QUERY_STRING", "")).get("part")
            if part:
                part_number = int(part[0])
                self.parts.setdefault(key, {})[part_number] = body
                etag = f'"etag-{key}-{part_number}"'
            else:
                self.objects[key] = body
                etag = f'"etag-{key}"'
            return _respond(start_response, "200 OK", b"", headers=[("ETag", etag)])
        if method == "POST" and path.startswith("/complete/"):
            key = path[len("/complete/"):]
            self.completions[key] = json.loads(body)["parts"]
            parts = self.parts[key]
            self.objects[key] = b"".join(parts[n] for n in sorted(parts))
            return _respond(start_response, "200 OK", b"{}", "application/json")
        return _respond(start_response, "404 Not Found", b"")

    def _target(self, base: str, key: str, size: int) -> Dict[str, Any]:
        if self.part_size is None:
            return {"type": "put", "url": f"{base}objects/{key}", "headers": {"x-amz-meta-key": key}}
        parts = []
        for number, offset in enumerate(range(0, size, self.part_size), start=1):
            parts.append({
                "part_number": number,
                "url": f"{base}objects/{key}?part={number}",
                "offset": offset,
                "size": min(self.part_size, size - offset),
            })
        return {"type": "multipart", "parts": parts, "complete_url": f"{base}complete/{key}"}


def _respond(start_response, status, body, content_type="text/plain", headers=None):
    start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body)))] + (headers or []))
    return [body]


def _stage(staging_directory: str, files: Dict[str, bytes], records: Optional[List[Dict[str, Any]]] = None) -> None:
    """Write files into the staging directory and a manifest naming them, as the job's metadata step does."""
    for name, content in files.items():
        path = os.path.join(staging_directory, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
    if records is None:
        records = [{"kind": "dataset", "uuid": f"uuid-{i}", "path": name} for i, name in enumerate(files)]
    _write_manifest(staging_directory, records)


def _write_manifest(staging_directory: str, records: List[Dict[str, Any]]) -> None:
    os.makedirs(staging_directory, exist_ok=True)
    with open(os.path.join(staging_directory, MANIFEST_NAME), "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def _executor(**kwds) -> RetryActionExecutor:
    return RetryActionExecutor(interval_start=0.01, interval_step=0.01, interval_max=0.05, **kwds)


def _never_cancelled() -> bool:
    return False


@pytest.fixture
def staging_directory():
    with temp_directory() as directory:
        yield os.path.join(directory, "object_store_staging")


def _serve(galaxy: FakeGalaxy):
    return server_for_test_app(TestApp(galaxy))


def test_each_staged_file_is_uploaded_to_its_target(staging_directory):
    files = {"dataset_a.dat": b"first output\n", "_metadata_files/0/metadata_1.dat": b"index"}
    _stage(staging_directory, files)
    galaxy = FakeGalaxy()
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
    assert galaxy.objects == {"0": files["dataset_a.dat"], "1": files["_metadata_files/0/metadata_1.dat"]}


def test_galaxy_is_asked_for_targets_once_with_each_records_fields_and_size(staging_directory):
    _stage(
        staging_directory,
        {"a.dat": b"12345"},
        records=[{"kind": "extra_file", "uuid": "u1", "extra_dir": "dataset_u1_files", "alt_name": "x", "path": "a.dat"}],
    )
    galaxy = FakeGalaxy()
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
    assert galaxy.targets_requests == [
        {"files": [{"kind": "extra_file", "uuid": "u1", "extra_dir": "dataset_u1_files", "alt_name": "x", "size": 5}]}
    ]


def test_put_sends_the_targets_headers_and_a_content_length(staging_directory):
    # Presigned object store PUTs need an exact length and refuse chunked uploads.
    _stage(staging_directory, {"a.dat": b"12345"})
    galaxy = FakeGalaxy()
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
    (put,) = galaxy.put_environs
    assert put["CONTENT_LENGTH"] == "5"
    assert "HTTP_TRANSFER_ENCODING" not in put
    assert put["HTTP_X_AMZ_META_KEY"] == "0"


def test_multipart_target_uploads_each_part_and_completes_with_their_etags(staging_directory):
    content = b"0123456789"
    _stage(staging_directory, {"big.dat": content})
    galaxy = FakeGalaxy(part_size=4)
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
    assert galaxy.parts["0"] == {1: b"0123", 2: b"4567", 3: b"89"}
    assert galaxy.completions["0"] == [
        {"part_number": 1, "etag": '"etag-0-1"'},
        {"part_number": 2, "etag": '"etag-0-2"'},
        {"part_number": 3, "etag": '"etag-0-3"'},
    ]
    assert galaxy.objects["0"] == content


@pytest.mark.parametrize("part_size", [None, 4])
def test_relative_target_urls_resolve_against_the_targets_url(staging_directory, part_size):
    content = b"0123456789"
    _stage(staging_directory, {"a.dat": content})
    galaxy = FakeGalaxy(part_size=part_size, prefix="/api/jobs/1/staging/outputs", relative_urls=True)
    with _serve(galaxy) as server:
        targets_url = f"{server.application_url}/api/jobs/1/staging/outputs/targets?sig=x"
        upload_outputs(staging_directory, targets_url, _executor(), _never_cancelled)
    assert galaxy.objects == {"0": content}


def test_failed_upload_is_retried(staging_directory):
    _stage(staging_directory, {"a.dat": b"retried"})
    galaxy = FakeGalaxy(failing_puts=1)
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(max_retries=2), _never_cancelled)
    assert galaxy.objects == {"0": b"retried"}


def test_failed_upload_raises_once_retries_are_exhausted(staging_directory):
    _stage(staging_directory, {"a.dat": b"lost"})
    galaxy = FakeGalaxy(failing_puts=5)
    with _serve(galaxy) as server:
        with pytest.raises(Exception):
            upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(max_retries=1), _never_cancelled)
    assert galaxy.objects == {}


def test_nothing_is_uploaded_without_a_manifest(staging_directory):
    galaxy = FakeGalaxy()
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
    assert galaxy.targets_requests == []


def test_nothing_is_uploaded_for_a_cancelled_job(staging_directory):
    _stage(staging_directory, {"a.dat": b"x"})
    galaxy = FakeGalaxy()
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), lambda: True)
    assert galaxy.targets_requests == []
    assert galaxy.objects == {}


def _escaping_symlink(staging_directory, outside):
    os.makedirs(staging_directory, exist_ok=True)
    os.symlink(os.path.join(outside, "secret"), os.path.join(staging_directory, "linked.dat"))
    return "linked.dat"


def _symlinked_directory(staging_directory, outside):
    os.makedirs(staging_directory, exist_ok=True)
    os.symlink(outside, os.path.join(staging_directory, "sub"))
    return "sub/secret"


def _directory(staging_directory, outside):
    os.makedirs(os.path.join(staging_directory, "a_directory"))
    return "a_directory"


def _missing(staging_directory, outside):
    return "never_written.dat"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        lambda staging, outside: "../secret",
        lambda staging, outside: os.path.join(outside, "secret"),
        _escaping_symlink,
        _symlinked_directory,
        _directory,
        _missing,
    ],
    ids=["parent", "absolute", "symlink", "symlinked_directory", "directory", "missing"],
)
def test_manifest_path_that_is_not_a_file_inside_the_staging_directory_is_refused(staging_directory, unsafe_path):
    # Pulsar uploads with its own privileges, so the job must not be able to name any other file.
    with temp_directory() as outside:
        with open(os.path.join(outside, "secret"), "wb") as f:
            f.write(b"pulsar's secret")
        _stage(staging_directory, {"ok.dat": b"fine"})
        path = unsafe_path(staging_directory, outside)
        _write_manifest(staging_directory, [{"kind": "dataset", "path": "ok.dat"}, {"kind": "dataset", "path": path}])
        galaxy = FakeGalaxy()
        with _serve(galaxy) as server:
            with pytest.raises(OutputStagingError):
                upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
        assert galaxy.targets_requests == []


def test_staging_directory_that_is_a_symlink_is_refused(staging_directory):
    with temp_directory() as outside:
        _stage(outside, {"secret": b"pulsar's secret"})
        os.symlink(outside, staging_directory)
        galaxy = FakeGalaxy()
        with _serve(galaxy) as server:
            with pytest.raises(OutputStagingError):
                upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
        assert galaxy.targets_requests == []


@pytest.mark.parametrize(
    "line", ["not json", '{"kind": "dataset"}', '["a.dat"]', ""], ids=["not_json", "no_path", "not_an_object", "blank"]
)
def test_malformed_manifest_line_is_refused(staging_directory, line):
    _stage(staging_directory, {"a.dat": b"x"})
    with open(os.path.join(staging_directory, MANIFEST_NAME), "a") as f:
        f.write(line + "\n")
    with pytest.raises(OutputStagingError):
        upload_outputs(staging_directory, "http://unused.example/targets", _executor(), _never_cancelled)


def test_uploads_stop_once_the_job_is_cancelled(staging_directory):
    _stage(staging_directory, {"a.dat": b"first", "b.dat": b"second"})
    answers = iter([False, False, True])  # before asking for targets, before each upload
    galaxy = FakeGalaxy()
    with _serve(galaxy) as server:
        upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), lambda: next(answers))
    assert galaxy.objects == {"0": b"first"}


def test_targets_that_do_not_match_the_files_are_refused(staging_directory):
    _stage(staging_directory, {"a.dat": b"x", "b.dat": b"y"})
    galaxy = FakeGalaxy()
    galaxy.targets_override = [{"type": "put", "url": "http://unused.example/objects/0"}]
    with _serve(galaxy) as server:
        with pytest.raises(OutputStagingError):
            upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)
    assert galaxy.objects == {}


@pytest.mark.parametrize(
    "parts",
    [
        [{"part_number": 1, "offset": 0, "size": 4}],
        [{"part_number": 1, "offset": 0, "size": 4}, {"part_number": 2, "offset": 5, "size": 5}],
        [{"part_number": 1, "offset": 0, "size": 6}, {"part_number": 2, "offset": 4, "size": 6}],
    ],
    ids=["short", "gap", "overlap"],
)
def test_multipart_target_whose_parts_do_not_cover_the_file_is_refused(staging_directory, parts):
    _stage(staging_directory, {"big.dat": b"0123456789"})
    galaxy = FakeGalaxy()
    galaxy.targets_override = [{
        "type": "multipart",
        "parts": [{**part, "url": "http://unused.example/objects/0"} for part in parts],
        "complete_url": "http://unused.example/complete/0",
    }]
    with _serve(galaxy) as server:
        with pytest.raises(OutputStagingError):
            upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)


def test_unknown_target_type_is_refused(staging_directory):
    _stage(staging_directory, {"a.dat": b"x"})
    galaxy = FakeGalaxy()
    galaxy.targets_override = [{"type": "carrier_pigeon", "url": "http://unused.example/objects/0"}]
    with _serve(galaxy) as server:
        with pytest.raises(OutputStagingError):
            upload_outputs(staging_directory, f"{server.application_url}/targets", _executor(), _never_cancelled)


def _job_directory(root: str, targets_url: Optional[str]) -> JobDirectory:
    job_directory = JobDirectory(root, "1")
    job_directory.setup()
    remote_staging = {"output_targets_url": targets_url} if targets_url else {}
    job_directory.store_metadata("launch_config", {"remote_staging": remote_staging})
    return job_directory


def test_postprocess_uploads_outputs_when_galaxy_issued_a_targets_url():
    galaxy = FakeGalaxy()
    with temp_directory() as root, _serve(galaxy) as server:
        job_directory = _job_directory(root, f"{server.application_url}/targets")
        _stage(job_directory.object_store_staging_directory(), {"a.dat": b"output"})
        assert postprocess(job_directory, _executor(), _never_cancelled)
    assert galaxy.objects == {"0": b"output"}


def test_postprocess_reports_failure_when_outputs_cannot_be_uploaded():
    galaxy = FakeGalaxy(failing_puts=5, put_status="403 Forbidden")
    with temp_directory() as root, _serve(galaxy) as server:
        job_directory = _job_directory(root, f"{server.application_url}/targets")
        _stage(job_directory.object_store_staging_directory(), {"a.dat": b"output"})
        assert not postprocess(job_directory, _executor(), _never_cancelled)


def test_postprocess_leaves_staged_files_alone_without_a_targets_url():
    with temp_directory() as root:
        job_directory = _job_directory(root, None)
        _stage(job_directory.object_store_staging_directory(), {"a.dat": b"output"})
        assert postprocess(job_directory, _executor(), _never_cancelled)
