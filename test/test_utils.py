from lwr.tools import ToolBox

from os import pardir
from os.path import join, dirname

from unittest import TestCase
from tempfile import mkdtemp
from shutil import rmtree


class TempDirectoryTestCase(TestCase):

    def setUp(self):
        self.temp_directory = mkdtemp()

    def tearDown(self):
        rmtree(self.temp_directory)


def get_test_toolbox():
    toolbox_path = join(dirname(__file__), pardir, "test_data", "test_shed_toolbox.xml")
    toolbox = ToolBox(toolbox_path)
    return toolbox
