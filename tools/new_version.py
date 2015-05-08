#!/usr/bin/env python
# Modify version...
import os
import re
import subprocess
import sys


PROJECT_NAME = "pulsar"
PROJECT_DIRECTORY = os.path.join(os.path.dirname(__file__), "..")
MOD_DIRECTORY = os.path.join(PROJECT_DIRECTORY, PROJECT_NAME)


def main(argv):
    version = argv[1]

    history_path = os.path.join(PROJECT_DIRECTORY, "HISTORY.rst")
    history = open(history_path, "r").read()

    def extend(from_str, line):
        from_str += "\n"
        return history.replace(from_str, from_str + line + "\n" )

    history = extend(".. to_doc", """
---------------------
%s.dev0
---------------------

    """ % version)
    open(history_path, "w").write(history)

    mod_path = os.path.join(MOD_DIRECTORY, "__init__.py")
    mod = open(mod_path, "r").read()
    mod = re.sub("__version__ = '[\d\.]+'",
                 "__version__ = '%s.dev0'" % version,
                 mod, 1)
    mod = open(mod_path, "w").write(mod)
    shell(["git", "commit", "-m", "Starting work on %s" % version,
           "HISTORY.rst", "%s/__init__.py" % PROJECT_NAME])


def shell(cmds, **kwds):
    p = subprocess.Popen(cmds, **kwds)
    return p.wait()


if __name__ == "__main__":
    main(sys.argv)
