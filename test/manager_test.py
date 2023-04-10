from pulsar.managers.unqueued import Manager

from os.path import join

from .test_utils import BaseManagerTestCase, get_failing_user_auth_manager


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
