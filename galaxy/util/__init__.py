"""
This file is a mess, it is a merge of random stuff that is in galaxy.util and
stuff that was in lwr.util. This should be reworked to only contain stuff in
galaxy.util and the rest should be moved into galaxy.util.lwr_io or something
like that.
"""
import os
import platform
import stat
try:
    import grp
except ImportError:
    grp = None
import errno
from shutil import move
from subprocess import Popen
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
            if not buffer:
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
    > open(source, "wb").write(b"Hello World!")
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


def verify_is_in_directory(path, directory, local_path_module=os.path):
    if not is_in_directory(path, directory, local_path_module):
        msg = "Attempt to read or write file outside an authorized directory."
        log.warn("%s Attempted path: %s, valid directory: %s" % (msg, path, directory))
        raise Exception(msg)


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


in_directory = is_in_directory  # For compat. w/Galaxy.


def umask_fix_perms(path, umask, unmasked_perms, gid=None):
    """
    umask-friendly permissions fixing
    """
    perms = unmasked_perms & ~umask
    try:
        st = os.stat(path)
    except OSError, e:
        log.exception('Unable to set permissions or group on %s' % path)
        return
    # fix modes
    if stat.S_IMODE(st.st_mode) != perms:
        try:
            os.chmod(path, perms)
        except Exception, e:
            log.warning('Unable to honor umask (%s) for %s, tried to set: %s but mode remains %s, error was: %s' % (oct(umask),
                                                                                                                    path,
                                                                                                                    oct(perms),
                                                                                                                    oct(stat.S_IMODE(st.st_mode)),
                                                                                                                    e))
    # fix group
    if gid is not None and st.st_gid != gid:
        try:
            os.chown(path, -1, gid)
        except Exception, e:
            try:
                desired_group = grp.getgrgid(gid)
                current_group = grp.getgrgid(st.st_gid)
            except:
                desired_group = gid
                current_group = st.st_gid
            log.warning('Unable to honor primary group (%s) for %s, group remains %s, error was: %s' % (desired_group,
                                                                                                        path,
                                                                                                        current_group,
                                                                                                        e))


def xml_text(root, name=None):
    """Returns the text inside an element"""
    if name is not None:
        # Try attribute first
        val = root.get(name)
        if val:
            return val
        # Then try as element
        elem = root.find(name)
    else:
        elem = root
    if elem is not None and elem.text:
        text = ''.join(elem.text.splitlines())
        return text.strip()
    # No luck, return empty string
    return ''


def force_symlink(source, link_name):
    try:
        os.symlink(source, link_name)
    except OSError, e:
        if e.errno == errno.EEXIST:
            os.remove(link_name)
            os.symlink(source, link_name)
        else:
            raise e


class Time:
    """ Time utilities of now that can be instrumented for testing."""

    @classmethod
    def now(cls):
        return datetime.utcnow()
