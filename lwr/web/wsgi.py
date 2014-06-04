import atexit
import inspect

from lwr.core import LwrApp
from lwr.web.framework import RoutingApp

import lwr.web.routes


def app_factory(global_conf, **local_conf):
    """
    Returns the LWR WSGI application.
    """
    lwr_app = LwrApp(global_conf=global_conf, **local_conf)
    webapp = LwrWebApp(lwr_app=lwr_app)
    atexit.register(webapp.shutdown)
    return webapp


class LwrWebApp(RoutingApp):
    """
    Web application for LWR web server.
    """

    def __init__(self, lwr_app):
        super(LwrWebApp, self).__init__()
        self.lwr_app = lwr_app
        self.__setup_routes()

    def __setup_routes(self):
        for func_name, func in inspect.getmembers(lwr.web.routes, lambda x: getattr(x, '__controller__', False)):
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

    def __getattr__(self, name):
        return getattr(self.lwr_app, name)
