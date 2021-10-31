# import os
# import time

# from .test_utils import BaseManagerTestCase, timed
from .test_utils import BaseManagerTestCase

from pulsar.managers.queued import QueueManager

CANCEL_TEST_PROGRAM = """import os
open('%s', 'w').write(str(os.getpid()))
import time
time.sleep(10000)
"""


class PythonQueuedManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        self._set_manager(num_concurrent_jobs=1)

    def tearDown(self):
        super().setUp()
        self.manager.shutdown()

    def _set_manager(self, **kwds):
        self.manager = QueueManager('_default_', self.app, **kwds)

    def test_simple_execution(self):
        self._test_simple_execution(self.manager)

    def test_cancel_simple(self):
        self._test_cancelling(self.manager)

    # @timed(10)
    # def test_cancel_deeper(self):
    #    manager = self.manager
    #    # Test goes deeper than needed when deferring to
    #    # external managers. Ensure the PID dies when killed
    #    # and subsequent jobs never run.

    #    pid1 = os.path.join(self.staging_directory, "pid1")
    #    pid2 = os.path.join(self.staging_directory, "pid2")
    #    command1 = self._python_to_command(CANCEL_TEST_PROGRAM % pid1)
    #    command2 = self._python_to_command(CANCEL_TEST_PROGRAM % pid2)

    #    job1_id = manager.setup_job("124", "tool1", "1.0.0")
    #    job2_id = manager.setup_job("125", "tool1", "1.0.0")
    #    manager.launch(job1_id, command1)
    #    manager.launch(job2_id, command2)
    #    time.sleep(0.05)
    #    assert os.path.exists(pid1)
    #    assert not os.path.exists(pid2)
    #    manager.kill(job2_id)
    #    manager.kill(job1_id)
    #    self._assert_status_becomes_cancelled(job1_id, manager)
    #    self._assert_status_becomes_cancelled(job2_id, manager)
    #    time.sleep(0.05)
    #    assert not os.path.exists(pid2)
