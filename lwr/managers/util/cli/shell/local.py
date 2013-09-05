from tempfile import TemporaryFile
from time import sleep
from subprocess import Popen, PIPE

from ..shell import BaseShellExec
from lwr.managers.util import Bunch, kill_pid


class LocalShell(BaseShellExec):

    def __init__(self, **kwds):
        pass

    def execute(self, cmd, timeout=60, **kwds):
        outf = TemporaryFile()
        p = Popen(cmd, shell=True, stdin=None, stdout=outf, stderr=PIPE)
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

__all__ = ('LocalShell',)
