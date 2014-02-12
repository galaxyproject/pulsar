from json import load
from os.path import abspath
from os.path import dirname
from os.path import join
from os.path import basename
from os.path import sep
import fnmatch
from re import compile
from re import escape
import galaxy.util
from galaxy.util.bunch import Bunch
from .util import directory_files
from .util import unique_path_prefix

DEFAULT_MAPPED_ACTION = 'transfer'  # Not really clear to me what this should be, exception?
DEFAULT_PATH_MAPPER_TYPE = 'prefix'

STAGING_ACTION_REMOTE = "remote"
STAGING_ACTION_LOCAL = "local"
STAGING_ACTION_NONE = None
STAGING_ACTION_DEFAULT = "default"

# Poor man's enum.
path_type = Bunch(
    # Galaxy input datasets and extra files.
    INPUT="input",
    # Galaxy config and param files.
    CONFIG="config",
    # Files from tool's tool_dir (for now just wrapper if available).
    TOOL="tool",
    # Input work dir files - e.g. metadata files, task-split input files, etc..
    WORKDIR="workdir",
    # Galaxy output datasets in their final home.
    OUTPUT="output",
    # Galaxy from_work_dir output paths and other files (e.g. galaxy.json)
    OUTPUT_WORKDIR="output_workdir",
    # Other fixed tool parameter paths (likely coming from tool data, but not
    # nessecarily). Not sure this is the best name...
    UNSTRUCTURED="unstructured",
)


ACTION_DEFAULT_PATH_TYPES = [
    path_type.INPUT,
    path_type.CONFIG,
    path_type.TOOL,
    path_type.WORKDIR,
    path_type.OUTPUT,
    path_type.OUTPUT_WORKDIR,
]
ALL_PATH_TYPES = ACTION_DEFAULT_PATH_TYPES + [path_type.UNSTRUCTURED]


