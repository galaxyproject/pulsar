import subprocess
import os

SSH_OPTIONS = ['-o', 'StrictHostKeyChecking=no', '-o', 'PreferredAuthentications=publickey', '-o', 'PubkeyAuthentication=yes']


def rsync_get_file(uri_from, uri_to, user, host, port, key):
    cmd = [
        'rsync',
        '-e',
        'ssh -i %s -p %s %s' % (key, port, ' '.join(SSH_OPTIONS)),
        '%s@%s:%s' % (user, host, uri_from),
        uri_to,
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("Rsync exited with code %s" % exit_code)


def rsync_post_file(uri_from, uri_to, user, host, port, key):
    directory = os.path.dirname(uri_to)
    cmd = [
        'ssh',
        '-i',
        key,
        '-p',
        str(port),
    ] + SSH_OPTIONS + [
        '%s@%s' % (user, host),
        'mkdir',
        '-p',
        directory,
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("ssh exited with code %s" % exit_code)
    cmd = [
        'rsync',
        '-e',
        'ssh -i %s -p %s %s' % (key, port, ' '.join(SSH_OPTIONS)),
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
        '-i', key
    ] + SSH_OPTIONS + [
        '%s@%s:%s' % (user, host, uri_from),
        uri_to,
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("scp exited with code %s" % exit_code)


def scp_post_file(uri_from, uri_to, user, host, port, key):
    directory = os.path.dirname(uri_to)
    cmd = [
        'ssh',
        '-i',
        key,
        '-p',
        str(port),
    ] + SSH_OPTIONS + [
        '%s@%s' % (user, host),
        'mkdir',
        '-p',
        directory,
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("ssh exited with code %s" % exit_code)
    cmd = [
        'scp',
        '-P', str(port),
        '-i', key,
    ] + SSH_OPTIONS + [
        uri_from,
        '%s@%s:%s' % (user, host, uri_to),
    ]
    exit_code = subprocess.check_call(cmd)
    if exit_code != 0:
        raise Exception("scp exited with code %s" % exit_code)


___all__ = [
    'rsync_post_file',
    'rsync_get_file',
    'scp_post_file',
    'scp_get_file'
]
