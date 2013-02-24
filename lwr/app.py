"""
"""
import atexit
import inspect
import os

from lwr.manager_factory import build_managers
from lwr.persistence import PersistedJobStore
from lwr.framework import RoutingApp
from lwr.tools import ToolBox
from lwr.tools.authorization import get_authorizer
import lwr.routes

from logging import getLogger
log = getLogger(__name__)


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
        RoutingApp.__init__(self)
        self.__setup_staging_directory(conf.get('staging_directory', "lwr_staging"))
        self.__setup_private_key(conf.get("private_key", None))
        self.__setup_persisted_job_store(conf)
        self.__setup_tool_config(conf.get("toolbox_path", None))
        self.__setup_managers(conf.get("job_managers_config", None))
        self.__setup_routes()

    def shutdown(self):
        for manager in self.managers.values():
            try:
                manager.shutdown()
            except:
                pass

    def __setup_tool_config(self, toolbox_path):
        """
        Setups toolbox object and authorization mechanism based
        on supplied toolbox_path.
        """
        toolbox = None
        if toolbox_path:
            toolbox = ToolBox(toolbox_path)
        else:
            log.info("Starting the LWR without a toolbox to white-list tools with, please ensure this application is protected by firewall or a configured private token.")
        self.toolbox = toolbox
        self.authorizer = get_authorizer(toolbox)

    def __setup_staging_directory(self, staging_directory):
        self.staging_directory = os.path.abspath(staging_directory)

    def __setup_persisted_job_store(self, conf):
        self.persisted_job_store = PersistedJobStore(**conf)

    def __setup_managers(self, job_managers_config):
        self.managers = build_managers(self, job_managers_config)

    def __setup_private_key(self, private_key):
        self.private_key = private_key
        if private_key:
            print "Securing LWR web app with private key, please verify you are using HTTPS so key cannot be obtained by monitoring traffic."

    def __setup_routes(self):
        for func_name, func in inspect.getmembers(lwr.routes, lambda x: getattr(x, '__controller__', False)):
            self.__add_route_for_function(func)

    def __add_route_for_function(self, function):
        route_suffix = '/%s' % function.__name__
        # Default or old-style route without explicit manager specified,
        # will be routed to manager '_default_'.
        default_manager_route = route_suffix
        self.add_route(default_manager_route, function)
        # Add route for named manager as well.
        named_manager_route = '/managers/{manager_name}%s' % route_suffix
        self.add_route(named_manager_route, function)
