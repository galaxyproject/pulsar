import ast
import os
import os.path
import re
import sys

from packaging.version import Version

DEV_RELEASE = os.environ.get("DEV_RELEASE", None) == "1"
source_dir = sys.argv[1]

_version_re = re.compile(r"__version__\s+=\s+(.*)")

with open(os.path.join(source_dir, "__init__.py")) as f:
    version_match = _version_re.search(f.read())
assert version_match
version = ast.literal_eval(version_match.group(1))

if not DEV_RELEASE:
    version_obj = Version(version)
    # Strip .devN
    print(version_obj.base_version)
else:
    print(version)
