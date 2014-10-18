import subprocess
import logging
log = logging.getLogger(__name__)


def rsync_get_file(uri_from, uri_to, user, host, port, key):
    cmd = [
        'rsync',
        '-e',
        'ssh -i %s -p %s -o StrictHostKeyChecking=no' % (key, port),
        '%s@%s:%s' % (user, host, uri_from),
        uri_to,
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("Rsync exited with code %s" % exit_code)


def rsync_post_file(uri_from, uri_to, user, host, port, key):
    cmd = [
        'rsync',
        '-e',
        'ssh -i %s -p %s -o StrictHostKeyChecking=no' % (key, port),
        uri_from,
        '%s@%s:%s' % (user, host, uri_to),
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("Rsync exited with code %s" % exit_code)


def scp_get_file(uri_from, uri_to, user, host, port, key):
    cmd = [
        'scp',
        '-P', str(port),
        '-i', key,
        '-o', 'StrictHostKeyChecking=no',
        '%s@%s:%s' % (user, host, uri_from),
        uri_to,
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("scp exited with code %s" % exit_code)


def scp_post_file(uri_from, uri_to, user, host, port, key):
    cmd = [
        'scp',
        '-P', str(port),
        '-i', key,
        '-o', 'StrictHostKeyChecking=no',
        uri_from,
        '%s@%s:%s' % (user, host, uri_to),
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("scp exited with code %s" % exit_code)


___all__ = [rsync_post_file, rsync_get_file, scp_post_file, scp_get_file]
