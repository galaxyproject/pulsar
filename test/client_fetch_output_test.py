"""Galaxy-side collection of from_work_dir outputs from a live Pulsar server.

A from_work_dir output the tool didn't produce gives an empty dataset, as it
does with a copy action, Pulsar-side staging or Galaxy's local runner: the
server serves it as an empty file. Anything else that stops the download (a
refused output, a file Pulsar can't read) still fails the job.
"""
import json
import os

import pytest
import webob.exc

from pulsar.client.exceptions import PulsarClientTransportError
from pulsar.client.manager import ClientManager
from pulsar.client.staging import (
    ClientOutputs,
    PulsarOutputs,
)
from pulsar.client.staging.down import finish_job
from pulsar.managers.base import JobDirectory
from .test_utils import (
    server_for_test_app,
    skip_unless_module,
    test_pulsar_app,
)


def _check_collection(tmp_path, transport=None):
    with test_pulsar_app() as app, server_for_test_app(app) as server:
        pulsar_app = app.app
        setup = json.loads(app.post("/jobs?job_id=1").body.decode("utf-8"))
        job_id = setup["job_id"]
        working = setup["working_directory"]
        with open(os.path.join(working, "out.txt"), "w") as f:
            f.write("OUT")
        # A symlinked directory inside the working directory: its files exist
        # but aren't in Pulsar's listing, which doesn't follow symlinks.
        os.mkdir(os.path.join(working, "real"))
        with open(os.path.join(working, "real", "inner.txt"), "w") as f:
            f.write("INNER")
        os.symlink("real", os.path.join(working, "linkdir"))
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret").write_text("SECRET")
        os.symlink(str(outside / "secret"), os.path.join(working, "escape"))
        os.symlink(str(outside), os.path.join(working, "escdir"))
        locked = os.path.join(working, "locked")
        os.mkdir(locked)
        with open(os.path.join(locked, "out.txt"), "w") as f:
            f.write("LOCKED")
        # Literally named like a glob, beside a file the glob would match.
        with open(os.path.join(working, "result?.txt"), "w") as f:
            f.write("LITERAL")
        with open(os.path.join(working, "result1.txt"), "w") as f:
            f.write("MATCH")
        with open(os.path.join(working, "plain"), "w") as f:
            f.write("PLAIN")
        os.symlink("never_written", os.path.join(working, "dangling"))
        listing = JobDirectory(pulsar_app.staging_directory, job_id).working_directory_contents()

        if transport is None:
            # An in-process Pulsar, as Galaxy's embedded runner uses.
            client_manager = ClientManager(job_manager=pulsar_app.only_manager, file_cache=pulsar_app.file_cache)
        else:
            client_manager = ClientManager(transport=transport)
        client = client_manager.get_client(
            {"url": server.application_url, "default_file_action": "transfer"}, job_id
        )
        galaxy_working = tmp_path / "galaxy_working"

        datasets = iter(range(100))

        def collect(from_work_dir):
            dataset = tmp_path / f"dataset_{next(datasets)}.dat"
            client_outputs = ClientOutputs(
                working_directory=str(galaxy_working),
                output_files=[str(dataset)],
                work_dir_outputs=[(str(galaxy_working / from_work_dir), str(dataset))],
            )
            pulsar_outputs = PulsarOutputs(
                working_directory_contents=listing,
                output_directory_contents=[],
                metadata_directory_contents=[],
                job_directory_contents=[],
            )
            failures = finish_job(client, "never", True, client_outputs, pulsar_outputs)
            return failures, dataset

        failures, dataset = collect("out.txt")
        assert failures == [] and dataset.read_text() == "OUT"

        failures, dataset = collect("linkdir/inner.txt")
        assert failures == [] and dataset.read_text() == "INNER"
        failures, dataset = collect("result?.txt")
        assert failures == [] and dataset.read_text() == "LITERAL"
        # The listing can't resolve this glob; the server does.
        failures, dataset = collect("linkdir/*.txt")
        assert failures == [] and dataset.read_text() == "INNER"

        # Not produced by the tool: an empty dataset.
        failures, dataset = collect("absent.txt")
        assert failures == [] and dataset.read_text() == ""
        failures, dataset = collect("absent_dir/absent.txt")
        assert failures == [] and dataset.read_text() == ""
        failures, dataset = collect("absent*.txt")
        assert failures == [] and dataset.read_text() == ""
        failures, dataset = collect("dangling")
        assert failures == [] and dataset.read_text() == ""

        # A file where a directory should be fails, as with the copy action
        # and Pulsar-side staging (NotADirectoryError).
        failures, _ = collect("plain/out.txt")
        assert len(failures) == 1

        # Refused by the server: fails the job.
        for refused in ("escape", "escdir/secret", "esc*/secret"):
            failures, _ = collect(refused)
            assert len(failures) == 1, refused
            if transport is not None:
                assert isinstance(failures[0], PulsarClientTransportError)

        if hasattr(os, "geteuid") and os.geteuid() != 0:
            # Present but unreadable: must not pass for a missing output.
            os.chmod(locked, 0)
            try:
                failures, _ = collect("locked/out.txt")
            finally:
                os.chmod(locked, 0o700)
            assert len(failures) == 1


def test_collection_urllib(tmp_path):
    _check_collection(tmp_path, "urllib")


@skip_unless_module("pycurl")
def test_collection_curl(tmp_path):
    _check_collection(tmp_path, "curl")


def test_collection_in_process(tmp_path):
    _check_collection(tmp_path)


def test_missing_output_of_other_types_is_an_error():
    with test_pulsar_app() as app:
        job_id = json.loads(app.post("/jobs?job_id=1").body.decode("utf-8"))["job_id"]
        for output_type in ("output", "output_metadata"):
            # The error escapes the app (a 500 over HTTP); WebTest re-raises it.
            with pytest.raises(webob.exc.HTTPNotFound):
                app.get(f"/jobs/{job_id}/files?name=absent.dat&type={output_type}")
