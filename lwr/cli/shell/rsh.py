"""
Interface for remote shell commands (rsh, rcp) and derivatives that use the
same syntax (ssh, scp).

Code stolen from Galaxy:
  - https://bitbucket.org/galaxy/galaxy-central/src/tip/lib/galaxy/jobs/runners/cli.py?at=default
"""
from time import sleep
from tempfile import TemporaryFile
from subprocess import Popen, PIPE

from lwr.util import Bunch, kill_pid

from logging import getLogger
log = getLogger(__name__)

__all__ = ('RemoteShell', 'SecureShell', 'GlobusSecureShell')


class RemoteShell(object):

    def __init__(self, rsh='rsh', rcp='rcp', hostname=None, username=None, **kwargs):
        self.rsh = rsh
        self.rcp = rcp
        self.hostname = hostname
        self.username = username
        self.sessions = {}

    def execute(self, cmd, persist=False, timeout=60):
        # TODO: implement persistence
        if self.username is None:
            fullcmd = '%s %s %s' % (self.rsh, self.hostname, cmd)
        else:
            fullcmd = '%s -l %s %s %s' % (self.rsh, self.username, self.hostname, cmd)
        # Read stdout to a tempfile in case it's large (>65K)
        outf = TemporaryFile()
        p = Popen(fullcmd, shell=True, stdin=None, stdout=outf, stderr=PIPE)
        # poll until timeout
        for i in range(timeout / 3):
            r = p.poll()
            if r is not None:
                break
            sleep(3)
        else:
            kill_pid(p.pid)
            return Bunch(stdout='', stderr='Execution timed out', returncode=-1)
        outf.seek(0)
        return Bunch(stdout=outf.read(), stderr=p.stderr.read(), returncode=p.returncode)


class SecureShell(RemoteShell):
    SSH_NEW_KEY_STRING = 'Are you sure you want to continue connecting'

    def __init__(self, rsh='ssh', rcp='scp', **kwargs):
        rsh += ' -oStrictHostKeyChecking=yes -oConnectTimeout=60'
        rcp += ' -oStrictHostKeyChecking=yes -oConnectTimeout=60'
        super(SecureShell, self).__init__(rsh=rsh, rcp=rcp, **kwargs)


class GlobusSecureShell(SecureShell):

    def __init__(self, rsh='gsissh', rcp='gsiscp', **kwargs):
        super(SecureShell, self).__init__(rsh=rsh, rcp=rcp, **kwargs)
