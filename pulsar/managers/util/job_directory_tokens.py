"""Substitution of job-directory tokens in command lines and staged files.

A Galaxy destination that computes paths on the client (``jobs_directory``
set, ``LocalSetupHandler``) has to name the remote staging root before it has
talked to Pulsar. ``__PULSAR_JOBS_DIRECTORY__`` stands in for it, so the
cluster admin and the Galaxy admin need not agree on an installation path -
see ``docs/files/job_conf_sample_mq_rsync.yml``. ``__PULSAR_JOB_DIRECTORY__``
is the per-job directory beneath it, used by the cvmfsexec container-image
rewrite because it survives ``shlex.quote`` where a shell variable would not.

Both are replaced server-side, where the real paths are known.
"""

import logging
import os
from typing import (
    List,
    Optional,
)

log = logging.getLogger(__name__)

JOBS_DIRECTORY_TOKEN = "__PULSAR_JOBS_DIRECTORY__"
JOB_DIRECTORY_TOKEN = "__PULSAR_JOB_DIRECTORY__"

_TOKEN_BYTES = tuple(
    token.encode("utf-8") for token in (JOBS_DIRECTORY_TOKEN, JOB_DIRECTORY_TOKEN)
)


def substitute_tokens(
    text: str, job_directory: str, jobs_directory: Optional[str] = None
) -> str:
    """Replace both job-directory tokens in ``text``.

    ``jobs_directory`` defaults to the parent of ``job_directory``.
    """
    if jobs_directory is None:
        jobs_directory = os.path.abspath(os.path.join(job_directory, os.pardir))
    text = text.replace(JOBS_DIRECTORY_TOKEN, jobs_directory)
    return text.replace(JOB_DIRECTORY_TOKEN, job_directory)


def substitute_tokens_in_directory(
    directory: str, job_directory: str, jobs_directory: Optional[str] = None
) -> List[str]:
    """Rewrite every file under ``directory`` that carries a token.

    Returns the paths actually rewritten. Files are opened in binary and
    scanned for the token bytes first, so the common case - no tokens
    anywhere - costs one read per file and no decode. Files that hold a
    token but are not UTF-8 are left alone: metadata directories carry
    dataset blobs beside their JSON.

    Rewrites are in place so the file keeps its mode; ``tool_script.sh``
    is staged executable.
    """
    if not os.path.isdir(directory):
        return []
    rewritten = []
    for dirpath, _, filenames in os.walk(directory):
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
            except OSError:
                log.warning("Could not read staged file %s for token substitution", path)
                continue
            if not any(token in raw for token in _TOKEN_BYTES):
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                log.warning(
                    "Staged file %s contains a Pulsar job-directory token but is not "
                    "UTF-8; leaving it unmodified.",
                    path,
                )
                continue
            substituted = substitute_tokens(text, job_directory, jobs_directory)
            if substituted == text:
                continue
            with open(path, "w") as fh:
                fh.write(substituted)
            rewritten.append(path)
    return rewritten


def substitute_tokens_in_staged_files(job_directory) -> List[str]:
    """Substitute tokens in the staged files whose *contents* can carry them.

    The client rewrites config-file contents with remote paths
    (``pulsar/client/staging/up.py``) and ships the metadata directory
    byte-for-byte, so both can arrive holding a token. Inputs, outputs and
    the working directory hold job data rather than client-computed paths.
    """
    job_path = os.path.abspath(job_directory.path)
    jobs_path = os.path.abspath(os.path.join(job_path, os.pardir))
    rewritten: List[str] = []
    for directory in (
        job_directory.configs_directory(),
        job_directory.metadata_directory(),
    ):
        rewritten.extend(substitute_tokens_in_directory(directory, job_path, jobs_path))
    return rewritten


__all__ = (
    "JOBS_DIRECTORY_TOKEN",
    "JOB_DIRECTORY_TOKEN",
    "substitute_tokens",
    "substitute_tokens_in_directory",
    "substitute_tokens_in_staged_files",
)
