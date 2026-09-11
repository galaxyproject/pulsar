from json import load

from pulsar.main import ArgumentParser
from pulsar.managers.util.drmaa import DrmaaSessionFactory

DESCRIPTION = "Submit a DRMAA job."


def main(argv=None):
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--job_attributes", required=True)
    args = arg_parser.parse_args(argv)
    with open(args.job_attributes) as fh:
        job_attributes = load(fh)
    session = DrmaaSessionFactory().get()
    external_id = session.run_job(**job_attributes)
    print(external_id)


if __name__ == "__main__":
    main()
