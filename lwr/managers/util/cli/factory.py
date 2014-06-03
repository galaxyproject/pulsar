try:
    from galaxy.jobs.runners.util.cli import (
        CliInterface,
        split_params
    )
    code_dir = None
except ImportError:
    from lwr.managers.util.cli import (
        CliInterface,
        split_params
    )
    code_dir = '.'


def get_plugins(params):
    cli_interface = CliInterface(code_dir=code_dir)
    shell_params, job_params = split_params(params)
    return cli_interface(shell_params, job_params)
