"""
"""
import os
from tempfile import tempdir

from pulsar.manager_factory import build_managers
from pulsar.cache import Cache
from pulsar.tools import ToolBox
from pulsar.tools.authorization import get_authorizer
from pulsar import messaging
from galaxy.objectstore import build_object_store_from_config
try:
    # If galaxy-lib or Galaxy <19.05 present.
    from galaxy.tools.deps import DependencyManager
except ImportError:
    # If galaxy-tool-util or Galaxy >=19.09 present.
    from galaxy.tool_util.deps import DependencyManager
try:
    # If galaxy-lib or Galaxy <19.05 present.
    from galaxy.jobs.metrics import JobMetrics
except ImportError:
    # If galaxy-job-metrics or Galaxy >=19.09 present.
    from galaxy.job_metrics import JobMetrics
from galaxy.util.bunch import Bunch

from logging import getLogger
log = getLogger(__name__)

DEFAULT_PRIVATE_TOKEN = None
DEFAULT_FILES_DIRECTORY = "files"
DEFAULT_STAGING_DIRECTORY = os.path.join(DEFAULT_FILES_DIRECTORY, "staging")
DEFAULT_PERSISTENCE_DIRECTORY = os.path.join(DEFAULT_FILES_DIRECTORY, "persisted_data")


NOT_WHITELIST_WARNING = "Starting the Pulsar without a toolbox to white-list." + \
                        "Ensure this application is protected by firewall or a configured private token."
MULTIPLE_MANAGERS_MESSAGE = "app.only_manager accessed with multiple managers configured"


class PulsarApp(object):

    def __init__(self, **conf):
        if conf is None:
            conf = {}
        self.__setup_staging_directory(conf.get("staging_directory", DEFAULT_STAGING_DIRECTORY))
        self.__setup_private_token(conf.get("private_token", DEFAULT_PRIVATE_TOKEN))
        self.__setup_persistence_directory(conf.get("persistence_directory", None))
        self.__setup_tool_config(conf)
        self.__setup_object_store(conf)
        self.__setup_dependency_manager(conf)
        self.__setup_job_metrics(conf)
        self.__setup_managers(conf)
        self.__setup_file_cache(conf)
        self.__setup_bind_to_message_queue(conf)
        self.__recover_jobs()
        self.ensure_cleanup = conf.get("ensure_cleanup", False)

    def shutdown(self, timeout=None):
        for manager in self.managers.values():
            try:
                manager.shutdown(timeout)
            except Exception:
                pass

        if self.__queue_state:
            self.__queue_state.deactivate()
            if self.ensure_cleanup:
                self.__queue_state.join(timeout)

    def __setup_bind_to_message_queue(self, conf):
        message_queue_url = conf.get("message_queue_url", None)
        queue_state = None
        if message_queue_url:
            queue_state = messaging.bind_app(self, message_queue_url, conf)
        self.__queue_state = queue_state

    def __setup_tool_config(self, conf):
        """
        Setups toolbox object and authorization mechanism based
        on supplied toolbox_path.
        """
        tool_config_files = conf.get("tool_config_files", None)
        if not tool_config_files:
            # For compatibity with Galaxy, allow tool_config_file
            # option name.
            tool_config_files = conf.get("tool_config_file", None)
        toolbox = None
        if tool_config_files:
            toolbox = ToolBox(tool_config_files)
        else:
            log.info(NOT_WHITELIST_WARNING)
        self.toolbox = toolbox
        self.authorizer = get_authorizer(toolbox)

    def __setup_staging_directory(self, staging_directory):
        self.staging_directory = os.path.abspath(staging_directory)

    def __setup_managers(self, conf):
        self.managers = build_managers(self, conf)

    def __recover_jobs(self):
        for manager in self.managers.values():
            manager.recover_active_jobs()

    def __setup_private_token(self, private_token):
        self.private_token = private_token
        if private_token:
            log.info("Securing Pulsar web app with private key, please verify you are using HTTPS so key cannot be obtained by monitoring traffic.")

    def __setup_persistence_directory(self, persistence_directory):
        persistence_directory = persistence_directory or DEFAULT_PERSISTENCE_DIRECTORY
        if persistence_directory == "__none__":
            persistence_directory = None
        self.persistence_directory = persistence_directory

    def __setup_file_cache(self, conf):
        file_cache_dir = conf.get('file_cache_dir', None)
        self.file_cache = Cache(file_cache_dir) if file_cache_dir else None

    def __setup_object_store(self, conf):
        if "object_store_config_file" not in conf:
            self.object_store = None
            return
        object_store_config = Bunch(
            object_store_config_file=conf['object_store_config_file'],
            file_path=conf.get("object_store_file_path", None),
            object_store_check_old_style=False,
            job_working_directory=conf.get("object_store_job_working_directory", None),
            new_file_path=conf.get("object_store_new_file_path", tempdir),
            umask=int(conf.get("object_store_umask", "0000")),
        )
        self.object_store = build_object_store_from_config(object_store_config)

    def __setup_dependency_manager(self, conf):
        dependencies_dir = conf.get("tool_dependency_dir", "dependencies")
        resolvers_config_file = conf.get("dependency_resolvers_config_file", "dependency_resolvers_conf.xml")
        conda_config = {k: v for k, v in conf.items() if k.startswith("conda_")}
        self.dependency_manager = DependencyManager(dependencies_dir, resolvers_config_file, app_config=conda_config)

    def __setup_job_metrics(self, conf):
        job_metrics = conf.get("job_metrics", None)
        if job_metrics is None:
            job_metrics_config_file = conf.get("job_metrics_config_file", "job_metrics_conf.xml")
            job_metrics = JobMetrics(job_metrics_config_file)
        self.job_metrics = job_metrics

    @property
    def only_manager(self):
        """Convience accessor for tests and contexts with sole manager."""
        assert len(self.managers) == 1, MULTIPLE_MANAGERS_MESSAGE
        return list(self.managers.values())[0]
