#!/usr/bin/env python
# Modify version...
import datetime
import os
import re
import subprocess
import sys


DEV_RELEASE = os.environ.get("DEV_RELEASE", None) == "1"
PROJECT_DIRECTORY = os.path.join(os.path.dirname(__file__), "..")


def main(argv):
    source_dir = argv[1]
    version = argv[2]
    mod_path = os.path.join(PROJECT_DIRECTORY, source_dir, "__init__.py")
    if not DEV_RELEASE:
        history_path = os.path.join(PROJECT_DIRECTORY, "HISTORY.rst")
        history = open(history_path).read()
        today = datetime.datetime.today()
        today_str = today.strftime('%Y-%m-%d')
        history = re.sub(r"^[\d\.]+\.dev\d*",
                         "{} ({})".format(version, today_str),
                         history,
                         flags=re.MULTILINE)
        open(history_path, "w").write(history)

        mod = open(mod_path).read()
        mod = re.sub(r"__version__ = '[\d\.]+\.dev\d*'",
                     "__version__ = '{}'".format(version),
                     mod,
                     flags=re.MULTILINE)
        mod = open(mod_path, "w").write(mod)
        for f in ("HISTORY.rst", os.path.join(source_dir, "__init__.py")):
            if not shell(["git", "diff", "--quiet", "--", f]):
                print("Expected changes to '{}' not found, refusing to commit".format(f))
                sys.exit(1)
        shell(["git", "commit", "-m", "Version %s" % version,
            "HISTORY.rst", "%s/__init__.py" % source_dir])
    shell(["git", "tag", version])


def shell(cmds, **kwds):
    p = subprocess.Popen(cmds, **kwds)
    return p.wait()


if __name__ == "__main__":
    main(sys.argv)
