from distutils.version import LooseVersion
import ast
import os
import re
import sys

DEV_RELEASE = os.environ.get("DEV_RELEASE", None) == "1"
source_dir = sys.argv[1]

_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('%s/__init__.py' % source_dir, 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))

# Strip .devN
version_tuple = LooseVersion(version).version[0:3]
if not DEV_RELEASE:
    # Strip .devN
    version_tuple = LooseVersion(version).version[0:3]
    print(".".join(map(str, version_tuple)))
else:
    print(version)