class FileActionMapper(object):
    """
    Objects of this class define how paths are mapped to actions.

    >>> json_string = r'''{"paths": [ \
      {"path": "/opt/galaxy", "action": "none"}, \
      {"path": "/galaxy/data", "action": "transfer"}, \
      {"path": "/cool/bamfiles/**/*.bam", "action": "copy", "match_type": "glob"}, \
      {"path": ".*/dataset_\\\\d+.dat", "action": "copy", "match_type": "regex"} \
    ]}'''
    >>> from tempfile import NamedTemporaryFile
    >>> from os import unlink
    >>> def mapper_for(default_action, config_contents):
    ...     f = NamedTemporaryFile(delete=False)
    ...     f.write(config_contents.encode('UTF-8'))
    ...     f.close()
    ...     mock_client = Bunch(default_file_action=default_action, action_config_path=f.name)
    ...     mapper = FileActionMapper(mock_client)
    ...     unlink(f.name)
    ...     return mapper
    >>> mapper = mapper_for(default_action='none', config_contents=json_string)
    >>> # Test first config line above, implicit path prefix mapper
    >>> action = mapper.action('/opt/galaxy/tools/filters/catWrapper.py', 'input')
    >>> action.action_type == u'none'
    True
    >>> action.staging_needed
    False
    >>> # Test another (2nd) mapper, this one with a different action
    >>> action = mapper.action('/galaxy/data/files/000/dataset_1.dat', 'input')
    >>> action.action_type == u'transfer'
    True
    >>> action.staging_needed
    True
    >>> # Always at least copy work_dir outputs.
    >>> action = mapper.action('/opt/galaxy/database/working_directory/45.sh', 'workdir')
    >>> action.action_type == u'copy'
    True
    >>> action.staging_needed
    True
    >>> # Test glob mapper (matching test)
    >>> mapper.action('/cool/bamfiles/projectABC/study1/patient3.bam', 'input').action_type == u'copy'
    True
    >>> # Test glob mapper (non-matching test)
    >>> mapper.action('/cool/bamfiles/projectABC/study1/patient3.bam.bai', 'input').action_type == u'none'
    True
    >>> # Regex mapper test.
    >>> mapper.action('/old/galaxy/data/dataset_10245.dat', 'input').action_type == u'copy'
    True
    >>> # Doesn't map unstructured paths by default
    >>> mapper.action('/old/galaxy/data/dataset_10245.dat', 'unstructured').action_type == u'none'
    True
    >>> input_only_mapper = mapper_for(default_action="none", config_contents=r'''{"paths": [ \
      {"path": "/", "action": "transfer", "path_types": "input"} \
    ] }''')
    >>> input_only_mapper.action('/dataset_1.dat', 'input').action_type == u'transfer'
    True
    >>> input_only_mapper.action('/dataset_1.dat', 'output').action_type == u'none'
    True
    >>> unstructured_mapper = mapper_for(default_action="none", config_contents=r'''{"paths": [ \
      {"path": "/", "action": "transfer", "path_types": "*any*"} \
    ] }''')
    >>> unstructured_mapper.action('/old/galaxy/data/dataset_10245.dat', 'unstructured').action_type == u'transfer'
    True
    """

    def __init__(self, client):
        self.default_action = client.default_file_action
        action_config_path = client.action_config_path
        self.mappers = []
        if action_config_path:
            self.__load_action_config(action_config_path)

    def __load_action_config(self, path):
        config = load(open(path, 'rb'))
        for path_config in config.get('paths', []):
            map_type = path_config.get('match_type', DEFAULT_PATH_MAPPER_TYPE)
            self.mappers.append(mappers[map_type](path_config))

    def action(self, path, type, mapper=None):
        action_type = self.default_action if type in ACTION_DEFAULT_PATH_TYPES else "none"
        file_lister = DEFAULT_FILE_LISTER
        normalized_path = abspath(path)
        if not mapper:
            for query_mapper in self.mappers:
                if query_mapper.matches(normalized_path, type):
                    mapper = query_mapper
                    break
        if mapper:
            action_type = mapper.action_type
            file_lister = mapper.file_lister
        if type in ["workdir", "output_workdir"] and action_type == "none":
            ## We are changing the working_directory relative to what
            ## Galaxy would use, these need to be copied over.
            action_type = "copy"
        action_class = actions.get(action_type, None)
        if action_class is None:
            message_template = "Unknown action_type encountered %s while trying to map path %s"
            message_args = (action_type, path)
            raise Exception(message_template % message_args)
        return action_class(path, file_lister=file_lister)

    def unstructured_mappers(self):
        """ Return mappers that will map 'unstructured' files (i.e. go beyond
        mapping inputs, outputs, and config files).
        """
        return filter(lambda m: path_type.UNSTRUCTURED in m.path_types, self.mappers)


class BaseAction(object):

    def __init__(self, path, file_lister=None):
        self.path = path
        self.file_lister = file_lister or DEFAULT_FILE_LISTER

    def unstructured_map(self):
        unstructured_map = self.file_lister.unstructured_map(self.path)
        # To ensure uniqueness, prepend unique prefix to each name
        prefix = unique_path_prefix(self.path)
        for path, name in unstructured_map.iteritems():
            unstructured_map[path] = join(prefix, name)
        return unstructured_map

    @property
    def staging_needed(self):
        return self.staging != STAGING_ACTION_NONE

    @property
    def staging_action_local(self):
        return self.staging == STAGING_ACTION_LOCAL


class NoneAction(BaseAction):
    """ This action indicates the corresponding path does not require any
    additional action. This should indicate paths that are available both on
    the LWR client (i.e. Galaxy server) and remote LWR server with the same
    paths. """
    action_type = "none"
    staging = STAGING_ACTION_NONE


class TransferAction(BaseAction):
    """ This actions indicates that the LWR client should initiate an HTTP
    transfer of the corresponding path to the remote LWR server before
    launching the job. """
    action_type = "transfer"
    staging = STAGING_ACTION_LOCAL


class CopyAction(BaseAction):
    """ This action indicates that the LWR client should execute a file system
    copy of the corresponding path to the LWR staging directory prior to
    launching the corresponding job. """
    action_type = "copy"
    staging = STAGING_ACTION_LOCAL


