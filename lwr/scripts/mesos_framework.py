from lwr.mesos import (
    ensure_mesos_libs
)
from lwr.mesos.framework import run

from lwr.daemon import (
    ArgumentParser,
    LwrManagerConfigBuilder,
)

DESCRIPTION = "LWR Mesos Framework Entry Point."


def main():
    ensure_mesos_libs()
    arg_parser = ArgumentParser(
        description=DESCRIPTION,
    )
    arg_parser.add_argument("--master", default=None, required=True)
    LwrManagerConfigBuilder.populate_options(arg_parser)
    args = arg_parser.parse_args()

    config_builder = LwrManagerConfigBuilder(args)
    config_builder.setup_logging()
    config = config_builder.load()

    run(
        master=args.master,
        manager_options=config_builder.to_dict(),
        config=config
    )


if __name__ == "__main__":
    main()
