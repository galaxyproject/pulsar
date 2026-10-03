import time
from contextlib import contextmanager
from os.path import (
    exists,
    join,
)

from galaxy.job_metrics import NULL_JOB_INSTRUMENTER
from galaxy.util.bunch import Bunch

from pulsar.managers.base import JobDirectory
from pulsar.managers.queued import QueueManager
from pulsar.managers.stateful import (
    ACTIVE_STATUS_LAUNCHED,
    StatefulManagerProxy,
)
from pulsar.managers.unqueued import JOB_FILE_SUBMITTED
from pulsar.tools.authorization import get_authorizer
from .test_utils import (
    get_test_user_auth_manager,
    temp_directory,
    TestDependencyManager,
)

TEST_JOB_ID = "4"
TEST_STAGED_FILE = "cow"
TEST_COMMAND_TOUCH_FILE = "ran"


def test_launched_job_recovery():
    """Tests persistence and recovery of launched managers jobs."""
    with _app() as app:
        staging_directory = app.staging_directory
        queue1 = StatefulManagerProxy(QueueManager('test', app, num_concurrent_jobs=0))
        job_id = queue1.setup_job(TEST_JOB_ID, 'tool1', '1.0.0')
        touch_file = join(staging_directory, TEST_COMMAND_TOUCH_FILE)
        queue1.preprocess_and_launch(job_id, {"command_line": 'touch %s' % touch_file})
        time.sleep(.4)
        assert not exists(touch_file)
        queue1.shutdown()
        _setup_manager_that_executes(app)
        assert exists(touch_file)


def test_preprocessing_job_recovery():
    """Tests persistence and recovery of preprocessing managers jobs (clean)."""
    with _app() as app:
        _setup_job_with_unexecuted_preprocessing_directive(app)
        staging_directory = app.staging_directory
        staged_file = join(staging_directory, TEST_JOB_ID, "inputs", TEST_STAGED_FILE)
        touch_file = join(staging_directory, TEST_COMMAND_TOUCH_FILE)

        # File shouldn't have been staged because we hacked stateful proxy manager to not
        # run preprocess.
        assert not exists(staged_file)

        _setup_manager_that_preprocesses(app)

        assert exists(staged_file)
        assert not exists(touch_file)

        _setup_manager_that_executes(app)
        assert exists(touch_file)


def test_preprocessing_job_recovery_dirty():
    """Tests persistence and recovery of preprocessing managers jobs (dirty)."""

    # Same test as above, but simulating existing files from a previous partial
    # preprocess.
    with _app() as app:
        _setup_job_with_unexecuted_preprocessing_directive(app)
        staging_directory = app.staging_directory
        staged_file = join(staging_directory, TEST_JOB_ID, "inputs", TEST_STAGED_FILE)
        touch_file = join(staging_directory, TEST_COMMAND_TOUCH_FILE)

        # File shouldn't have been staged because we hacked stateful proxy manager to not
        # run preprocess.
        assert not exists(staged_file)
        # write out partial contents, make sure preprocess writes over this with the correct
        # contents.
        open(staged_file, "wb").write(b"co")
        _setup_manager_that_preprocesses(app)

        assert exists(staged_file)
        assert open(staged_file, "rb").read() == b"cow file"
        assert not exists(touch_file)

        _setup_manager_that_executes(app)
        assert exists(touch_file)


def _setup_manager_that_preprocesses(app):
    # Setup a manager that will preprocess the job but won't execute it.

    # Now start a real stateful manager proxy and watch the file get staged.
    queue2 = StatefulManagerProxy(QueueManager('test', app, num_concurrent_jobs=0))
    try:
        queue2.recover_active_jobs()
        # Preprocessing ends by recording the job as launched, which is what the next manager recovers.
        _wait_for(lambda: TEST_JOB_ID in queue2.active_jobs.active_job_ids(active_status=ACTIVE_STATUS_LAUNCHED))
    finally:
        try:
            queue2.shutdown()
        except Exception:
            pass


def _setup_job_with_unexecuted_preprocessing_directive(app):
    staging_directory = app.staging_directory
    queue1 = DoesntPreprocessStatefulManagerProxy(QueueManager('test', app, num_concurrent_jobs=0))
    job_id = queue1.setup_job(TEST_JOB_ID, 'tool1', '1.0.0')
    action = {"name": TEST_STAGED_FILE, "type": "input", "action": {"action_type": "message", "contents": "cow file"}}
    remote_staging = {"setup": [action]}
    touch_file = join(staging_directory, TEST_COMMAND_TOUCH_FILE)
    queue1.preprocess_and_launch(job_id, {"command_line": "touch '%s'" % touch_file, "remote_staging": remote_staging})
    queue1.shutdown()


def _setup_manager_that_executes(app):
    queue2 = StatefulManagerProxy(QueueManager('test', app, num_concurrent_jobs=1))
    try:
        queue2.recover_active_jobs()
        # Wait for the run to finish, not just the command: finishing still writes to the job directory.
        touch_file = join(app.staging_directory, TEST_COMMAND_TOUCH_FILE)
        job_directory = JobDirectory(app.staging_directory, TEST_JOB_ID)
        _wait_for(lambda: exists(touch_file) and not job_directory.has_metadata(JOB_FILE_SUBMITTED))
    finally:
        try:
            queue2.shutdown()
        except Exception:
            pass


def _wait_for(condition, timeout=10):
    # A fixed sleep raced the recovered job: it usually finishes within half a second, but not always.
    deadline = time.time() + timeout
    while not condition() and time.time() < deadline:
        time.sleep(0.05)


@contextmanager
def _app():
    with temp_directory() as staging_directory:
        app = Bunch(
            staging_directory=staging_directory,
            persistence_directory=staging_directory,
            authorizer=get_authorizer(None),
            user_auth_manager=get_test_user_auth_manager(),
            dependency_manager=TestDependencyManager(),
            job_metrics=Bunch(default_job_instrumenter=NULL_JOB_INSTRUMENTER),
            object_store=None,
        )
        yield app


class DoesntPreprocessStatefulManagerProxy(StatefulManagerProxy):

    def _launch_prepreprocessing_thread(self, job_id, launch_config):
        pass
