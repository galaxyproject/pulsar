import os

import pytest

from pulsar.managers.base import JobDirectory
from .test_utils import TempDirectoryTestCase

TEST_JOB_ID = "1234"


class JobDirectoryTestCase(TempDirectoryTestCase):

    def setUp(self):
        super().setUp()
        self.job_directory = JobDirectory(self.temp_directory, TEST_JOB_ID)

    def test_setup(self):
        expected_path = os.path.join(self.temp_directory, TEST_JOB_ID)
        assert not os.path.exists(expected_path)
        self.job_directory.setup()
        assert os.path.exists(expected_path)

    def test_metadata(self):
        self.prep()
        assert not self.job_directory.has_metadata("MooCow")
        self.job_directory.store_metadata("MooCow", True)
        assert self.job_directory.has_metadata("MooCow")

    def test_read_stream_keeps_start_and_end_of_oversized_stream(self):
        self.prep()
        self.job_directory.write_file("tool_stdout", b"start" + b"x" * 100 + b"end")
        contents = self.job_directory.read_stream("tool_stdout", 20)
        assert contents == b"startxxx\n..\nxxxxxend"

    def test_read_stream_limit_too_small_to_join_keeps_start(self):
        self.prep()
        self.job_directory.write_file("tool_stdout", b"start and end")
        assert self.job_directory.read_stream("tool_stdout", 4) == b"star"

    def test_read_stream_returns_small_stream_whole(self):
        self.prep()
        self.job_directory.write_file("tool_stdout", b"all of it")
        assert self.job_directory.read_stream("tool_stdout", 20) == b"all of it"
        assert self.job_directory.read_stream("tool_stdout", -1) == b"all of it"

    def test_read_stream_missing_file(self):
        self.prep()
        assert self.job_directory.read_stream("missing", 20, default=b"") == b""
        with pytest.raises(FileNotFoundError):
            self.job_directory.read_stream("missing", 20)

    def prep(self):
        self.job_directory.setup()
