#!/usr/bin/env python
# Modify version...
import os
import re
import subprocess
import sys
from distutils.version import StrictVersion


DEV_RELEASE = os.environ.get("DEV_RELEASE", None) == "1"
PROJECT_DIRECTORY = os.path.join(os.path.dirname(__file__), "..")


def main(argv):
    source_dir = argv[1]
    version = argv[2]
    if not DEV_RELEASE:
        old_version = StrictVersion(version)
        old_version_tuple = old_version.version
        new_version_tuple = list(old_version_tuple)
        new_version_tuple[1] = old_version_tuple[1] + 1
        new_version_tuple[2] = 0
        new_version = ".".join(map(str, new_version_tuple))
        new_dev_version = 0
    else:
        dev_version = re.compile(r'dev([\d]+)').search(version).group(1)
        new_dev_version = int(dev_version) + 1
        new_version = version.replace("dev%s" % dev_version, "dev%s" % new_dev_version)

    history_path = os.path.join(PROJECT_DIRECTORY, "HISTORY.rst")
    if not DEV_RELEASE:
        history = open(history_path).read()

        def extend(from_str, line):
            from_str += "\n"
            return history.replace(from_str, from_str + line + "\n")

        history = extend(".. to_doc", """
---------------------
%s.dev0
---------------------

    """ % new_version)
        open(history_path, "w").write(history)

    mod_path = os.path.join(PROJECT_DIRECTORY, source_dir, "__init__.py")
    mod = open(mod_path).read()
    if not DEV_RELEASE:
        mod = re.sub(
            r"__version__ = '[\d\.]+'",
            "__version__ = '%s.dev0'" % new_version,
            mod,
            1
        )
    else:
        mod = re.sub(
            "dev%s" % dev_version,
            "dev%s" % new_dev_version,
            mod,
            1
        )
    mod = open(mod_path, "w").write(mod)
    shell(["git", "commit", "-m", "Starting work on %s" % new_version,
           "HISTORY.rst", "%s/__init__.py" % source_dir])


def shell(cmds, **kwds):
    p = subprocess.Popen(cmds, **kwds)
    return p.wait()


if __name__ == "__main__":
    main(sys.argv)
