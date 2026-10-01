"""Upload a job's outputs to the targets Galaxy issues for them.

With remote metadata, the job's metadata step writes the outputs Galaxy will import
into the job's object store staging directory, with a manifest: one JSON record per
file, naming it by a path relative to that directory. After the job, Pulsar sends
Galaxy the records (each file's size in place of its path) and uploads each file to
the target Galaxy answers with: a single PUT, or a multipart upload whose parts Pulsar
PUTs and Galaxy then completes. Targets may point straight at Galaxy's object store,
so no storage credentials reach the job. A target URL relative to the targets URL is
resolved against it, as for an HTTP redirect.
"""
import json
import logging
import os
import stat
from functools import partial
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
)
from urllib.parse import urljoin

import requests

from pulsar.client.transport import put_file

if TYPE_CHECKING:
    from pulsar.managers.util.retry import RetryActionExecutor

log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.jsonl"

# A staged file: its path, size and the manifest record describing it to Galaxy.
StagedFile = Tuple[str, int, Dict[str, Any]]


class OutputStagingError(Exception):
    """The staged outputs, or the targets Galaxy issued for them, cannot be uploaded as described."""


def upload_outputs(
    staging_directory: str,
    targets_url: str,
    action_executor: "RetryActionExecutor",
    was_cancelled: Callable[[], Optional[bool]],
) -> None:
    """Upload the files the manifest in ``staging_directory`` lists to the targets Galaxy issues."""
    if os.path.islink(staging_directory):
        raise OutputStagingError("The object store staging directory is a symlink.")
    manifest_path = os.path.join(staging_directory, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        return
    staged = _read_manifest(staging_directory, manifest_path)
    if not staged or was_cancelled():
        return
    files = [{**record, "size": size} for _, size, record in staged]
    targets = action_executor.execute(partial(_request_targets, targets_url, files), "requesting output targets")
    if not isinstance(targets, list) or len(targets) != len(staged):
        raise OutputStagingError("Galaxy did not issue one target per staged output.")
    for (_, size, _), target in zip(staged, targets):
        _validate_target(target, size)
    for (path, size, _), target in zip(staged, targets):
        if was_cancelled():
            log.info("Skipped uploading outputs, job is cancelled")
            return
        _upload(path, size, target, targets_url, action_executor)


def _read_manifest(staging_directory: str, manifest_path: str) -> List[StagedFile]:
    staged = []
    with open(manifest_path) as manifest:
        for number, line in enumerate(manifest, start=1):
            try:
                record = json.loads(line)
            except ValueError as e:
                raise OutputStagingError(f"Line {number} of the output manifest is not JSON.") from e
            if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                raise OutputStagingError(f"Line {number} of the output manifest names no path.")
            path = _staged_file(staging_directory, record.pop("path"))
            staged.append((path, os.lstat(path).st_size, record))
    return staged


def _staged_file(staging_directory: str, relative_path: str) -> str:
    """The regular file ``relative_path`` names inside the staging directory, reached without symlinks.

    Pulsar uploads with its own privileges: a job must not be able to name any other file.
    """
    parts = relative_path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise OutputStagingError(f"Output manifest names a path outside the staging directory: {relative_path!r}")
    path = staging_directory
    mode = 0
    for part in parts:
        path = os.path.join(path, part)
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            raise OutputStagingError(f"Output manifest names a missing file: {relative_path!r}")
        if stat.S_ISLNK(mode):
            raise OutputStagingError(f"Output manifest names a path through a symlink: {relative_path!r}")
    if not stat.S_ISREG(mode):
        raise OutputStagingError(f"Output manifest names something other than a file: {relative_path!r}")
    return path


def _request_targets(targets_url: str, files: List[Dict[str, Any]]) -> Any:
    with requests.post(targets_url, json={"files": files}) as response:
        response.raise_for_status()
        return response.json().get("targets")


def _validate_target(target: Any, size: int) -> None:
    target_type = target.get("type") if isinstance(target, dict) else None
    if target_type == "put":
        return
    if target_type != "multipart":
        raise OutputStagingError(f"Galaxy issued an unknown output target type: {target_type!r}")
    covered = 0
    for part in sorted(target["parts"], key=lambda part: part["offset"]):
        if part["offset"] != covered or part["size"] <= 0:
            raise OutputStagingError("The parts of a multipart output target overlap or leave gaps.")
        covered += part["size"]
    if covered != size:
        raise OutputStagingError("The parts of a multipart output target do not cover the output.")


def _upload(
    path: str, size: int, target: Dict[str, Any], targets_url: str, action_executor: "RetryActionExecutor"
) -> None:
    if target["type"] == "put":
        url = urljoin(targets_url, target["url"])
        upload = partial(put_file, url, path, size=size, headers=target.get("headers"))
        action_executor.execute(upload, f"uploading {path}")
        return
    completed = []
    for part in target["parts"]:
        url = urljoin(targets_url, part["url"])
        upload_part = partial(put_file, url, path, offset=part["offset"], size=part["size"], headers=part.get("headers"))
        response_headers = action_executor.execute(upload_part, f"uploading part {part['part_number']} of {path}")
        completed.append({"part_number": part["part_number"], "etag": response_headers.get("etag")})
    complete_url = urljoin(targets_url, target["complete_url"])
    action_executor.execute(partial(_complete, complete_url, completed), f"completing the upload of {path}")


def _complete(complete_url: str, parts: List[Dict[str, Any]]) -> None:
    with requests.post(complete_url, json={"parts": parts}) as response:
        response.raise_for_status()
