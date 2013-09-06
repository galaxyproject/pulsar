from tempfile import TemporaryFile
from time import sleep
from subprocess import Popen, PIPE

from ..shell import BaseShellExec
from ....util import Bunch, kill_pid

TIMEOUT_ERROR_MESSAGE = 'Execution timed out'
TIMEOUT_RETURN_CODE = -1
DEFAULT_TIMEOUT = 60
DEFAULT_TIMEOUT_CHECK_INTERVAL = 3


class LocalShell(BaseShellExec):
    """

    >>> shell = LocalShell()
    >>> def exec_python(script, **kwds): return shell.execute('python -c "%s"' % script, **kwds)
    >>> exec_result = exec_python("print 'Hello World'")
    >>> exec_result.stdout.strip()
    'Hello World'
    >>> exec_result = exec_python("import time; time.sleep(90)", timeout=3, timeout_check_interval=1)
    >>> exec_result.stdout
    ''
    >>> exec_result.stderr
    'Execution timed out'
    >>> exec_result.returncode == TIMEOUT_RETURN_CODE
    True
    """

    def __init__(self, **kwds):
        pass

    def execute(self, cmd, timeout=DEFAULT_TIMEOUT, timeout_check_interval=DEFAULT_TIMEOUT_CHECK_INTERVAL, **kwds):
        outf = TemporaryFile()
        p = Popen(cmd, shell=True, stdin=None, stdout=outf, stderr=PIPE)
        # poll until timeout

        for i in range(int(timeout / timeout_check_interval)):
            r = p.poll()
            if r is not None:
                break
            sleep(timeout_check_interval)
        else:
            kill_pid(p.pid)
            return Bunch(stdout='', stderr=TIMEOUT_ERROR_MESSAGE, returncode=TIMEOUT_RETURN_CODE)
        outf.seek(0)
        return Bunch(stdout=outf.read(), stderr=p.stderr.read(), returncode=p.returncode)

__all__ = ('LocalShell',)
