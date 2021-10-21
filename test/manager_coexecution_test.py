import subprocess
import threading

from .test_utils import (
    BaseManagerTestCase,
)

from pulsar.managers.unqueued import CoexecutionManager


class Coexecutor:
    """Mimic shell script in other container of coexecutor pod-like environment."""

    def __init__(self, manager):
        self.manager = manager
        self.has_command_line = False
        self.command_line = None

    def monitor(self):
        while not self.has_command_line:
            try:
                command_line = self.manager.read_command_line("123")
            except (OSError, ValueError):
                continue
            if not command_line:
                # might be partially written... need to be make this atomic I think.
                continue
            self.command_line = command_line
            self.has_command_line = True

        subprocess.call(command_line, shell=True)
        # we are ignoring this exit code and just trusting the one in the job script...
        # I'm not sure what to do about that.


class CoexecutionManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        self._set_manager()

    def tearDown(self):
        super().setUp()

    def _set_manager(self, **kwds):
        self.manager = CoexecutionManager('_default_', self.app, **kwds)

    def test_simple_execution(self):
        coexecutor = Coexecutor(self.manager)
        t = threading.Thread(target=coexecutor.monitor)
        t.start()
        try:
            self._test_simple_execution(self.manager, timeout=5)
        finally:
            coexecutor.has_command_line = True
            t.join(2)
