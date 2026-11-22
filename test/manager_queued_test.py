# import time
import os
from functools import partial
from pathlib import Path

from pulsar.managers.queued import QueueManager

# from .test_utils import BaseManagerTestCase, timed
from .test_utils import (
    BaseManagerTestCase,
    wait_for,
)

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

    def test_num_concurrent_jobs_limits_running_jobs(self):
        manager = self.manager
        jobs = [self._launch_timed_sleep(job_number) for job_number in ("1", "2")]
        for job_id, _ in jobs:
            wait_for(
                partial(manager.get_status, job_id),
                f"job {job_id} to complete",
                until=lambda polled: polled == "complete",
                timeout=15,
            )
        (start1, end1), (start2, end2) = (map(float, Path(timestamps).read_text().split()) for _, timestamps in jobs)
        assert end1 <= start2 or end2 <= start1, f"jobs overlapped with num_concurrent_jobs=1: [{start1}, {end1}] and [{start2}, {end2}]"

    def _launch_timed_sleep(self, job_number):
        timestamps = os.path.join(self.staging_directory, f"timestamps_{job_number}")
        command = self._python_to_command(
            f"import time\nstart = time.time(); time.sleep(2)\nopen('{timestamps}', 'w').write(f'{{start}} {{time.time()}}')"
        )
        job_id = self.manager.setup_job(job_number, "tool1", "1.0.0")
        self.manager.launch(job_id, command)
        return job_id, timestamps

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
