from os import remove
from os.path import exists
from tempfile import mkdtemp, NamedTemporaryFile
from unittest import TestCase

from lwr.cache import Cache
from shutil import rmtree


class CacheTest(TestCase):

    def setUp(self):
        self.temp_dir = mkdtemp()
        self.temp_file = NamedTemporaryFile(delete=False)
        self.temp_file.write("Hello World!")
        self.temp_file.close()
        self.cache = Cache(self.temp_dir)

    def tearDown(self):
        rmtree(self.temp_dir)
        if exists(self.temp_file.name):
            remove(self.temp_file.name)

    def test_same_token_for_same_inputs(self):
        cache = self.cache
        cache_response_1 = cache.get_cache_token("127.0.0.2", "/galaxy/dataset10000.dat")
        cache_response_2 = cache.get_cache_token("127.0.0.2", "/galaxy/dataset10000.dat")
        assert cache_response_1["token"] == cache_response_2["token"]

    def test_inserted_only_once(self):
        cache = self.cache
        cache_response_1 = cache.get_cache_token("127.0.0.2", "/galaxy/dataset10001.dat")
        cache_response_2 = cache.get_cache_token("127.0.0.2", "/galaxy/dataset10001.dat")
        assert cache_response_1["inserted"]
        assert not cache_response_2["inserted"]

    def test_making_file_available(self):
        cache = self.cache
        assert not cache.file_available("127.0.0.2", "/galaxy/dataset10001.dat")
        cache.cache_file(self.temp_file.name, "127.0.0.2", "/galaxy/dataset10001.dat")
        assert cache.file_available("127.0.0.2", "/galaxy/dataset10001.dat")
