import tempfile
from time import sleep

from lwr.managers.unqueued import Manager
from galaxy.util.bunch import Bunch
from galaxy.jobs.metrics import NULL_JOB_INSTRUMENTER

from shutil import rmtree

from os import listdir
from os.path import join

from .test_utils import TestCase
from .test_utils import TestAuthorizer
from .test_utils import TestDependencyManager


class ManagerTest(TestCase):

    def setUp(self):
        staging_directory = tempfile.mkdtemp()
        rmtree(staging_directory)
        self.staging_directory = staging_directory
        self.authorizer = TestAuthorizer()

        self.app = Bunch(staging_directory=staging_directory,
                         authorizer=self.authorizer,
                         job_metrics=NullJobMetrics(),
                         dependency_manager=TestDependencyManager())

        self._set_manager()

    def _set_manager(self, **kwds):
        self.manager = Manager('_default_', self.app, **kwds)

    def tearDown(self):
        rmtree(self.staging_directory)

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
        manager = self.manager
        command = """python -c "import sys; sys.stdout.write(\'Hello World!\'); sys.stderr.write(\'moo\')" """
        job_id = manager.setup_job("123", "tool1", "1.0.0")
        manager.launch(job_id, command)
        while manager.get_status(job_id) not in ['complete', 'cancelled']:
            pass
        self.assertEquals(manager.stderr_contents(job_id), 'moo')
        self.assertEquals(manager.stdout_contents(job_id), 'Hello World!')
        self.assertEquals(manager.return_code(job_id), 0)
        manager.clean(job_id)
        self.assertEquals(len(listdir(self.staging_directory)), 0)

    def test_kill(self):
        manager = self.manager
        job_id = manager.setup_job("124", "tool1", "1.0.0")
        command = """python -c "import time; time.sleep(10000)" """
        manager.launch(job_id, command)
        sleep(0.1)
        manager.kill(job_id)
        manager.kill(job_id)  # Make sure kill doesn't choke if pid doesn't exist
        while manager.get_status(job_id) not in ['complete', 'cancelled']:
            pass
        manager.clean(job_id)


class NullJobMetrics(object):

    def __init__(self):
        self.default_job_instrumenter = NULL_JOB_INSTRUMENTER
