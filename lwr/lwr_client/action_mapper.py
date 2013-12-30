from simplejson import load
from os.path import abspath
from fnmatch import fnmatch
from re import compile
from galaxy.util.bunch import Bunch

DEFAULT_MAPPED_ACTION = 'transfer'  # Not really clear to me what this should be, exception?
DEFAULT_PATH_MAPPER_TYPE = 'prefix'

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
)


class FileActionMapper(object):
    """
    Objects of this class define how paths are mapped to actions.

    >>> json_string = r'''{"paths": [ \
      {"path": "/opt/galaxy", "action": "none"}, \
      {"path": "/galaxy/data", "action": "transfer"}, \
      {"path": "/cool/bamfiles/**/*.bam", "action": "copy", "type": "glob"}, \
      {"path": ".*/dataset_\\\\d+.dat", "action": "copy", "type": "regex"} \
    ]}'''
    >>> from tempfile import NamedTemporaryFile
    >>> from os import unlink
    >>> f = NamedTemporaryFile(delete=False)
    >>> write_result = f.write(json_string.encode('UTF-8'))
    >>> f.close()
    >>> class MockClient():
    ...     default_file_action = 'none'
    ...     action_config_path = f.name
    ...
    >>> mapper = FileActionMapper(MockClient())
    >>> unlink(f.name)
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
    >>> action = mapper.action('/opt/galaxy/database/working_directory/45.sh', 'work_dir')
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
            map_type = path_config.get('type', DEFAULT_PATH_MAPPER_TYPE)
            self.mappers.append(mappers[map_type](path_config))

    def action(self, path, type):
        action_type = self.default_action
        normalized_path = abspath(path)
        for mapper in self.mappers:
            if mapper.matches(normalized_path):
                action_type = mapper.action_type
                break
        if type in ["work_dir", "output_task"] and action_type == "none":
            ## We are changing the working_directory relative to what
            ## Galaxy would use, these need to be copied over.
            action_type = "copy"
        action_class = actions.get(action_type, None)
        if action_class is None:
            message_template = "Unknown action_type encountered %s while trying to map path %s"
            message_args = (action_type, path)
            raise Exception(message_template % message_args)
        return action_class(path)


class NoneAction(object):
    """ This action indicates the corresponding path does not require any
    additional action. This should indicate paths that are available both on
    the LWR client (i.e. Galaxy server) and remote LWR server with the same
    paths. """
    action_type = "none"
    staging_needed = False

    def __init__(self, path):
        self.path = path


class TransferAction(object):
    """ This actions indicates that the LWR client should initiate an HTTP
    transfer of the corresponding path to the remote LWR server before
    launching the job. """
    action_type = "transfer"
    staging_needed = True

    def __init__(self, path):
        self.path = path


class CopyAction(object):
    """ This action indicates that the LWR client should execute a file system
    copy of the corresponding path to the LWR staging directory prior to
    launching the corresponding job. """
    action_type = "copy"
    staging_needed = True

    def __init__(self, path):
        self.path = path


class BasePathMapper(object):

    def __init__(self, config):
        self.action_type = config.get('action', DEFAULT_MAPPED_ACTION)


class PrefixPathMapper(BasePathMapper):

    def __init__(self, config):
        super(PrefixPathMapper, self).__init__(config)
        self.prefix_path = abspath(config['path'])

    def matches(self, path):
        return path.startswith(self.prefix_path)


class GlobPathMapper(BasePathMapper):

    def __init__(self, config):
        super(GlobPathMapper, self).__init__(config)
        self.glob_path = config['path']

    def matches(self, path):
        return fnmatch(path, self.glob_path)


class RegexPathMapper(BasePathMapper):

    def __init__(self, config):
        super(RegexPathMapper, self).__init__(config)
        self.pattern = compile(config['path'])

    def matches(self, path):
        return self.pattern.match(path) is not None


ACTION_CLASSES = [NoneAction, TransferAction, CopyAction]
actions = dict([(clazz.action_type, clazz) for clazz in ACTION_CLASSES])

mappers = {
    'prefix': PrefixPathMapper,
    'glob': GlobPathMapper,
    'regex': RegexPathMapper,
}


__all__ = [FileActionMapper, path_type]
