from os.path import exists, join
import shutil
import tempfile
import time

from lwr.managers.queued import QueueManager
from lwr.util import Bunch
from lwr.tools.authorization import get_authorizer


def test_persistence():
    """
    Tests persistence of a managers jobs.
    """
    staging_directory = tempfile.mkdtemp()
    try:
        app = Bunch(staging_directory=staging_directory,
                    persistence_directory=staging_directory,
                    authorizer=get_authorizer(None))
        assert not exists(join(staging_directory, "queued_jobs"))
        queue1 = QueueManager('test', app, num_concurrent_jobs=0)
        job_id = queue1.setup_job('4', 'tool1', '1.0.0')
        touch_file = join(staging_directory, 'ran')
        queue1.launch(job_id, 'touch %s' % touch_file)
        time.sleep(.4)
        assert (not(exists(touch_file)))
        assert exists(join(staging_directory, "queued_jobs"))
        queue1.shutdown()
        queue2 = QueueManager('test', app, num_concurrent_jobs=1)
        assert exists(join(staging_directory, "queued_jobs"))
        time.sleep(1)
        assert exists(touch_file)
    finally:
        shutil.rmtree(staging_directory)
        try:
            queue2.shutdown()
        except:
            pass
