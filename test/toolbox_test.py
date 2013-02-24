
from lwr.tools import ToolBox
from os import pardir
from os.path import join, dirname


def test_load_simple_tool():
    toolbox_path = join(dirname(__file__), pardir, "test_data", "test_shed_toolbox.xml")
    toolbox = ToolBox(toolbox_path)
    tool1 = toolbox.get_tool("tool1")
    assert tool1.version == "0.1"
