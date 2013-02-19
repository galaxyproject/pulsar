"""
"""
import atexit
import inspect
import os

from lwr.manager_factory import build_managers
from lwr.persistence import PersistedJobStore
from lwr.framework import RoutingApp
import lwr.routes


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
        self.private_key = None
        self.staging_directory = os.path.abspath(conf.get('staging_directory', "lwr_staging"))
        self.__setup_private_key(conf.get("private_key", None))
        self.persisted_job_store = PersistedJobStore(**conf)
        self.managers = build_managers(self, conf.get("job_managers_config", None))
        self.__setup_routes()

    def shutdown(self):
        for manager in self.managers.values():
            try:
                manager.shutdown()
            except:
                pass

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

    def __setup_private_key(self, private_key):
        if not private_key:
            return
        print "Securing LWR web app with private key, please verify you are using HTTPS so key cannot be obtained by monitoring traffic."
        self.private_key = private_key
