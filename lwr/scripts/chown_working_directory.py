from argparse import ArgumentParser
from os import system
from os.path import join, abspath
try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser


DESCRIPTION = "Change ownership of a job working directory."


def main():
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--user", required=True)
    arg_parser.add_argument("--job_id", required=True)
    args = arg_parser.parse_args()
    user = args.user
    job_id = args.job_id

    config = ConfigParser()
    config.read(['server.ini'])
    staging_directory = abspath(config.get('app:main', 'staging_directory'))

    working_directory = abspath(join(staging_directory, job_id))
    assert working_directory.startswith(staging_directory)
    system("chown -Rh '%s' '%s'" % (user, working_directory))

if __name__ == "__main__":
    main()
