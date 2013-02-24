from test_utils import get_test_toolbox


def test_load_simple_tool():
    toolbox = get_test_toolbox()
    tool1 = toolbox.get_tool("tool1")
    assert tool1.version == "0.1"
