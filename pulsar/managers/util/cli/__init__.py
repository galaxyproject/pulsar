"""
"""
from glob import glob
from inspect import getsourcefile
from os import pardir
from os.path import abspath
from os.path import basename
from os.path import join

DEFAULT_SHELL_PLUGIN = 'LocalShell'

ERROR_MESSAGE_NO_JOB_PLUGIN = "No job plugin parameter found, cannot create CLI job interface"
ERROR_MESSAGE_NO_SUCH_JOB_PLUGIN = "Failed to find job_plugin of type %s, available types include %s"


class CliInterface(object):
    """
    High-level interface for loading shell and job plugins and matching
    them to specified parameters.
    """

    def __init__(self, code_dir='lib'):
        """
        """
        def __load(module_prefix, d, code_dir):
            module_pattern = join(join(code_dir, module_prefix), '*.py')
            for file in glob(module_pattern):
                if basename(file).startswith('_'):
                    continue
                file = file.split(code_dir)[1]
                module_name = '%s.%s' % (module_prefix.replace("/", "."), basename(file).rsplit('.py', 1)[0])
                module = __import__(module_name)
                for comp in module_name.split(".")[1:]:
                    module = getattr(module, comp)
                for name in module.__all__:
                    try:
                        d[name] = getattr(module, name)
                    except TypeError:
                        raise TypeError("Invalid type for name %s" % name)

        self.cli_shells = {}
        self.cli_job_interfaces = {}

        module_prefix = self.__module__
        module_prefix = join(*module_prefix.split("."))
        module_path = abspath(join(getsourcefile(CliInterface), pardir))
        code_dir = module_path.split(module_prefix)[0]
        __load('%s/shell' % module_prefix, self.cli_shells, code_dir)
        __load('%s/job' % module_prefix, self.cli_job_interfaces, code_dir)

    def get_plugins(self, shell_params, job_params):
        """
        Return shell and job interface defined by and configured via
        specified params.
        """
        shell = self.get_shell_plugin(shell_params)
        job_interface = self.get_job_interface(job_params)
        return shell, job_interface

    def get_shell_plugin(self, shell_params):
        shell_plugin = shell_params.get('plugin', DEFAULT_SHELL_PLUGIN)
        shell = self.cli_shells[shell_plugin](**shell_params)
        return shell

    def get_job_interface(self, job_params):
        job_plugin = job_params.get('plugin', None)
        if not job_plugin:
            raise ValueError(ERROR_MESSAGE_NO_JOB_PLUGIN)
        job_plugin_class = self.cli_job_interfaces.get(job_plugin, None)
        if not job_plugin_class:
            raise ValueError(ERROR_MESSAGE_NO_SUCH_JOB_PLUGIN % (job_plugin, self.cli_job_interfaces.keys()))
        job_interface = job_plugin_class(**job_params)

        return job_interface


def split_params(params):
    shell_params = dict((k.replace('shell_', '', 1), v) for k, v in params.items() if k.startswith('shell_'))
    job_params = dict((k.replace('job_', '', 1), v) for k, v in params.items() if k.startswith('job_'))
    return shell_params, job_params
