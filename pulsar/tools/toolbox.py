from io import open
from logging import getLogger
from os.path import abspath, dirname, join
from xml.etree import ElementTree

from pulsar.tools.validator import ExpressionValidator


log = getLogger(__name__)


class ToolBox(object):
    """
    Abstraction over a tool config file largely modelled after
    Galaxy's shed_tool_conf.xml. Hopefully over time this toolbox
    schema will be a direct superset of Galaxy's with extensions
    to support simple, non-toolshed based tool setups.
    """

    def __init__(self, path_string):
        self.tool_configs = []
        paths = [path.strip() for path in path_string.split(",")]
        for path in paths:
            toolbox_tree = ElementTree.parse(path)
            toolbox_root = toolbox_tree.getroot()
            tool_path = toolbox_root.get('tool_path')
            self.__load_tools_from_els(toolbox_root, tool_path)

    def __load_tools_from_els(self, toolbox_root, tool_path):
        els = toolbox_root.findall('tool')
        for el in els:
            try:
                if 'guid' in el.attrib:
                    tool_cls = ToolShedToolConfig
                else:
                    tool_cls = SimpleToolConfig
                tool = tool_cls(el, tool_path)
                self.tool_configs.append(tool)
            except Exception:
                log.exception('Failed to load tool.')

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
            contents = open(path, "r", encoding="UTF-8").read()
            valid = config_validator.validate(job_directory, contents)
        return valid


class ToolConfig(object):
    """
    Abstract description of a Galaxy tool.
    """

    def __init__(self):
        super(ToolConfig, self).__init__()

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
    toolbox with the `tool` tag not containing a guid, i.e.
    one not from the toolshed.
    """

    def __init__(self, tool_el, tool_path):
        super(SimpleToolConfig, self).__init__()
        rel_path = tool_el.get('file')
        assert tool_path, "tool_path not set, toolbox XML files must be configured with a tool_path directory."
        assert rel_path, "file not set on tool, each tool element must define a file attribute pointing to a valid tool XML file."
        resolved_path = join(tool_path, rel_path)
        self.path = resolved_path
        root = self._root()
        self.id = root.get('id')
        self.version = root.get('version', '1.0.0')
        self.tool_dir = dirname(resolved_path)


class ToolShedToolConfig(SimpleToolConfig):
    """
    Abstract description of a Galaxy tool loaded from a
    toolbox with the `tool` tag, i.e. one from the
    toolshed.

    ::

        <tool file="../shed_tools/gvk.bx.psu.edu/repos/test/column_maker/f06aa1bf1e8a/column_maker/column_maker.xml" guid\
    ="gvk.bx.psu.edu:9009/repos/test/column_maker/Add_a_column1/1.1.0">
            <tool_shed>gvk.bx.psu.edu:9009</tool_shed>
            <repository_name>column_maker</repository_name>
            <repository_owner>test</repository_owner>
            <installed_changeset_revision>f06aa1bf1e8a</installed_changeset_revision
            <id>gvk.bx.psu.edu:9009/repos/test/column_maker/Add_a_column1/1.1.0</id>
            <version>1.1.0</version>
        </tool>
    """

    def __init__(self, tool_el, tool_path):
        super(ToolShedToolConfig, self).__init__(tool_el, tool_path)
        self.guid = tool_el.get("guid")
        # Override id in file for tool shed tools. Use GUID instead.
        self.id = self.guid
