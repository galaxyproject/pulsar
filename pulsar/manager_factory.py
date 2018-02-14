import inspect
import logging
import os

import pulsar.managers
from pulsar.managers import stateful
from six.moves import configparser

log = logging.getLogger(__name__)


MANAGER_PREFIX = 'manager:'
DEFAULT_MANAGER_NAME = '_default_'
DEFAULT_MANAGER_TYPE = 'queued_python'


def build_managers(app, conf):
    """
    Takes in a config file as outlined in job_managers.ini.sample and builds
    a dictionary of job manager objects from them.
    """
    # Load default options from config file that apply to all
    # managers.
    default_options = _get_default_options(conf)

    manager_descriptions = ManagerDescriptions()
    if "job_managers_config" in conf:
        job_managers_config = conf.get("job_managers_config", None)
        _populate_manager_descriptions_from_ini(manager_descriptions, job_managers_config)
    elif "managers" in conf:
        for manager_name, manager_options in conf["managers"].items():
            manager_description = ManagerDescription.from_dict(manager_options, manager_name)
            manager_descriptions.add(manager_description)
    elif "manager" in conf:
        manager_description = ManagerDescription.from_dict(conf["manager"])
        manager_descriptions.add(manager_description)
    else:
        manager_descriptions.add(ManagerDescription())

    manager_classes = _get_managers_dict()
    managers = {}
    for manager_name, manager_description in manager_descriptions.descriptions.items():
        manager_options = dict(default_options)
        manager_options.update(manager_description.manager_options)

        manager_class = manager_classes[manager_description.manager_type]
        manager = _build_manager(manager_class, app, manager_name, manager_options)
        managers[manager_name] = manager

    return managers


def _populate_manager_descriptions_from_ini(manager_descriptions, job_managers_config):
    config = configparser.ConfigParser()
    config.readfp(open(job_managers_config))
    for section in config.sections():
        if not section.startswith(MANAGER_PREFIX):
            continue
        manager_name = section[len(MANAGER_PREFIX):]
        manager_description = ManagerDescription.from_ini_config(config, manager_name)
        manager_descriptions.add(manager_description)


def _get_default_options(conf):
    options = {}
    for simple_key in ["assign_ids", "galaxy_home"]:
        if simple_key in conf:
            options[simple_key] = conf[simple_key]
    options["debug"] = conf.get("debug", False)
    maximum_stream_size = conf.get("maximum_stream_size", 1024 * 1024)
    if maximum_stream_size:
        options["maximum_stream_size"] = int(maximum_stream_size)
    # mode to create job directories with, if None just use
    # default (usually 0777 with umask applied).
    job_directory_mode = conf.get("job_directory_mode", None)
    options["job_directory_mode"] = None
    if job_directory_mode is not None:
        options["job_directory_mode"] = int(job_directory_mode, 8)
    return options


def _build_manager(manager_class, app, name=DEFAULT_MANAGER_NAME, manager_options={}):
    return stateful.StatefulManagerProxy(manager_class(name, app, **manager_options), **manager_options)


def _get_manager_modules():
    """

    >>> 'pulsar.managers.queued_pbs' in _get_manager_modules()
    True
    >>> 'pulsar.managers.queued_drmaa' in _get_manager_modules()
    True
    """
    managers_dir = pulsar.managers.__path__[0]
    module_names = []
    for fname in os.listdir(managers_dir):
        if not(fname.startswith("_")) and fname.endswith(".py"):
            manager_module_name = "pulsar.managers.%s" % fname[:-len(".py")]
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

    >>> from pulsar.managers.queued_pbs import PbsQueueManager
    >>> _get_managers_dict()['queued_pbs'] == PbsQueueManager
    True
    >>> from pulsar.managers.queued_drmaa import DrmaaQueueManager
    >>> _get_managers_dict()['queued_drmaa'] == DrmaaQueueManager
    True
    """
    managers = {}
    for manager_module in _load_manager_modules():
        for _, obj in inspect.getmembers(manager_module):
            if inspect.isclass(obj) and hasattr(obj, 'manager_type'):
                managers[getattr(obj, 'manager_type')] = obj

    return managers


class ManagerDescriptions(object):

    def __init__(self):
        self.descriptions = {}

    def add(self, manager_description):
        manager_name = manager_description.manager_name
        if manager_name in self.descriptions:
            raise Exception("Problem configuring job managers, multiple managers with name %s" % manager_name)
        self.descriptions[manager_name] = manager_description


class ManagerDescription(object):

    def __init__(self, manager_type=DEFAULT_MANAGER_TYPE, manager_name=DEFAULT_MANAGER_NAME, manager_options={}):
        self.manager_type = manager_type
        self.manager_name = manager_name
        self.manager_options = manager_options

    @staticmethod
    def from_ini_config(config, manager_name):
        section_name = '%s%s' % (MANAGER_PREFIX, manager_name)
        try:
            manager_type = config.get(section_name, 'type')
        except ValueError:
            manager_type = DEFAULT_MANAGER_TYPE

        # Merge default and specific manager options.
        manager_options = {}
        manager_options.update(dict(config.items(section_name)))
        return ManagerDescription(manager_type, manager_name, manager_options)

    @staticmethod
    def from_dict(config, manager_name=DEFAULT_MANAGER_NAME):
        manager_type = config.get("type", DEFAULT_MANAGER_TYPE)
        return ManagerDescription(manager_type, manager_name, config)
