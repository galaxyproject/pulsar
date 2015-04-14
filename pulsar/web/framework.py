"""
Tiny framework used to power Pulsar application, nothing in here is specific to running
or staging jobs. Mostly deals with routing web traffic and parsing parameters.
"""
from webob import Request
from webob import Response
from webob import exc

import inspect
from os.path import exists
import re

from pulsar.client.util import json_dumps
from six import Iterator


class RoutingApp(object):
    """
    Abstract definition for a python web application.
    """
    def __init__(self):
        self.routes = []

    def add_route(self, route, method, controller, **args):
        route_regex = self.__template_to_regex(route)
        self.routes.append((route_regex, method, controller, args))

    def __call__(self, environ, start_response):
        req = Request(environ)
        req.app = self
        for route, method, controller, args in self.routes:
            if method and not req.method == method:
                continue
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


def build_func_args(func, *arg_dicts):
    args = {}

    def add_args(func_args, arg_values):
        for func_arg in func_args:
            if func_arg not in args and func_arg in arg_values:
                args[func_arg] = arg_values[func_arg]

    func_args = inspect.getargspec(func).args
    for arg_dict in arg_dicts:
        add_args(func_args, arg_dict)

    return args


class Controller(object):
    """
    Wraps python functions into controller methods.
    """

    def __init__(self, method=None, path=None, response_type='OK'):
        self.method = method
        self.path = path
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

    def __handle_access(self, req, environ, start_response):
        access_response = None
        if hasattr(self, '_check_access'):
            access_response = self._check_access(req, environ, start_response)
        return access_response

    def __build_args(self, func, args, req, environ):
        args = build_func_args(func, args, req.GET, self._app_args(args, req))
        func_args = inspect.getargspec(func).args

        for func_arg in func_args:
            if func_arg == "ip":
                args["ip"] = self.__get_client_address(environ)

        if 'body' in func_args:
            args['body'] = req.body_file

        return args

    def __execute_request(self, func, args, req, environ):
        args = self.__build_args(func, args, req, environ)
        try:
            result = func(**args)
        except exc.HTTPException as e:
            result = e
        return result

    def __build_response(self, result):
        if self.response_type == 'file':
            resp = file_response(result)
        else:
            resp = Response(body=self.body(result))
        return resp

    def __call__(self, func):
        def controller_replacement(environ, start_response, **args):
            req = Request(environ)

            access_response = self.__handle_access(req, environ, start_response)
            if access_response:
                return access_response

            result = self.__execute_request(func, args, req, environ)
            resp = self.__build_response(result)

            return resp(environ, start_response)

        controller_replacement.func = func
        controller_replacement.response_type = self.response_type
        controller_replacement.body = self.body
        controller_replacement.__name__ = func.__name__
        controller_replacement.__controller__ = True
        controller_replacement.__method__ = self.method
        controller_replacement.__path__ = self.path or "/%s" % func.__name__
        return controller_replacement

    def body(self, result):
        body = 'OK'
        if self.response_type == 'json':
            body = json_dumps(result)
        return body

    def _prepare_controller_args(self, req, args):
        pass


def file_response(path):
    resp = Response()
    if exists(path):
        resp.app_iter = FileIterator(path)
    else:
        raise exc.HTTPNotFound("No file found with path %s." % path)
    return resp


class FileIterator(Iterator):

    def __init__(self, path):
        self.input = open(path, 'rb')

    def __iter__(self):
        return self

    def __next__(self):
        buffer = self.input.read(1024)
        if(buffer == b""):
            raise StopIteration
        return buffer
