"""Small utility for bootstrapping a Conda environment for Pulsar.

This should probably be moved into galaxy-tool-util.
"""

import os.path
import sys
from argparse import ArgumentParser

from galaxy.tool_util.deps.conda_util import (
    CondaContext,
    install_conda,
)
from galaxy.util import safe_makedirs


def main(argv=None):
    mod_docstring = sys.modules[__name__].__doc__
    arg_parser = ArgumentParser(description=mod_docstring)
    arg_parser.add_argument("--conda_prefix", required=True)
    args = arg_parser.parse_args(argv)
    conda_prefix = args.conda_prefix
    safe_makedirs(os.path.dirname(conda_prefix))
    conda_context = CondaContext(
        conda_prefix=conda_prefix,
    )
    install_conda(conda_context)


if __name__ == "__main__":
    main()
