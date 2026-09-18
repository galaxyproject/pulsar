"""Tests for job-directory token substitution.

``__PULSAR_JOBS_DIRECTORY__`` lets a Galaxy admin point a destination at a
staging root whose real path only the Pulsar server knows. The client emits
the token; the server replaces it once the job directory exists.
"""
import os

import pytest

from pulsar.managers.util.job_directory_tokens import (
    JOB_DIRECTORY_TOKEN,
    JOBS_DIRECTORY_TOKEN,
    substitute_tokens,
    substitute_tokens_in_directory,
)

JOB_DIRECTORY = "/staging/j1"
JOBS_DIRECTORY = "/staging"


def test_both_tokens_substituted():
    text = f"{JOBS_DIRECTORY_TOKEN}/j1/configs/x and {JOB_DIRECTORY_TOKEN}/working"
    assert substitute_tokens(text, JOB_DIRECTORY, JOBS_DIRECTORY) == (
        "/staging/j1/configs/x and /staging/j1/working"
    )


def test_singular_token_not_clobbered_by_plural():
    """The plural token contains the singular one's prefix.

    They are not substrings of each other today, but a future rename could
    make them so - assert the invariant rather than trusting the spelling.
    """
    assert JOB_DIRECTORY_TOKEN not in JOBS_DIRECTORY_TOKEN
    assert JOBS_DIRECTORY_TOKEN not in JOB_DIRECTORY_TOKEN
    text = f"{JOBS_DIRECTORY_TOKEN} {JOB_DIRECTORY_TOKEN}"
    assert substitute_tokens(text, JOB_DIRECTORY, JOBS_DIRECTORY) == "/staging /staging/j1"


def test_text_without_tokens_is_unchanged():
    assert substitute_tokens("echo hello", JOB_DIRECTORY, JOBS_DIRECTORY) == "echo hello"


def test_jobs_directory_defaults_to_parent_of_job_directory():
    text = f"{JOBS_DIRECTORY_TOKEN}/j1"
    assert substitute_tokens(text, JOB_DIRECTORY) == "/staging/j1"


def test_directory_sweep_rewrites_only_files_holding_a_token(tmp_path):
    tokened = tmp_path / "tool_script.sh"
    tokened.write_text(f"#!/bin/sh\ncd {JOBS_DIRECTORY_TOKEN}/j1/working\n")
    plain = tmp_path / "other.txt"
    plain.write_text("nothing to see\n")
    plain_mtime = plain.stat().st_mtime_ns

    rewritten = substitute_tokens_in_directory(str(tmp_path), JOB_DIRECTORY, JOBS_DIRECTORY)

    assert rewritten == [str(tokened)]
    assert tokened.read_text() == "#!/bin/sh\ncd /staging/j1/working\n"
    assert plain.stat().st_mtime_ns == plain_mtime


def test_directory_sweep_recurses(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    target = nested / "params.json"
    target.write_text('{"filename_override": "%s/j1/outputs/out"}' % JOBS_DIRECTORY_TOKEN)

    substitute_tokens_in_directory(str(tmp_path), JOB_DIRECTORY, JOBS_DIRECTORY)

    assert target.read_text() == '{"filename_override": "/staging/j1/outputs/out"}'


def test_directory_sweep_preserves_the_executable_bit(tmp_path):
    script = tmp_path / "tool_script.sh"
    script.write_text(f"cd {JOB_DIRECTORY_TOKEN}\n")
    os.chmod(script, 0o755)

    substitute_tokens_in_directory(str(tmp_path), JOB_DIRECTORY, JOBS_DIRECTORY)

    assert script.read_text() == "cd /staging/j1\n"
    assert os.stat(script).st_mode & 0o777 == 0o755


def test_directory_sweep_skips_undecodable_files(tmp_path):
    """Metadata directories carry pickled dataset blobs alongside JSON."""
    blob = tmp_path / "metadata.dat"
    raw = JOBS_DIRECTORY_TOKEN.encode("utf-8") + b"\xff\xfe\x00 binary"
    blob.write_bytes(raw)

    rewritten = substitute_tokens_in_directory(str(tmp_path), JOB_DIRECTORY, JOBS_DIRECTORY)

    assert rewritten == []
    assert blob.read_bytes() == raw


def test_directory_sweep_tolerates_a_missing_directory(tmp_path):
    missing = str(tmp_path / "nope")
    assert substitute_tokens_in_directory(missing, JOB_DIRECTORY, JOBS_DIRECTORY) == []


@pytest.mark.parametrize("token", [JOBS_DIRECTORY_TOKEN, JOB_DIRECTORY_TOKEN])
def test_tokens_are_documented_spellings(token):
    """Guard the wire contract - these strings are in Galaxy job_conf files."""
    assert token.startswith("__PULSAR_JOB")
    assert token.endswith("_DIRECTORY__")
