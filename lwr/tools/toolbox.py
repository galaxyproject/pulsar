
from xml.etree import ElementTree
from os.path import join

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


class ToolConfig(object):
    """
    Abstract description of a Galaxy tool.
    """

    def __init__(self, toolbox):
        super(ToolConfig, self).__init__()
        self.toolbox = toolbox


class SimpleToolConfig(ToolConfig):
    """
    Abstract description of a Galaxy tool loaded from a
    toolbox with the `simple_tool` tag, i.e. one not from
    the toolshed.
    """

    def __init__(self, toolbox, simple_tool_el):
        super(SimpleToolConfig, self).__init__(toolbox)
        self.path = simple_tool_el.get('file')
        resolved_path = toolbox.get_path(self.path)
        tool_el = ElementTree.parse(resolved_path)
        self.id = tool_el.getroot().get('id')
        self.version = tool_el.getroot().get('version', '1.0.0')


class ToolShedToolConfig(ToolConfig):
    """
    Abstract description of a Galaxy tool loaded from a
    toolbox with the `tool` tag, i.e. one from the
    toolshed.
    """

    def __init__(self, toolbox, simple_tool_el):
        super(ToolShedToolConfig, self).__init__(toolbox)
