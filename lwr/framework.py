"""
Tiny framework used to power LWR application, nothing in here is specific to running
or staging jobs. Mostly deals with routing web traffic and parsing parameters.
"""
from webob import Request
from webob import Response
from webob import exc

import inspect
from os.path import exists
import re

from simplejson import dumps


class RoutingApp(object):
    """
    Abstract definition for a python web application.
    """
    def __init__(self):
        self.routes = []

    def add_route(self, route, controller, **args):
        route_regex = self.__template_to_regex(route)
        self.routes.append((route_regex, controller, args))

    def __call__(self, environ, start_response):
        req = Request(environ)
        req.app = self
        for route, controller, args in self.routes:
            match = route.match(req.path_info)
            if match:
                request_args = dict(args)
                route_args = match.groupdict()
                request_args.update(route_args)
                return controller(environ, start_response, **request_args)
        return exc.HTTPNotFound()(environ, start_response)

    def __template_to_regex(self, template):
        var_regex = re.compile(r'''
            \{          # The exact character "{"
            (\w+)       # The variable name (restricted to a-z, 0-9, _)
            (?::([^}]+))? # The optional :regex part
            \}          # The exact character "}"
           ''', re.VERBOSE)
        regex = ''
        last_pos = 0
        for match in var_regex.finditer(template):
            regex += re.escape(template[last_pos:match.start()])
            var_name = match.group(1)
            expr = match.group(2) or '[^/]+'
            expr = '(?P<%s>%s)' % (var_name, expr)
            regex += expr
            last_pos = match.end()
        regex += re.escape(template[last_pos:])
        regex = '^%s$' % regex
        return re.compile(regex)


class Controller(object):
    """
    Wraps python functions into controller methods.
    """

    def __init__(self, response_type='OK'):
        self.response_type = response_type

    def __get_client_address(self, environ):
        """
        http://stackoverflow.com/questions/7835030/obtaining-client-ip-address-from-a-wsgi-app-using-eventlet
        """
        try:
            return environ['HTTP_X_FORWARDED_FOR'].split(',')[-1].strip()
        except KeyError:
            return environ['REMOTE_ADDR']

    def __add_args(self, args, func_args, arg_values):
        for func_arg in func_args:
            if func_arg not in args and func_arg in arg_values:
                args[func_arg] = arg_values[func_arg]

    def __call__(self, func):
        def controller_replacement(environ, start_response, **args):
            req = Request(environ)

            if hasattr(self, '_check_access'):
                access_response = self._check_access(req, environ, start_response)
                if access_response:
                    return access_response

            func_args = inspect.getargspec(func).args
            self.__add_args(args, func_args, req.GET)
            self.__add_args(args, func_args, self._app_args(args, req))
            for func_arg in func_args:
                if func_arg == "ip":
                    args[func_arg] = self.__get_client_address(environ)

            for key in dict(args):
                if key not in func_args:
                    del args[key]

            if 'body' in func_args:
                args['body'] = req.body_file
            try:
                result = func(**args)
            except exc.HTTPException as e:
                result = e
            if self.response_type == 'json':
                resp = Response(body=dumps(result))
            elif self.response_type == 'file':
                resp = Response()
                path = result
                if exists(path):
                    resp.app_iter = FileIterator(path)
                else:
                    raise exc.HTTPNotFound("No file found with path %s." % path)
            else:
                resp = Response(body='OK')
            return resp(environ, start_response)
        controller_replacement.__name__ = func.__name__
        controller_replacement.__controller__ = True
        return controller_replacement

    def _prepare_controller_args(self, req, args):
        pass


class FileIterator:

    def __init__(self, path):
        self.input = open(path, 'rb')

    def __iter__(self):
        return self

    def next(self):
        buffer = self.input.read(1024)
        if(buffer == ""):
            raise StopIteration
        return buffer
