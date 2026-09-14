try:
    from drmaa import JobState
except (OSError, ImportError, RuntimeError):
    # DRMAA bindings are optional.
    JobState = None

from pulsar.managers import status
from pulsar.managers.queued_drmaa import DrmaaQueueManager
from .test_utils import (
    BaseManagerTestCase,
    skip_unless_module,
)


class DrmaaManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        self._set_manager()

    def tearDown(self):
        super().tearDown()
        self.manager.shutdown()

    def _set_manager(self, **kwds):
        self.manager = DrmaaQueueManager('_default_', self.app, **kwds)

    @skip_unless_module("drmaa")
    def test_simple_execution(self):
        self._test_simple_execution(self.manager)

    @skip_unless_module("drmaa")
    def test_cancel(self):
        self._test_cancelling(self.manager)

    @skip_unless_module("drmaa")
    def test_drmaa_state_to_pulsar_status(self):
        # Cover the full mapping so every DRMAA state uses Pulsar's vocabulary.
        expected = {
            JobState.UNDETERMINED: status.COMPLETE,
            JobState.QUEUED_ACTIVE: status.QUEUED,
            JobState.SYSTEM_ON_HOLD: status.QUEUED,
            JobState.USER_ON_HOLD: status.QUEUED,
            JobState.USER_SYSTEM_ON_HOLD: status.QUEUED,
            JobState.RUNNING: status.RUNNING,
            JobState.SYSTEM_SUSPENDED: status.QUEUED,
            JobState.USER_SUSPENDED: status.QUEUED,
            JobState.DONE: status.COMPLETE,
            JobState.FAILED: status.FAILED,
        }
        drmaa_session = _StubDrmaaSession()
        self.manager.drmaa_session = drmaa_session
        for drmaa_state, expected_status in expected.items():
            drmaa_session.state = drmaa_state
            assert self.manager._get_status_external("1234") == expected_status


class _StubDrmaaSession:

    def __init__(self):
        self.state = None

    def job_status(self, external_id):
        return self.state

    def close(self):
        pass
