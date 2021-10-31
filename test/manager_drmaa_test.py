from .test_utils import (
    BaseManagerTestCase,
    skip_unless_module
)

from pulsar.managers.queued_drmaa import DrmaaQueueManager


class DrmaaManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        self._set_manager()

    def tearDown(self):
        super().setUp()
        self.manager.shutdown()

    def _set_manager(self, **kwds):
        self.manager = DrmaaQueueManager('_default_', self.app, **kwds)

    @skip_unless_module("drmaa")
    def test_simple_execution(self):
        self._test_simple_execution(self.manager)

    @skip_unless_module("drmaa")
    def test_cancel(self):
        self._test_cancelling(self.manager)
