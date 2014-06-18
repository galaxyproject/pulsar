from abc import ABCMeta
from abc import abstractmethod
from string import Template

try:
    from StringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO
try:
    from six import text_type
except ImportError:
    from galaxy.util import unicodify as text_type
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode


class LwrInteface(object):
    """
    Abstract base class describes how synchronous client communicates with
    (potentially remote) LWR procedures. Obvious implementation is HTTP based
    but LWR objects wrapped in routes can also be directly communicated with
    if in memory.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def execute(self, command, args={}, data=None, input_path=None, output_path=None):
        """
        Execute the correspond command against configured LWR job manager. Arguments are
        method parameters and data or input_path describe essentially POST bodies. If command
        results in a file, resulting path should be specified as output_path.
        """


COMMAND_TO_PATH = {
    "path": Template("jobs/${job_id}/files/path"),
    "upload_file": Template("jobs/${job_id}/files"),
    "download_output": Template("jobs/${job_id}/files"),

    "file_available": Template("cache/status"),
    "cache_required": Template("cache"),
    "cache_insert": Template("cache"),

    "object_store_exists": Template("objects/${object_id}/exists"),
    "object_store_file_ready": Template("objects/${object_id}/file_ready"),
    "object_store_update_from_file": Template("objects/${object_id}"),
    "object_store_create": Template("objects/${object_id}"),
    "object_store_empty": Template("objects/${object_id}/empty"),
    "object_store_size": Template("objects/${object_id}/size"),
    "object_store_delete": Template("objects/${object_id}"),
    "object_store_get_data": Template("objects/${object_id}"),
    "object_store_get_filename": Template("objects/${object_id}/filename"),
    "object_store_get_store_usage_percent": Template("object_store_usage_percent")
}

COMMAND_TO_METHOD = {
    "upload_file": "POST",
    "download_output": "GET",

    "object_store_update_from_file": "PUT",
    "object_store_create": "POST",
    "object_store_delete": "DELETE",

    "file_available": "GET",
    "cache_required": "PUT",
    "cache_insert": "POST",
}


class HttpLwrInterface(LwrInteface):

    def __init__(self, destination_params, transport):
        self.transport = transport
        remote_host = destination_params.get("url")
        assert remote_host is not None, "Failed to determine url for LWR client."
        if not remote_host.endswith("/"):
            remote_host = "%s/" % remote_host
        if not remote_host.startswith("http"):
            remote_host = "http://%s" % remote_host
        self.remote_host = remote_host
        self.private_key = destination_params.get("private_token", None)

    def execute(self, command, args={}, data=None, input_path=None, output_path=None):
        url = self.__build_url(command, args)
        method = COMMAND_TO_METHOD.get(command, None)  # Default to GET is no data, POST otherwise
        response = self.transport.execute(url, method=method, data=data, input_path=input_path, output_path=output_path)
        return response

    def __build_url(self, command, args):
        path = COMMAND_TO_PATH.get(command, Template(command)).safe_substitute(args)
        if self.private_key:
            args["private_key"] = self.private_key
        arg_bytes = dict([(k, text_type(args[k]).encode('utf-8')) for k in args])
        data = urlencode(arg_bytes)
        url = self.remote_host + path + "?" + data
        return url


class LocalLwrInterface(LwrInteface):

    def __init__(self, destination_params, job_manager=None, file_cache=None, object_store=None):
        self.job_manager = job_manager
        self.file_cache = file_cache
        self.object_store = object_store

    def __app_args(self):
        # Arguments that would be specified from LwrApp if running
        # in web server.
        return {
            'manager': self.job_manager,
            'file_cache': self.file_cache,
            'object_store': self.object_store,
            'ip': None
        }

    def execute(self, command, args={}, data=None, input_path=None, output_path=None):
        # If data set, should be unicode (on Python 2) or str (on Python 3).
        from lwr.web import routes
        from lwr.web.framework import build_func_args
        controller = getattr(routes, command)
        action = controller.func
        body_args = dict(body=self.__build_body(data, input_path))
        args = build_func_args(action, args.copy(), self.__app_args(), body_args)
        result = action(**args)
        if controller.response_type != 'file':
            return controller.body(result)
        else:
            # TODO: Add to Galaxy.
            from galaxy.util import copy_to_path
            with open(result, 'rb') as result_file:
                copy_to_path(result_file, output_path)

    def __build_body(self, data, input_path):
        if data is not None:
            return BytesIO(data.encode('utf-8'))
        elif input_path is not None:
            return open(input_path, 'rb')
        else:
            return None
