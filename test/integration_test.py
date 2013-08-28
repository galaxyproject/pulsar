from .test_utils import TestCase

from lwr.util import Bunch
from .check import run


class IntegrationTest(TestCase):

    def test_integration_cached(self):
        self.__run(private_token=None, transport=None, cache=True, test_errors=False)

    def test_integration_default(self):
        self.__run(private_token=None, transport=None, cache=False, test_errors=False)

    def test_integration_curl(self):
        self.__run(private_token=None, transport="curl", cache=False, test_errors=False)

    def test_integration_token(self):
        self.__run(app_conf={"private_key": "testtoken"}, private_token="testtoken", transport="curl", cache=False, test_errors=False)

    def test_integration_errors(self):
        self.__run(app_conf={"private_key": "testtoken"}, private_token="testtoken", transport="curl", cache=False, test_errors=True)

    def __run(self, app_conf={}, **kwds):
        from .test_utils import test_server
        with test_server(app_conf=app_conf) as server:
            options = Bunch(url=server.application_url, **kwds)
            run(options)
