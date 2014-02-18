import os

from .test_utils import server_for_test_app
from .test_utils import temp_directory

import galaxy.util

import webob
import webtest
import contextlib

from lwr.lwr_client.action_mapper import RemoteTransferAction
from lwr.lwr_client.transport import curl
from lwr.framework import file_response


def app_factory(global_conf, **local_conf):
    return JobFilesApp()


class JobFilesApp(object):

    def __init__(self, root_directory=None):
        self.root_directory = root_directory

    def __call__(self, environ, start_response):
        req = webob.Request(environ)
        params = req.params.mixed()
        method = req.method
        if method == "POST":
            resp = self._post(req, params)
        elif method == "GET":
            resp = self._get(req, params)
        return resp(environ, start_response)

    def _post(self, request, params):
        path = params['path']
        assert galaxy.util.in_directory(path, self.root_directory)
        galaxy.util.copy_to_path(params["file"].file, path)
        return webob.Response(body='')

    def _get(self, request, params):
        path = params['path']
        assert galaxy.util.in_directory(path, self.root_directory)
        return file_response(path)


@contextlib.contextmanager
def files_server(directory=None):
    if not directory:
        with temp_directory() as directory:
            app = webtest.TestApp(JobFilesApp(directory))
            with server_for_test_app(app) as server:
                yield server, directory
    else:
        app = webtest.TestApp(JobFilesApp(directory))
        with server_for_test_app(app) as server:
            yield server


def test_write_to_file():
    with files_server() as (server, directory):
        from_path = os.path.join(directory, "remote_get")
        open(from_path, "wb").write(u"123456")

        to_path = os.path.join(directory, "local_get")
        url = server.application_url + "?path=%s" % from_path
        RemoteTransferAction(to_path, url=url).write_to_path(to_path)

        assert open(to_path, "rb").read() == u"123456"


def test_write_from_file():
    with files_server() as (server, directory):
        from_path = os.path.join(directory, "local_post")
        open(from_path, "wb").write(u"123456")

        to_path = os.path.join(directory, "remote_post")
        url = server.application_url + "?path=%s" % to_path
        RemoteTransferAction(to_path, url=url).write_from_path(from_path)

        posted_contents = open(to_path, "rb").read()
        assert posted_contents == u"123456",  posted_contents