class RemoteCopyAction(BaseAction):
    """ This action indicates the LWR server should copy the file before
    execution via direct file system copy. This is like a CopyAction, but
    it indicates the action should occur on the LWR server instead of on
    the client.
    """
    action_type = "remote_copy"
    staging = STAGING_ACTION_REMOTE

    def to_dict(self):
        return dict(path=self.path, action_type=RemoteCopyAction.action_type)

    @classmethod
    def from_dict(cls, action_dict):
        return RemoteCopyAction(path=action_dict["path"])

    def write_to_path(self, path):
        galaxy.util.copy_to_path(open(self.path, "rb"), path)


class MessageAction(object):
    """ Sort of pseudo action describing "files" store in memory and
    transferred via message (HTTP, Python-call, MQ, etc...)
    """
    action_type = "message"
    staging = STAGING_ACTION_DEFAULT

    def __init__(self, contents, client=None):
        self.contents = contents
        self.client = client

    @property
    def staging_needed(self):
        return True

    @property
    def staging_action_local(self):
        # Ekkk, cannot be called if created through from_dict.
        # Shouldn't be a problem the way it is used - but is an
        # object design problem.
        return self.client.prefer_local_staging

    def to_dict(self):
        return dict(contents=self.contents, action_type=MessageAction.action_type)

    @classmethod
    def from_dict(cls, action_dict):
        return MessageAction(contents=action_dict["contents"])

    def write_to_path(self, path):
        open(path, "w").write(self.contents)

DICTIFIABLE_ACTION_CLASSES = [RemoteCopyAction, MessageAction]


def from_dict(action_dict):
    action_type = action_dict.get("action_type", None)
    target_class = None
    for action_class in DICTIFIABLE_ACTION_CLASSES:
        if action_type == action_class.action_type:
            target_class = action_class
    if not target_class:
        message = "Failed to recover action from dictionary - invalid action type specified %s." % action_type
        raise Exception(message)
    return target_class.from_dict(action_dict)


class BasePathMapper(object):

    def __init__(self, config):
        self.action_type = config.get('action', DEFAULT_MAPPED_ACTION)
        path_types_str = config.get('path_types', "*defaults*")
        path_types_str = path_types_str.replace("*defaults*", ",".join(ACTION_DEFAULT_PATH_TYPES))
        path_types_str = path_types_str.replace("*any*", ",".join(ALL_PATH_TYPES))
        self.path_types = path_types_str.split(",")
        self.file_lister = FileLister(config)

    def matches(self, path, path_type):
        path_type_matches = path_type in self.path_types
        return path_type_matches and self._path_matches(path)


class PrefixPathMapper(BasePathMapper):

    def __init__(self, config):
        super(PrefixPathMapper, self).__init__(config)
        self.prefix_path = abspath(config['path'])

    def _path_matches(self, path):
        return path.startswith(self.prefix_path)

    def to_pattern(self):
        pattern_str = "(%s%s[^\s,\"\']+)" % (escape(self.prefix_path), escape(sep))
        return compile(pattern_str)


class GlobPathMapper(BasePathMapper):

    def __init__(self, config):
        super(GlobPathMapper, self).__init__(config)
        self.glob_path = config['path']

    def _path_matches(self, path):
        return fnmatch.fnmatch(path, self.glob_path)

    def to_pattern(self):
        return compile(fnmatch.translate(self.glob_path))


class RegexPathMapper(BasePathMapper):

    def __init__(self, config):
        super(RegexPathMapper, self).__init__(config)
        self.pattern = compile(config['path'])

    def _path_matches(self, path):
        return self.pattern.match(path) is not None

    def to_pattern(self):
        return self.pattern


class FileLister(object):

    def __init__(self, config):
        self.depth = int(config.get("depth", "0"))

    def unstructured_map(self, path):
        depth = self.depth
        if self.depth == 0:
            return {path: basename(path)}
        else:
            while depth > 0:
                path = dirname(path)
                depth -= 1
            return dict([(join(path, f), f) for f in directory_files(path)])

DEFAULT_FILE_LISTER = FileLister(dict(depth=0))

ACTION_CLASSES = [NoneAction, TransferAction, CopyAction, RemoteCopyAction]
actions = dict([(clazz.action_type, clazz) for clazz in ACTION_CLASSES])

mappers = {
    'prefix': PrefixPathMapper,
    'glob': GlobPathMapper,
    'regex': RegexPathMapper,
}


__all__ = [FileActionMapper, path_type, from_dict, MessageAction]
