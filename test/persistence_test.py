import os
import shutil
import tempfile
import time

from lwr.persistence import PersistedJobStore
from lwr.managers.queued import QueueManager
from lwr.util import Bunch


def test_persistence():
    """
    Tests persistence of a managers jobs.
    """
    staging_directory = tempfile.mkdtemp()
    try:
        persisted_job_store = PersistedJobStore(**{'shelf_filename': os.path.join(staging_directory, 'persisted_jobs')})
        app = Bunch(persisted_job_store=persisted_job_store, staging_directory=staging_directory)
        queue1 = QueueManager('test', app, num_concurrent_jobs=0)
        queue1.setup_job_directory('4')
        touch_file = os.path.join(staging_directory, 'ran')
        queue1.launch('4', 'touch %s' % touch_file)
        time.sleep(5)
        assert (not(os.path.exists(touch_file)))
        queue1.shutdown()
        persisted_job_store.close()

        persisted_job_store2 = PersistedJobStore(**{'shelf_filename': os.path.join(staging_directory, 'persisted_jobs')})
        app.persisted_job_store = persisted_job_store2
        queue2 = QueueManager('test', app, num_concurrent_jobs=1)
        time.sleep(5)
        assert os.path.exists(touch_file)
    finally:
        shutil.rmtree(staging_directory)
        try:
            queue2.shutdown()
        except:
            pass
