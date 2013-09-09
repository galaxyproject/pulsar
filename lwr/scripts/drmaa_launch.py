from __future__ import print_function
from argparse import ArgumentParser
from simplejson import load
from lwr.managers.util.drmaa import DrmaaSessionFactory


DESCRIPTION = "Submit a DRMAA job."


def main():
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--job_attributes", required=True)
    args = arg_parser.parse_args()
    job_attributes = load(args.job_attributes)
    session = DrmaaSessionFactory().get()
    external_id = session.run_job(**job_attributes)
    print(external_id)


if __name__ == "__main__":
    main()
