from os.path import exists, join
import shutil
import tempfile
import time

from lwr.managers.queued import QueueManager
from lwr.managers.stateful import StatefulManagerProxy
from lwr.tools.authorization import get_authorizer
from .test_utils import TestDependencyManager

from galaxy.util.bunch import Bunch
from galaxy.jobs.metrics import NULL_JOB_INSTRUMENTER


def test_persistence():
    """
    Tests persistence of a managers jobs.
    """
    staging_directory = tempfile.mkdtemp()
    try:
        app = Bunch(staging_directory=staging_directory,
                    persistence_directory=staging_directory,
                    authorizer=get_authorizer(None),
                    dependency_manager=TestDependencyManager(),
                    job_metrics=Bunch(default_job_instrumenter=NULL_JOB_INSTRUMENTER),
                    )
        assert not exists(join(staging_directory, "queued_jobs"))
        queue1 = StatefulManagerProxy(QueueManager('test', app, num_concurrent_jobs=0))
        job_id = queue1.setup_job('4', 'tool1', '1.0.0')
        touch_file = join(staging_directory, 'ran')
        queue1.launch(job_id, 'touch %s' % touch_file)
        time.sleep(.4)
        assert (not(exists(touch_file)))
        queue1.shutdown()
        queue2 = StatefulManagerProxy(QueueManager('test', app, num_concurrent_jobs=1))
        time.sleep(1)
        assert exists(touch_file)
    finally:
        shutil.rmtree(staging_directory)
        try:
            queue2.shutdown()
        except:
            pass
