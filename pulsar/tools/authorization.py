from os.path import join


class AllowAnyAuthorization(object):

    def authorize_setup(self):
        pass

    def authorize_tool_file(self, name, contents):
        pass

    def authorize_execution(self, job_directory, command_line):
        pass

    def authorize_config_file(self, job_directory, name, path):
        pass


class AllowAnyAuthorizer(object):
    """
    Allow any, by default Pulsar is assumed to be secured
    using a firewall or private_token.
    """
    ALLOW_ANY_AUTHORIZATION = AllowAnyAuthorization()

    def get_authorization(self, tool_id):
        return self.ALLOW_ANY_AUTHORIZATION


class ToolBasedAuthorization(AllowAnyAuthorization):

    def __init__(self, tool):
        self.tool = tool

    def __unauthorized(self, msg):
        raise Exception("Unauthorized action attempted: %s" % msg)

    def authorize_setup(self):
        if self.tool is None:
            self.__unauthorized("Attempt to setup a tool with id not registered with Pulsar toolbox.")

    def authorize_tool_file(self, name, contents):
        tool = self.tool
        tool_dir = tool.get_tool_dir()
        tool_dir_file = join(tool_dir, name)
        allowed_contents = open(tool_dir_file).read()
        if contents != allowed_contents:
            self.__unauthorized("Attempt to write tool file with contents differing from Pulsar copy of tool file.")

    def authorize_config_file(self, job_directory, name, path):
        if not self.__inputs_validator.validate_configfile(job_directory, name, path):
            self.__unauthorized("Attempt to utilize unauthorized configfile.")

    def authorize_execution(self, job_directory, command_line):
        if not self.__inputs_validator.validate_command(job_directory, command_line):
            self.__unauthorized("Attempt to execute unauthorized command.")

    @property
    def __inputs_validator(self):
        return self.tool.inputs_validator


class ToolBasedAuthorizer(object):
    """
    Work In Progress: Implement tool based white-listing
    of what jobs can run and what those jobs can do.
    """

    def __init__(self, toolbox):
        self.toolbox = toolbox

    def get_authorization(self, tool_id):
        tool = None
        try:
            tool = self.toolbox.get_tool(tool_id)
        except Exception:
            pass
        return ToolBasedAuthorization(tool)


def get_authorizer(toolbox):
    if toolbox:
        # Use toolbox as a white list.
        authorizer = ToolBasedAuthorizer(toolbox)
    else:
        # No toolbox specified, allow any tools to run.
        authorizer = AllowAnyAuthorizer()
    return authorizer


__all__ = ('get_authorizer',)
