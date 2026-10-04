"""Job staging constants."""

COMMAND_VERSION_FILENAME = "COMMAND_VERSION"
DEFAULT_DYNAMIC_COLLECTION_PATTERN = [
    r"primary_.*|galaxy.json|metadata_.*|dataset_\d+\.dat|__instrument_.*|dataset_\d+_files.+|outputs_populated/.*|tool_stdout|tool_stderr"
]
EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN = [
    r"outputs_populated/.*"
]
