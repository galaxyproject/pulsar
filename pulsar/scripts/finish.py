"""Finish a job submitted with submit.
"""
import sys

from pulsar.main import ArgumentParser
from pulsar.scripts.submit_util import (
    add_common_submit_args,
    run_server_for_job_finish,
)


def main(args=None):
    mod_docstring = sys.modules[__name__].__doc__
    arg_parser = ArgumentParser(description=mod_docstring)
    add_common_submit_args(arg_parser)
    args = arg_parser.parse_args(args)
    run_server_for_job_finish(args)


if __name__ == "__main__":
    main()
