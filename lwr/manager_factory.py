import inspect
import logging
import os

import lwr.managers
from lwr.managers import stateful
from lwr.managers.queued import QueueManager
from six.moves import configparser

log = logging.getLogger(__name__)


MANAGER_PREFIX = 'manager:'
DEFAULT_MANAGER_NAME = '_default_'


def build_managers(app, conf):
    """
    Takes in a config file as outlined in job_managers.ini.sample and builds
    a dictionary of job manager objects from them.
    """
    job_managers_config = conf.get("job_managers_config", None)

    # Load default options from config file that apply to all
    # managers.
    default_options = _get_default_options(conf)

    manager_classes = _get_managers_dict()
    managers = {}

    if not job_managers_config:
        managers[DEFAULT_MANAGER_NAME] = _build_manager(QueueManager, app, DEFAULT_MANAGER_NAME, default_options)
    else:
        config = configparser.ConfigParser()
        config.readfp(open(job_managers_config))
        for section in config.sections():
            if not section.startswith(MANAGER_PREFIX):
                continue
            manager_name = section[len(MANAGER_PREFIX):]
            managers[manager_name] = \
                _parse_manager(manager_classes, app, manager_name, config, default_options)

    return managers


def _get_default_options(conf):
    options = {}
    if "assign_ids" in conf:
        options["assign_ids"] = conf["assign_ids"]
    options["debug"] = conf.get("debug", False)
    return options


def _parse_manager(manager_classes, app, manager_name, config, default_options):
    section_name = '%s%s' % (MANAGER_PREFIX, manager_name)
    try:
        manager_type = config.get(section_name, 'type')
    except ValueError:
        manager_type = 'queued_python'

    manager_class = manager_classes[manager_type]

    # Merge default and specific manager options.
    manager_options = dict(default_options)
    manager_options.update(dict(config.items(section_name)))

    return _build_manager(manager_class, app, manager_name, manager_options)


def _build_manager(manager_class, app, name=DEFAULT_MANAGER_NAME, manager_options={}):
    return stateful.StatefulManagerProxy(manager_class(name, app, **manager_options), **manager_options)


def _get_manager_modules():
    """

    >>> 'lwr.managers.queued_pbs' in _get_manager_modules()
    True
    >>> 'lwr.managers.queued_drmaa' in _get_manager_modules()
    True
    """
    managers_dir = lwr.managers.__path__[0]
    module_names = []
    for fname in os.listdir(managers_dir):
        if not(fname.startswith("_")) and fname.endswith(".py"):
            manager_module_name = "lwr.managers.%s" % fname[:-len(".py")]
            module_names.append(manager_module_name)
    return module_names


def _load_manager_modules():
    modules = []
    for manager_module_name in _get_manager_modules():
        try:
            module = __import__(manager_module_name)
            for comp in manager_module_name.split(".")[1:]:
                module = getattr(module, comp)
            modules.append(module)
        except BaseException as exception:
            exception_str = str(exception)
            message = "%s manager module could not be loaded: %s" % (manager_module_name, exception_str)
            log.warn(message)
            continue

    return modules


def _get_managers_dict():
    """

    >>> from lwr.managers.queued_pbs import PbsQueueManager
    >>> _get_managers_dict()['queued_pbs'] == PbsQueueManager
    True
    >>> from lwr.managers.queued_drmaa import DrmaaQueueManager
    >>> _get_managers_dict()['queued_drmaa'] == DrmaaQueueManager
    True
    """
    managers = {}
    for manager_module in _load_manager_modules():
        for _, obj in inspect.getmembers(manager_module):
            if inspect.isclass(obj) and hasattr(obj, 'manager_type'):
                managers[getattr(obj, 'manager_type')] = obj

    return managers
