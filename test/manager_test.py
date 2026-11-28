import os
from os.path import (
    exists,
    join,
)
from unittest import mock

from pulsar.managers.base.directory import (
    JOB_FILE_RETURN_CODE,
    JOB_FILE_STANDARD_OUTPUT,
)
from pulsar.managers.unqueued import Manager
from .test_utils import (
    BaseManagerTestCase,
    get_failing_user_auth_manager,
)


class ManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        self._set_manager()

    def _set_manager(self, **kwds):
        self.manager = Manager('_default_', self.app, **kwds)

    def test_unauthorized_tool_submission(self):
        self.authorizer.authorization.allow_setup = False
        with self.assertRaises(Exception):
            self.manager.setup_job("123", "tool1", "1.0.0")

    def test_unauthorized_tool_file(self):
        self.authorizer.authorization.allow_tool_file = False
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        tool_directory = self.manager.job_directory(job_id).tool_files_directory()
        open(join(tool_directory, "test.sh"), "w") \
            .write("#!/bin/sh\ncat /etc/top_secret_passwords.txt")
        with self.assertRaises(Exception):
            self.manager.launch(job_id, 'python')

    def test_unauthorized_command_line(self):
        self.authorizer.authorization.allow_execution = False
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        with self.assertRaises(Exception):
            self.manager.launch(job_id, 'python')

    def test_unauthorized_user(self):
        self.manager.user_auth_manager = get_failing_user_auth_manager()
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        with self.assertRaises(Exception):
            self.manager.launch(job_id, 'python')

    def test_id_assigners(self):
        self._set_manager(assign_ids="galaxy")
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        self.assertEqual(job_id, "123")

        self._set_manager(assign_ids="uuid")
        job_id = self.manager.setup_job("124", "tool1", "1.0.0")
        self.assertNotEqual(job_id, "124")

    def test_maximum_stream_size_from_string_config(self):
        # Config sources that only produce strings (e.g. INI) must still cap streams.
        self._set_manager(maximum_stream_size="4")
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        self.manager.job_directory(job_id).write_file(JOB_FILE_STANDARD_OUTPUT, b"0123456789")
        self.assertEqual(self.manager.job_stdout_contents(job_id), b"0123")

    def test_unauthorized_config_file(self):
        self.authorizer.authorization.allow_config = False
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")

        config_directory = self.manager.job_directory(job_id).configs_directory()
        open(join(config_directory, "config1"), "w") \
            .write("#!/bin/sh\ncat /etc/top_secret_passwords.txt")

        with self.assertRaises(Exception):
            self.manager.launch(job_id, 'python')

    def test_simple_execution(self):
        self._test_simple_execution(self.manager)

    def test_kill(self):
        self._test_cancelling(self.manager)

    def test_clean_removes_a_file_written_while_the_directory_is_removed(self):
        # After a kill, the thread that waits for the job's process writes return_code once the process has ended.
        # When that lands while clean's rmtree runs, the final rmdir fails on the non-empty directory.
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        job_directory = self.manager.job_directory(job_id)
        real_rmdir = os.rmdir
        late_writes = []

        def rmdir(path, *args, **kwargs):
            if not late_writes and os.path.abspath(str(path)) == os.path.abspath(job_directory.path):
                late_writes.append(path)
                job_directory.write_file(JOB_FILE_RETURN_CODE, "-9")
            return real_rmdir(path, *args, **kwargs)

        with mock.patch.object(os, "rmdir", side_effect=rmdir):
            self.manager.clean(job_id)
        assert late_writes
        assert not exists(job_directory.path)

    def test_clean_survives_a_file_removed_while_the_directory_is_removed(self):
        # The same thread then removes the job's pid file (_finish_execution). When rmtree has listed it already,
        # unlinking it fails with FileNotFoundError and rmtree stops with nothing else removed. Python 3.13+ rmtree
        # skips the missing file itself, so there this only checks that nothing regressed.
        job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        job_directory = self.manager.job_directory(job_id)
        job_directory.store_metadata("pid", "12345")
        real_unlink = os.unlink
        removed_meanwhile = []

        def unlink(path, *args, **kwargs):
            if not removed_meanwhile and os.path.basename(str(path)) == "pid":
                removed_meanwhile.append(path)
                job_directory.remove_metadata("pid")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(os, "unlink", side_effect=unlink):
            self.manager.clean(job_id)
        assert removed_meanwhile
        assert not exists(job_directory.path)
