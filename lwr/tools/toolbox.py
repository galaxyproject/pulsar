
from lwr.tools.validator import ExpressionValidator
from xml.etree import ElementTree
from os.path import join, abspath, dirname

from logging import getLogger
log = getLogger(__name__)


class ToolBox(object):
    """
    Abstraction over a tool config file largely modelled after
    Galaxy's shed_tool_conf.xml. Hopefully over time this toolbox
    schema will be a direct superset of Galaxy's with extensions
    to support simple, non-toolshed based tool setups.
    """

    def __init__(self, path):
        self.path = path
        self.tool_configs = []
        toolbox_tree = ElementTree.parse(path)
        toolbox_root = toolbox_tree.getroot()
        self.tool_path = toolbox_root.get('tool_path')
        self.__load_simple_tools(toolbox_root)
        self.__load_toolshed_tools(toolbox_root)

    def __load_toolshed_tools(self, toolbox_root):
        self.__load_tools_from_els(toolbox_root, 'tool', ToolShedToolConfig)

    def __load_simple_tools(self, toolbox_root):
        self.__load_tools_from_els(toolbox_root, 'simple_tool', SimpleToolConfig)

    def __load_tools_from_els(self, toolbox_root, el_name, tool_cls):
        els = toolbox_root.findall(el_name)
        for el in els:
            try:
                tool = tool_cls(self, el)
                self.tool_configs.append(tool)
            except Exception, e:
                print str(e)
                log.exception('Failed to load tool.')

    def get_path(self, relative_path):
        """
        Resolve relative paths defined in toolbox XML using
        self.path as a base.
        """
        return join(self.tool_path, relative_path)

    def get_tool(self, id):
        # Need to handle multiple tools per id someday, but
        # starting simple.
        tools = self.__find_tools_by_id(id)
        if not tools:
            raise KeyError("Failed to find tool with id '%s'" % id)
        if len(tools) > 1:
            log.warn("Found multiple tools with id '%s', returning first." % id)
        return tools[0]

    def __find_tools_by_id(self, id):
        return [tool for tool in self.tool_configs if tool.id == id]


class InputsValidator(object):

    def __init__(self, command_validator, config_validators):
        self.command_validator = command_validator
        self.config_validators = config_validators

    def validate_command(self, job_directory, command):
        return self.command_validator.validate(job_directory, command)

    def validate_config(self, job_directory, name, path):
        config_validator = self.config_validators.get(name, None)
        valid = True
        if config_validator:
            contents = open(path, "r").read()
            valid = config_validator.validate(job_directory, contents)
        return valid


class ToolConfig(object):
    """
    Abstract description of a Galaxy tool.
    """

    def __init__(self, toolbox):
        super(ToolConfig, self).__init__()
        self.toolbox = toolbox

    def get_tool_dir(self):
        return abspath(dirname(self.path))

    @property
    def inputs_validator(self):
        if not hasattr(self, "_inputs_validator"):
            command_el = self._root().find("./validators/command_validator")
            command_validator = ExpressionValidator(command_el)
            config_validators = {}
            for config_el in self._root().findall("./validators/configfile_validator"):
                name = config_el.get("name")
                config_validators[name] = ExpressionValidator(config_el)
            self._inputs_validator = InputsValidator(command_validator, config_validators)
        return self._inputs_validator

    def _root(self):
        return self._el().getroot()

    def _el(self):
        return ElementTree.parse(self.path)


class SimpleToolConfig(ToolConfig):
    """
    Abstract description of a Galaxy tool loaded from a
    toolbox with the `simple_tool` tag, i.e. one not from
    the toolshed.
    """

    def __init__(self, toolbox, simple_tool_el):
        super(SimpleToolConfig, self).__init__(toolbox)
        rel_path = simple_tool_el.get('file')
        resolved_path = toolbox.get_path(rel_path)
        self.path = resolved_path
        root = self._root()
        self.id = root.get('id')
        self.version = root.get('version', '1.0.0')


class ToolShedToolConfig(ToolConfig):
    """
    Abstract description of a Galaxy tool loaded from a
    toolbox with the `tool` tag, i.e. one from the
    toolshed.
    """

    def __init__(self, toolbox, simple_tool_el):
        super(ToolShedToolConfig, self).__init__(toolbox)
