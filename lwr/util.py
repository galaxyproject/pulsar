import os
import platform
import subprocess
import time
import posixpath
from subprocess import Popen
from collections import deque

from logging import getLogger
log = getLogger(__name__)

BUFFER_SIZE = 4096


def kill_pid(pid):
    def __check_pid():
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    is_windows = platform.system() == 'Windows'

    if is_windows:
        try:
            Popen("taskkill /F /T /PID %i" % pid, shell=True)
        except Exception:
            pass
    else:
        if __check_pid():
            for sig in [15, 9]:
                try:
                    os.killpg(pid, sig)
                except OSError:
                    return
                time.sleep(1)
                if not __check_pid():
                    return


def copy_to_path(object, path):
    """
    Copy file-like object to path.
    """
    output = open(path, 'wb')
    try:
        while True:
            buffer = object.read(BUFFER_SIZE)
            if buffer == "":
                break
            output.write(buffer)
    finally:
        output.close()


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

    def __job_file(self, name):
        return os.path.join(self.job_directory, name)

    @property
    def path(self):
        return self.job_directory

    def read_file(self, name):
        path = self.__job_file(name)
        job_file = open(path, 'r')
        try:
            return job_file.read()
        finally:
            job_file.close()

    def write_file(self, name, contents):
        path = self.__job_file(name)
        job_file = open(path, 'w')
        try:
            job_file.write(contents)
        finally:
            job_file.close()

    def remove_file(self, name):
        """
        Quietly remove a job file.
        """
        try:
            os.remove(self.__job_file(name))
        except OSError:
            pass

    def contains_file(self, name):
        return os.path.exists(self.__job_file(name))

    def open_file(self, name, mode='w'):
        return open(self.__job_file(name), mode)

    def setup(self):
        os.mkdir(self.job_directory)

    def make_directory(self, name):
        path = self.__job_file(name)
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
    if not __is_in_directory(path, directory, local_path_module):
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


def __is_in_directory(file, directory, local_path_module=os.path):
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

    def __setitem__(self, k, v):
        self.__dict__.__setitem__(k, v)
