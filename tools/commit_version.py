#!/usr/bin/env python
# Modify version...
import datetime
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
    today = datetime.datetime.today()
    today_str = today.strftime('%Y-%m-%d')
    history = history.replace(".dev0", " (%s)" % today_str)
    open(history_path, "w").write(history)

    mod_path = os.path.join(MOD_DIRECTORY, "__init__.py")
    mod = open(mod_path, "r").read()
    mod = re.sub("__version__ = '[\d\.]*\.dev0'",
                 "__version__ = '%s'" % version,
                 mod)
    mod = open(mod_path, "w").write(mod)
    shell(["git", "commit", "-m", "Version %s" % version,
           "HISTORY.rst", "%s/__init__.py" % PROJECT_NAME])
    shell(["git", "tag", version])


def shell(cmds, **kwds):
    p = subprocess.Popen(cmds, **kwds)
    return p.wait()


if __name__ == "__main__":
    main(sys.argv)
