"""
"""
import atexit
import inspect
import os
from tempfile import tempdir

from lwr.manager_factory import build_managers
from lwr.cache import Cache
from lwr.framework import RoutingApp
from lwr.tools import ToolBox
from lwr.tools.authorization import get_authorizer
from lwr.util.bunch import Bunch
import lwr.routes
from galaxy.objectstore import build_object_store_from_config
from galaxy.tools.deps import DependencyManager

from logging import getLogger
log = getLogger(__name__)

DEFAULT_PRIVATE_KEY = None
DEFAULT_STAGING_DIRECTORY = "lwr_staging"
DEFAULT_PERSISTENCE_DIRECTORY = "persisted_data"


NOT_WHITELIST_WARNING = "Starting the LWR without a toolbox to white-list." + \
                        "Ensure this application is protected by firewall or a configured private token."


def app_factory(global_conf, **local_conf):
    """
    Returns the LWR WSGI application.
    """
    webapp = LwrApp(global_conf=global_conf, **local_conf)
    atexit.register(webapp.shutdown)
    return webapp


class LwrApp(RoutingApp):
    """
    Central application logic for LWR server.
    """

    def __init__(self, **conf):
        if conf is None:
            conf = {}
        RoutingApp.__init__(self)
        self.__setup_staging_directory(conf.get("staging_directory", DEFAULT_STAGING_DIRECTORY))
        self.__setup_private_key(conf.get("private_key", DEFAULT_PRIVATE_KEY))
        self.__setup_persistence_directory(conf.get("persistence_directory", None))
        self.__setup_tool_config(conf)
        self.__setup_object_store(conf)
        self.__setup_dependency_manager(conf)
        self.__setup_managers(conf)
        self.__setup_file_cache(conf)
        self.__setup_routes()

    def shutdown(self):
        for manager in self.managers.values():
            try:
                manager.shutdown()
            except:
                pass

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

    def __setup_private_key(self, private_key):
        self.private_key = private_key
        if private_key:
            log.info("Securing LWR web app with private key, please verify you are using HTTPS so key cannot be obtained by monitoring traffic.")

    def __setup_routes(self):
        for func_name, func in inspect.getmembers(lwr.routes, lambda x: getattr(x, '__controller__', False)):
            self.__add_route_for_function(func)

    def __setup_persistence_directory(self, persistence_directory):
        self.persistence_directory = persistence_directory or DEFAULT_PERSISTENCE_DIRECTORY

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
        self.dependency_manager = DependencyManager(dependencies_dir, resolvers_config_file)

    def __add_route_for_function(self, function):
        route_suffix = '/%s' % function.__name__
        # Default or old-style route without explicit manager specified,
        # will be routed to manager '_default_'.
        default_manager_route = route_suffix
        self.add_route(default_manager_route, function)
        # Add route for named manager as well.
        named_manager_route = '/managers/{manager_name}%s' % route_suffix
        self.add_route(named_manager_route, function)
