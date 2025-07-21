#!/usr/bin/env python

"""Stage files in or out of a compute environment made available via the Advanced Resource Connector (ARC) [1].

This script reads a set of source and target URL (with `http`, `https` or `file` as URL scheme) and/or path pairs passed
either as command line arguments and/or from a file in the form of a JSON array. It then reads the files from the source
URLs and posts (copies them for `file://` urls) them to the target URLs.

Example usage:

```shell
$ ./staging_arc.py --stage https://example.org file.dat --stage file:///home/user/text.txt https://example.org/files \
    --json staging_manifest.json
```

_staging_manifest.json_
```json
[
  {
    "source": "file:///home/user/data.txt",
    "target": "file:///home/person/file.txt"
  },
  {
    "source": "file:///home/user/analysis.txt",
    "target": "https://example.org/files/analysis.txt"
  }
]
```

Retrieve files from a set of source URLs and save them to a set of target URLs.

References:
- [1] https://www.nordugrid.org/arc/about-arc.html
"""

# When the URL is the target, use POST.

import json
import sys
from argparse import ArgumentParser

from pulsar.client.transport import (
    get_file,
    post_file,
)



def main(args):
    for entry in parse_json_manifest(args.json):
        if entry.get("to_path"):
            get_file(entry["url"], entry["to_path"])
        elif entry.get("from_path"):
            post_file(entry["url"], entry["from_path"])
        else:
            raise Exception(f"Didn't expect this in the staging manifest: {entry}")


def parse_json_manifest(json_path):
    with open(json_path) as fh:
        return json.load(fh)


HELP_STAGE = "Read a file from `source` and save it to `target`."
HELP_JSON = "Read a list of `source` and `target` URLs from a JSON file."


def make_parser() -> ArgumentParser:
    """Construct an argument parser used to call the script from the command line."""

    module_docstring = sys.modules[__name__].__doc__

    parser = ArgumentParser(description=module_docstring)

    parser.add_argument(
        "--stage", dest="stage", metavar=("source", "target"), nargs=2, action="append", help=HELP_STAGE
    )
    parser.add_argument("--json", help=HELP_JSON)

    return parser


if __name__ == "__main__":
    """Invoke script from the command line."""
    argument_parser = make_parser()
    args = argument_parser.parse_args()
    main(args)
