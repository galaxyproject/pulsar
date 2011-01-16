from webob import Request
from webob import Response
from webob import exc

import inspect

from simplejson import dumps

class RoutingApp(object):
    def __init__(self):
        self.routes = []

    def add_route(self, route, controller, **args):
        self.routes.append((route, controller, args))

    def __call__(self, environ, start_response):
        req = Request(environ)
        for route, controller, args in self.routes:
            if route == req.path_info:
                return controller(environ, start_response, **args)
        return exc.HTTPNotFound()(environ, start_response)

class Controller:
    
    def __init__(self, response_type = 'OK'):
        self.response_type = response_type

    def __call__(self, func):
        def controller_replacement(environ, start_response, **args):
            req = Request(environ)
            func_args = inspect.getargspec(func).args
            for func_arg in func_args:
                if func_arg not in args and func_arg in req.GET:
                    args[func_arg] = req.GET[func_arg]
            if 'body' in func_args:
                args['body'] = req.body_file
            try:
                result = func(**args)
            except exc.HTTPException, e:
                result = e
            if self.response_type == 'json':
                resp = Response(body=dumps(result))
            elif self.response_type == 'file':
                resp = Response()
                resp.app_iter = FileIterator(result)
            else:
                resp = Response(body='OK')    
            return resp(environ, start_response)
        controller_replacement.__name__ = func.__name__
        return controller_replacement

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

