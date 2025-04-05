import atexit
import inspect
import logging
import os

import pulsar.web.routes
from pulsar.core import PulsarApp
from pulsar.main import load_app_configuration
from pulsar.web.framework import RoutingApp

log = logging.getLogger(__name__)


def app_factory(global_conf=None, **local_conf):
    """
    Returns the Pulsar WSGI application.
    """
    if global_conf:
        configuration_file = global_conf.get("__file__")
    else:
        configuration_file = os.environ.get("PULSAR_CONFIG_FILE")
    webapp = init_webapp(ini_path=configuration_file, local_conf=local_conf)
    return webapp


def init_webapp(**config_kwds):
    app_conf = load_app_configuration(**config_kwds)
    pulsar_app = PulsarApp(**app_conf)
    webapp = PulsarWebApp(pulsar_app=pulsar_app)
    atexit.register(webapp.shutdown)
    return webapp


class PulsarWebApp(RoutingApp):
    """
    Web application for Pulsar web server.
    """

    def __init__(self, pulsar_app):
        super().__init__()
        self.pulsar_app = pulsar_app
        self.__setup_routes()

    def __setup_routes(self):
        for func_name, func in inspect.getmembers(pulsar.web.routes, lambda x: getattr(x, '__controller__', False)):
            self.__add_route_for_function(func)

    def __add_route_for_function(self, function):
        path = function.__path__
        method = function.__method__

        # Default or old-style route without explicit manager specified,
        # will be routed to manager '_default_'.
        default_manager_route = path
        self.add_route(default_manager_route, method, function)
        # Add route for named manager as well.
        named_manager_route = '/managers/{manager_name}%s' % path
        self.add_route(named_manager_route, method, function)

    def __getattr__(self, name):
        return getattr(self.pulsar_app, name)
