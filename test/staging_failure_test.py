"""Tests for the staging failure messages Pulsar sends Galaxy to show the user."""
from email.message import Message
from urllib.error import HTTPError as UrllibHTTPError

import pytest
import requests

from pulsar.client.exceptions import PulsarClientTransportError
from pulsar.managers.staging.failure import (
    describe_transfer_error,
    input_staging_failure,
    output_staging_failure,
    raising_staging_failure,
    StagingFailure,
)

JOB_KEY = "0123456789abcdef"
URL = f"https://galaxy.example.org/api/jobs/1/files?job_key={JOB_KEY}&path=%2Fgalaxy%2Fdataset_1.dat"


def _requests_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    response.url = URL
    return requests.HTTPError(f"{status_code} Server Error: Bad Gateway for url: {URL}", response=response)


@pytest.mark.parametrize("exc,expected", [
    (_requests_error(502), "HTTP 502"),
    (UrllibHTTPError(URL, 503, f"Service Unavailable for {URL}", Message(), None), "HTTP 503"),
    (
        # The curl transport's failed upload.
        PulsarClientTransportError(
            code=PulsarClientTransportError.NOT_200,
            transport_code=502,
            transport_message=f"Failed to post_file properly for url {URL}, remote server returned status code of 502.",
        ),
        "HTTP 502",
    ),
    (
        PulsarClientTransportError(
            code=PulsarClientTransportError.TIMEOUT, transport_code=28, transport_message=f"Timed out on {URL}"
        ),
        "Connection timed out",
    ),
    (requests.ConnectionError(f"Max retries exceeded with url: {URL}"), "ConnectionError"),
    (Exception(f"Unexpected failure fetching {URL}"), "Exception"),
])
def test_transfer_error_is_described_without_its_text(exc, expected):
    assert describe_transfer_error(exc) == expected
    assert JOB_KEY not in str(input_staging_failure("dataset_1.dat", exc))
    assert JOB_KEY not in str(output_staging_failure([("dataset_2.dat", exc)]))


def test_any_other_staging_error_is_raised_as_a_staging_failure():
    error = Exception(f"Unexpected failure fetching {URL}")
    with pytest.raises(StagingFailure) as raised:
        with raising_staging_failure("inputs"):
            raise error
    assert str(raised.value) == "Failed to transfer job inputs: Exception"
    assert raised.value.__cause__ is error


def test_a_staging_failure_is_raised_as_is():
    failure = input_staging_failure("dataset_1.dat", _requests_error(502))
    with pytest.raises(StagingFailure) as raised:
        with raising_staging_failure("inputs"):
            raise failure
    assert raised.value is failure


def test_output_failure_names_the_first_output_and_counts_the_rest():
    failure = output_staging_failure([
        ("dataset_2.dat", _requests_error(502)),
        ("dataset_3.dat", _requests_error(504)),
        (None, OSError("disk full")),
    ])
    assert str(failure) == "Failed to transfer output 'dataset_2.dat': HTTP 502 (2 more failed)"


def test_output_failure_without_a_name():
    failure = output_staging_failure([(None, _requests_error(502))])
    assert str(failure) == "Failed to transfer outputs: HTTP 502"
