from .test_utils import TempDirectoryTestCase
from pulsar.managers.base import JobDirectory
import os

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

    def prep(self):
        self.job_directory.setup()
