import os
import platform
import posixpath
from shutil import move, rmtree
from subprocess import Popen
from collections import deque
from tempfile import NamedTemporaryFile
from datetime import datetime

from logging import getLogger
log = getLogger(__name__)

BUFFER_SIZE = 4096


def enum(**enums):
    """
    http://stackoverflow.com/questions/36932/how-can-i-represent-an-enum-in-python
    """
    return type('Enum', (), enums)


def copy_to_path(object, path):
    """
    Copy file-like object to path.
    """
    output = open(path, 'wb')
    _copy_and_close(object, output)


def _copy_and_close(object, output):
    try:
        while True:
            buffer = object.read(BUFFER_SIZE)
            if buffer == "":
                break
            output.write(buffer)
    finally:
        output.close()


def copy_to_temp(object):
    """
    Copy file-like object to temp file and return
    path.
    """
    temp_file = NamedTemporaryFile(delete=False)
    _copy_and_close(object, temp_file)
    return temp_file.name


def atomicish_move(source, destination, tmp_suffix="_TMP"):
    """
    Move source to destination without copying to directly to destination
    there is never a partial file.

    > from tempfile import mkdtemp
    > from os.path import join, exists
    > temp_dir = mkdtemp()
    > source = join(temp_dir, "the_source")
    > destination = join(temp_dir, "the_dest")
    > open(source, "w").write("Hello World!")
    > assert exists(source)
    > assert not exists(destination)
    > atomicish_move(source, destination)
    > assert not exists(source)
    > assert exists(destination)
    """
    destination_dir = os.path.dirname(destination)
    destination_name = os.path.basename(destination)
    temp_destination = os.path.join(destination_dir, "%s%s" % (destination_name, tmp_suffix))
    move(source, temp_destination)
    os.rename(temp_destination, destination)


class JobDirectory(object):

    def __init__(self, staging_directory, job_id):
        # Make sure job_id is clean, not a path hacking attempt
        assert job_id == os.path.basename(job_id)
        self.job_directory = os.path.join(staging_directory, job_id)

    def _sub_dir(self, name):
        return os.path.join(self.job_directory, name)

    def working_directory(self):
        return self._sub_dir('working')

    def inputs_directory(self):
        return self._sub_dir('inputs')

    def outputs_directory(self):
        return self._sub_dir('outputs')

    def configs_directory(self):
        return self._sub_dir('configs')

    def tool_files_directory(self):
        return self._sub_dir('tool_files')

    def _job_file(self, name):
        return os.path.join(self.job_directory, name)

    @property
    def path(self):
        return self.job_directory

    def read_file(self, name, default=None):
        path = self._job_file(name)
        job_file = None
        try:
            job_file = open(path, 'r')
            return job_file.read()
        except:
            if default is not None:
                return default
            else:
                raise
        finally:
            if job_file:
                job_file.close()

    def write_file(self, name, contents):
        path = self._job_file(name)
        job_file = open(path, 'w')
        try:
            job_file.write(contents)
        finally:
            job_file.close()
        return path

    def remove_file(self, name):
        """
        Quietly remove a job file.
        """
        try:
            os.remove(self._job_file(name))
        except OSError:
            pass

    def contains_file(self, name):
        return os.path.exists(self._job_file(name))

    def open_file(self, name, mode='w'):
        return open(self._job_file(name), mode)

    def exists(self):
        return os.path.exists(self.path)

    def delete(self):
        return rmtree(self.path)

    def setup(self):
        os.mkdir(self.job_directory)

    def make_directory(self, name):
        path = self._job_file(name)
        os.mkdir(path)


def execute(command_line, working_directory, stdout, stderr):
    preexec_fn = None
    if not (platform.system() == 'Windows'):
        preexec_fn = os.setpgrp
    proc = Popen(args=command_line,
                 shell=True,
                 cwd=working_directory,
                 stdout=stdout,
                 stderr=stderr,
                 preexec_fn=preexec_fn)
    return proc


def get_mapped_file(directory, remote_path, allow_nested_files=False, local_path_module=os.path, mkdir=True):
    """

    >>> import ntpath
    >>> get_mapped_file(r'C:\\lwr\\staging\\101', 'dataset_1_files/moo/cow', allow_nested_files=True, local_path_module=ntpath, mkdir=False)
    'C:\\\\lwr\\\\staging\\\\101\\\\dataset_1_files\\\\moo\\\\cow'
    >>> get_mapped_file(r'C:\\lwr\\staging\\101', 'dataset_1_files/moo/cow', allow_nested_files=False, local_path_module=ntpath)
    'C:\\\\lwr\\\\staging\\\\101\\\\cow'
    >>> get_mapped_file(r'C:\\lwr\\staging\\101', '../cow', allow_nested_files=True, local_path_module=ntpath, mkdir=False)
    Traceback (most recent call last):
    Exception: Attempt to read or write file outside an authorized directory.
    """
    if not allow_nested_files:
        name = local_path_module.basename(remote_path)
        path = local_path_module.join(directory, name)
    else:
        local_rel_path = __posix_to_local_path(remote_path, local_path_module=local_path_module)
        local_path = local_path_module.join(directory, local_rel_path)
        verify_is_in_directory(local_path, directory, local_path_module=local_path_module)
        local_directory = local_path_module.dirname(local_path)
        if mkdir and not local_path_module.exists(local_directory):
            os.makedirs(local_directory)
        path = local_path
    return path


def verify_is_in_directory(path, directory, local_path_module=os.path):
    if not is_in_directory(path, directory, local_path_module):
        msg = "Attempt to read or write file outside an authorized directory."
        log.warn("%s Attempted path: %s, valid directory: %s" % (msg, path, directory))
        raise Exception(msg)


def __posix_to_local_path(path, local_path_module=os.path):
    """
    Converts a posix path (coming from Galaxy), to a local path (be it posix or Windows).

    >>> import ntpath
    >>> __posix_to_local_path('dataset_1_files/moo/cow', local_path_module=ntpath)
    'dataset_1_files\\\\moo\\\\cow'
    >>> import posixpath
    >>> __posix_to_local_path('dataset_1_files/moo/cow', local_path_module=posixpath)
    'dataset_1_files/moo/cow'
    """
    partial_path = deque()
    while True:
        if not path or path == '/':
            break
        (path, base) = posixpath.split(path)
        partial_path.appendleft(base)
    return local_path_module.join(*partial_path)


def is_in_directory(file, directory, local_path_module=os.path):
    """
    Return true, if the common prefix of both is equal to directory
    e.g. /a/b/c/d.rst and directory is /a/b, the common prefix is /a/b

    Heavily inspired by similar method in from Galaxy's BaseJobRunner class.
    """

    # Make both absolute.
    directory = local_path_module.abspath(directory)
    file = local_path_module.abspath(file)
    return local_path_module.commonprefix([file, directory]) == directory


class Bunch(object):
    """
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52308

    Often we want to just collect a bunch of stuff together, naming each item of
    the bunch; a dictionary's OK for that, but a small do-nothing class is even handier, and prettier to use.
    """
    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def get(self, key, default=None):
        return self.__dict__.get(key, default)

    def __iter__(self):
        return iter(self.__dict__)

    def items(self):
        return self.__dict__.items()

    def __str__(self):
        return '%s' % self.__dict__

    def __nonzero__(self):
        return bool(self.__dict__)

    def __bool__(self):
        return bool(self.__dict__)

    def __setitem__(self, k, v):
        self.__dict__.__setitem__(k, v)


class Time:
    """ Time utilities of now that can be instrumented for testing."""

    @classmethod
    def now(cls):
        return datetime.utcnow()
