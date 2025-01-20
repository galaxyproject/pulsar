"""Submit a job and wait for it.
"""
import sys

from pulsar.main import ArgumentParser
from pulsar.scripts.submit_util import (
    add_common_submit_args,
    run_server_for_job,
)


def main(args=None):
    mod_docstring = sys.modules[__name__].__doc__
    arg_parser = ArgumentParser(description=mod_docstring)
    add_common_submit_args(arg_parser)
    arg_parser.add_argument('--wait', action='store_true')
    arg_parser.add_argument('--no_wait', "--no-wait", dest='wait', action='store_false')
    arg_parser.set_defaults(wait=True)
    args = arg_parser.parse_args(args)
    run_server_for_job(args)


if __name__ == "__main__":
    main()
