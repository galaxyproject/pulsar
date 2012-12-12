import os
import platform
import subprocess
import time
import posixpath
from collections import deque


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
            subprocess.Popen("taskkill /F /T /PID %i" % pid, shell=True)
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


def get_mapped_file(directory, remote_path, allow_nested_files=False, local_path_module=os.path):
    """

    >>> import ntpath
    >>> get_mapped_file(r'C:\\lwr\\staging\\101', 'dataset_1_files/moo/cow', allow_nested_files=True, local_path_module=ntpath)
    'C:\\\\lwr\\\\staging\\\\101\\\\dataset_1_files\\\\moo\\\\cow'
    >>> get_mapped_file(r'C:\\lwr\\staging\\101', 'dataset_1_files/moo/cow', allow_nested_files=False, local_path_module=ntpath)
    'C:\\\\lwr\\\\staging\\\\101\\\\cow'
    >>> get_mapped_file(r'C:\\lwr\\staging\\101', '../cow', allow_nested_files=True, local_path_module=ntpath)
    Traceback (most recent call last):
    Exception: Invalid remote_path attempt to write files outside valid directory.
    """
    if not allow_nested_files:
        name = local_path_module.basename(remote_path)
        path = local_path_module.join(directory, name)
    else:
        local_rel_path = __posix_to_local_path(remote_path, local_path_module=local_path_module)
        local_path = local_path_module.join(directory, local_rel_path)
        if not __is_in_directory(local_path, directory, local_path_module=local_path_module):
            raise Exception("Invalid remote_path attempt to write files outside valid directory.")
        local_directory = local_path_module.dirname(local_path)
        if not local_path_module.exists(local_directory):
            os.makedirs(local_directory)
        path = local_path
    return path


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
