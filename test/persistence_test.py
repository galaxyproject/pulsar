import os
import shutil
import tempfile
import time


from lwr.persistence import PersistedJobStore
from lwr.queue_manager import QueueManager


def test_persistence():
    """
    Tests persistence of a managers jobs.
    """
    staging_directory = tempfile.mkdtemp()
    try:
        persisted_job_store = PersistedJobStore(**{'shelf_filename': os.path.join(staging_directory, 'persisted_jobs')})
        queue1 = QueueManager('test', staging_directory, persisted_job_store, 0)
        queue1.setup_job_directory('4')
        touch_file = os.path.join(staging_directory, 'ran')
        queue1.launch('4', 'touch %s' % touch_file)
        time.sleep(5)
        assert (not(os.path.exists(touch_file)))
        queue1.shutdown()
        
        queue2 = QueueManager('test', staging_directory, persisted_job_store, 1)
        time.sleep(5)
        assert os.path.exists(touch_file)
    finally:
        shutil.rmtree(staging_directory)
        try:
            queue2.shutdown()
        except:
            pass

            
    
