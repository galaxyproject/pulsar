import textwrap
import subprocess
import sys
import os
try:
    import virtualenv
except ImportError:
    virtualenv = None

def main(argv):
    install_pulsar_in_virtualenv("C:\\Users\\john\\pt3")

def install_pulsar_in_virtualenv(venv):
    if virtualenv is None:
        raise ImportError("Bootstrapping Pulsar into a virtual environment, requires virtualenv.")

    if sys.platform.startswith('win'):
        bin_dir = "Scripts"
    else:
        bin_dir = "bin"
    virtualenv.create_environment(venv)
    subprocess.call([os.path.join(venv, bin_dir, 'pip'), 'install', "--pre", "pulsar-app"])

if __name__ == "__main__":
    main(sys.argv)
