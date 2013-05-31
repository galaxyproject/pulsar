
from os.path import join, exists
from hashlib import sha256

from lwr.persistence import PersistenceStore
from lwr.util import atomicish_move


class CacheFileMapper(object):

    def __init__(self, directory):
        self.directory = directory

    def get(self, token):
        return join(self.directory, token)


class Cache(PersistenceStore):
    """
    Maintain a cache of uploaded files.
    """

    def __init__(self, cache_directory="file_cache"):
        super(Cache, self).__init__(join(cache_directory, "cache_shelf"))
        self.file_mapper = CacheFileMapper(cache_directory)

    def cache_required(self, ip, path):
        token = self.__token(ip, path)

        def get_token():
            inserted = False
            if token not in self.shelf:
                self.shelf[token] = "cache/%s" % token
                inserted = True
            return inserted

        return self._with_lock(get_token)

    def cache_file(self, local_path, ip, path):
        """
        Move a file from a temporary staging area into the cache.
        """
        destination = self.__destination(ip, path)
        atomicish_move(local_path, destination)

    def file_available(self, ip, path):
        token = self.__token(ip, path)
        ready = exists(self.destination(token))
        return {"token": token, "ready": ready}

    def destination(self, token):
        return self.file_mapper.get(token)

    def __destination(self, ip, path):
        token = self.__token(ip, path)
        return self.destination(token)

    def __token(self, ip, path):
        return sha256("IP:%s:%s" % (ip, path)).hexdigest()


__all__ = [Cache]
