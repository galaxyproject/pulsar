from json import load
from pulsar.managers.util.drmaa import DrmaaSessionFactory
from pulsar.main import ArgumentParser


DESCRIPTION = "Kill a job via DRMAA interface."


def main():
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--external_id", required=True)
    args = arg_parser.parse_args()
    external_id = load(args.external_id)
    session = DrmaaSessionFactory().get()
    external_id = session.kill(external_id)

if __name__ == "__main__":
    main()
