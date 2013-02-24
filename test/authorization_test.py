
from lwr.tools.authorization import get_authorizer
from test_utils import get_test_toolbox


def test_allow_any_authorization():
    authorization_manager = get_authorizer(None)
    assert authorization_manager.get_authorization('tool1').can_setup()


def test_tool_whitelist_authorization():
    toolbox = get_test_toolbox()
    authorization_manager = get_authorizer(toolbox)
    assert authorization_manager.get_authorization('tool1').can_setup()
