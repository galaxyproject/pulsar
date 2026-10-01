"""Pulsar-side stage-out of working-directory outputs (``remote_transfer`` and friends).

A tool can leave symlinks in its working directory. Staging out must not follow
one to a file outside the working directory, and refusing such an output must
fail the job rather than leave Galaxy with an empty dataset.
"""
import os
from types import SimpleNamespace

from pulsar.client.staging.down import ResultsCollector
from pulsar.client.staging.models import (
    ClientOutputs,
    PulsarOutputs,
)
from pulsar.managers.base import JobDirectory
from pulsar.managers.staging.post import PulsarServerOutputCollector

JOB_ID = "1"


class RecordingActionMapper:
    """Maps every output to a remote action that records the Pulsar path it is staged from."""

    def __init__(self):
        self.uploaded = {}

    def action(self, source, type):
        uploaded = self.uploaded
        galaxy_path = source["path"]

        def write_from_path(pulsar_path):
            with open(pulsar_path) as f:
                uploaded[galaxy_path] = f.read()

        return SimpleNamespace(staging_action_local=False, path=galaxy_path, write_from_path=write_from_path)


class ImmediateExecutor:

    def execute(self, action, description):
        action()


def _job_directory(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    job_directory = JobDirectory(str(staging), JOB_ID)
    job_directory.setup()
    for directory in (job_directory.working_directory(), job_directory.inputs_directory()):
        os.makedirs(directory)
    return job_directory


def _write(path, contents):
    with open(path, "w") as f:
        f.write(contents)
    return str(path)


def _outside_file(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    return _write(outside / "secret", "SECRET")


def _stage_out(tmp_path, job_directory, from_work_dirs):
    """Stage out ``from_work_dirs`` as Pulsar does after the job; return (uploaded, failures)."""
    galaxy_working = tmp_path / "galaxy" / "working"
    work_dir_outputs = []
    for index, from_work_dir in enumerate(from_work_dirs):
        galaxy_path = str(tmp_path / "galaxy" / f"dataset_{index}.dat")
        work_dir_outputs.append((str(galaxy_working / from_work_dir), galaxy_path))
    client_outputs = ClientOutputs(
        working_directory=str(galaxy_working),
        output_files=[galaxy_path for _, galaxy_path in work_dir_outputs],
        work_dir_outputs=work_dir_outputs,
    )
    pulsar_outputs = PulsarOutputs(
        working_directory_contents=job_directory.working_directory_contents(),
        output_directory_contents=[],
        metadata_directory_contents=[],
        job_directory_contents=[],
    )
    action_mapper = RecordingActionMapper()
    output_collector = PulsarServerOutputCollector(job_directory, ImmediateExecutor(), lambda: False)
    failures = ResultsCollector(output_collector, action_mapper, client_outputs, pulsar_outputs).collect()
    uploaded = {os.path.basename(path): contents for path, contents in action_mapper.uploaded.items()}
    return uploaded, failures


def test_symlink_out_of_working_directory_fails_job(tmp_path):
    job_directory = _job_directory(tmp_path)
    working = job_directory.working_directory()
    _write(os.path.join(working, "real.txt"), "REAL")
    os.symlink("real.txt", os.path.join(working, "inner_link"))
    os.symlink(_outside_file(tmp_path), os.path.join(working, "escape"))

    uploaded, failures = _stage_out(tmp_path, job_directory, ["inner_link", "escape"])

    assert uploaded == {"dataset_0.dat": "REAL"}
    assert len(failures) == 1


def test_symlink_to_job_input_fails_job(tmp_path):
    job_directory = _job_directory(tmp_path)
    input_path = _write(os.path.join(job_directory.inputs_directory(), "dataset_7.dat"), "INPUT")
    os.symlink(input_path, os.path.join(job_directory.working_directory(), "passthrough.txt"))

    uploaded, failures = _stage_out(tmp_path, job_directory, ["passthrough.txt"])

    assert uploaded == {}
    assert len(failures) == 1


def test_file_under_symlinked_directory_fails_job(tmp_path):
    job_directory = _job_directory(tmp_path)
    os.symlink(os.path.dirname(_outside_file(tmp_path)), os.path.join(job_directory.working_directory(), "linkdir"))

    uploaded, failures = _stage_out(tmp_path, job_directory, ["linkdir/secret"])

    assert uploaded == {}
    assert len(failures) == 1


def test_glob_matching_under_symlinked_directory_fails_job(tmp_path):
    # The listing of the working directory doesn't descend into the symlinked
    # directory, so the pattern is resolved by globbing on the Pulsar host.
    job_directory = _job_directory(tmp_path)
    os.symlink(os.path.dirname(_outside_file(tmp_path)), os.path.join(job_directory.working_directory(), "linkdir"))

    uploaded, failures = _stage_out(tmp_path, job_directory, ["link*/secret"])

    assert uploaded == {}
    assert len(failures) == 1
