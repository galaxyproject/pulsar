from unittest import TestCase

from lwr.util import Bunch
from .check import run


class IntegrationTest(TestCase):

    def test_integration_cached(self):
        self.__run(private_token=None, transport=None, cache=True, test_errors=False)

    def test_integration_default(self):
        self.__run(private_token=None, transport=None, cache=False, test_errors=False)

    def test_integration_curl(self):
        self.__run(private_token=None, transport="curl", cache=False, test_errors=False)

    def __run(self, **kwds):
        from test_utils import test_server
        with test_server() as server:
            options = Bunch(url=server.application_url, **kwds)
            run(options)
