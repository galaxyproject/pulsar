import argparse
import json

from pulsar.managers.base import JobDirectory
from pulsar.managers.staging.post import _collect_outputs
from pulsar.managers.util.retry import RetryActionExecutor


def make_parser():
    """Construct an argument parser used to call the script from the command line."""

    parser = argparse.ArgumentParser(description="Create output staging manifest")

    parser.add_argument("--job-directory")
    parser.add_argument("--staging-config-path", help="Path to staging config JSON file")
    parser.add_argument("--output-manifest-path")

    return parser


def collect_outputs(job_directory: str, staging_config_path: str, output_manifest_path: str):
    job_directory = JobDirectory(job_directory)
    with open(staging_config_path) as staging_fh:
        staging_config = json.load(staging_fh)

    action_mapper, _ = _collect_outputs(job_directory, staging_config=staging_config, action_executor=RetryActionExecutor(), was_cancelled=lambda: False)
    new_manifest = action_mapper.finalize()
    with open(output_manifest_path, "w") as manifest_fh:
        json.dump(new_manifest, manifest_fh)


if __name__ == "__main__":
    parser = make_parser()
    args = parser.parse_args()
    collect_outputs(args.job_directory, args.staging_config_path, args.output_manifest_path)