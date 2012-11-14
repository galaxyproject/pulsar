import multiprocessing

from queue_manager import QueueManager
from manager import Manager
from ConfigParser import ConfigParser, NoOptionError

MANAGER_PREFIX = 'manager:'
DEFAULT_MANAGER_NAME = '_default_'
# Number of concurrent jobs used by default for
# QueueManager.
DEFAULT_NUM_CONCURRENT_JOBS = 1


def build_managers(app, config_file):
    """
    Takes in a config file as outlined in job_managers.ini.sample and builds
    a dictionary of job manager objects from them.
    """
    managers = {}
    if not config_file:
        managers[DEFAULT_MANAGER_NAME] = _build_manager(app)
    else:
        config = ConfigParser()
        config.readfp(open(config_file))
        for section in config.sections():
            if not section.startswith(MANAGER_PREFIX):
                continue
            manager_name = section[len(MANAGER_PREFIX):]
            managers[manager_name] = _parse_manager(app, manager_name, config)
    return managers


def _parse_manager(app, manager_name, config):
    section_name = '%s%s' % (MANAGER_PREFIX, manager_name)
    try:
        queued = config.getboolean(section_name, 'queued')
    except ValueError:
        queued = True
    try:
        num_concurrent_jobs = config.get(section_name, 'num_concurrent_jobs')
    except NoOptionError:
        num_concurrent_jobs = 1
    return _build_manager(app, manager_name, queued, num_concurrent_jobs)


def _build_manager(app, name=DEFAULT_MANAGER_NAME, queued=True, num_concurrent_jobs=1):
    if num_concurrent_jobs == '*':
        num_concurrent_jobs = multiprocessing.cpu_count()
    else:
        num_concurrent_jobs = int(num_concurrent_jobs)
    if queued:
        return QueueManager(name, app.staging_directory,
                            app.persisted_job_store,
                            num_concurrent_jobs)
    else:
        return Manager(name, app.staging_directory)
