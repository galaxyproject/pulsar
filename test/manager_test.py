import tempfile

from lwr.managers.base import Manager
from lwr.util import Bunch

from unittest import TestCase
from shutil import rmtree


class ManagerTest(TestCase):

    def setUp(self):
        staging_directory = tempfile.mkdtemp()
        rmtree(staging_directory)
        self.staging_directory = staging_directory
        self.authorizer = TestAuthorizer()

        self.app = Bunch(staging_directory=staging_directory,
                         persisted_job_store=TestPersistedJobStore(),
                         authorizer=self.authorizer)

        self.manager = Manager('_default_', self.app)

    def tearDown(self):
        rmtree(self.staging_directory)

    def test_unauthorized_tool_submission(self):
        self.authorizer.authorization.allow_setup = False
        with self.assertRaises(Exception):
            self.manager.setup_job("123", "tool1", "1.0.0")


class TestAuthorization(object):

    def __init__(self):
        self.allow_setup = True

    def can_setup(self):
        return self.allow_setup


class TestAuthorizer(object):

    def __init__(self):
        self.authorization = TestAuthorization()

    def get_authorization(self):
        return self.authorization


class TestPersistedJobStore:

    def next_id(self):
        yield 1
        yield 2
        yield 3
