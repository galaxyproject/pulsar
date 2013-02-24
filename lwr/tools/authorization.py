

class AllowAnyAuthorization(object):

    def can_setup(self):
        return True


class AllowAnyAuthorizer(object):
    """
    Allow any, by default LWR is assumed to be secured
    using a firewall or private_token.
    """
    ALLOW_ANY_AUTHORIZATION = AllowAnyAuthorization()

    def get_authorization(self, tool_id):
        return self.ALLOW_ANY_AUTHORIZATION


class ToolBasedAuthorization(AllowAnyAuthorization):

    def __init__(self, tool):
        self.tool = tool

    def can_setup(self):
        return self.tool is not None


class ToolBasedAuthorizer(object):
    """
    Work In Progress: Implement tool based white-listing
    of what jobs can run and what those jobs can do.
    """

    def __init__(self, toolbox):
        self.toolbox = toolbox

    def get_authorization(self, tool_id):
        tool = self.toolbox.get_tool(tool_id)
        return ToolBasedAuthorization(tool)


def get_authorizer(toolbox):
    if toolbox:
        # Use toolbox as a white list.
        authorizer = ToolBasedAuthorizer(toolbox)
    else:
        # No toolbox specified, allow any tools to run.
        authorizer = AllowAnyAuthorizer()
    return authorizer

__all__ = [get_authorizer]
