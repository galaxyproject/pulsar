"""Interface layer for Boto's batch library shared between Galaxy and Pulsar."""

BOTO3_IMPORT_MSG = (
    "The Python 'boto3' package is required to use "
    "this feature, please install it or correct the "
    "following error:\nImportError {msg!s}"
)

try:
    import boto3

except ImportError as e:
    boto3 = None
    BOTO3_IMPORT_MSG.format(msg=str(e))


def ensure_client_available() -> None:
    if boto3 is None:
        raise Exception(BOTO3_IMPORT_MSG)


def get_client(access_key_id=None, secret_access_key=None, region_name=None):
    session = boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
    )
    return session.client("batch")


__all__ = (
    "ensure_client_available",
    "get_client",
)
