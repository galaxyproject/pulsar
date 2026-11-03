import os

import pytest
from galaxy.util.bunch import Bunch

from pulsar.client.action_mapper import (
    FileActionMapper,
)
from pulsar.client.util import PathHelper


def test_endpoint_validation():
    client = _min_client("remote_transfer")
    mapper = FileActionMapper(client)
    exception_found = False
    try:
        mapper.action({'path': '/opt/galaxy/tools/filters/catWrapper.py'}, 'input')
    except Exception as e:
        exception_found = True
        assert "files_endpoint" in str(e)
    assert exception_found


def test_ssh_key_validation():
    client = _min_client("remote_rsync_transfer")
    mapper = FileActionMapper(client)
    exception_found = False
    try:
        mapper.action({'path': '/opt/galaxy/tools/filters/catWrapper.py'}, 'input')
    except Exception as e:
        exception_found = True
        assert "ssh_key" in str(e)
    assert exception_found


def test_ssh_key_defaults():
    client = _client("remote_rsync_transfer")
    mapper = FileActionMapper(client)
    action = mapper.action({'path': '/opt/galaxy/tools/filters/catWrapper.py'}, 'input')
    action.to_dict()


def test_prefix_mapper_matches_whole_path_segments():
    mapper = FileActionMapper(_mapped_client({"path": "/data/ref", "action": "copy"}))
    assert mapper.action({"path": "/data/ref"}, "input").action_type == "copy"
    assert mapper.action({"path": "/data/ref/hg19.fa"}, "input").action_type == "copy"
    assert mapper.action({"path": "/data/refX/hg19.fa"}, "input").action_type == "none"
    assert mapper.action({"path": "/data/ref2"}, "input").action_type == "none"


def test_root_prefix_mapper_matches_everything():
    mapper = FileActionMapper(_mapped_client({"path": "/", "action": "copy"}))
    assert mapper.action({"path": "/data/ref/hg19.fa"}, "input").action_type == "copy"


@pytest.mark.parametrize("match_type,mapped_path", [
    ("prefix", "{ref}"),
    ("glob", "{ref}/*"),
    ("glob", "{ref}/genomes/hg19.fa*"),
])
def test_depth_is_clamped_to_mapped_directory(tmp_path, match_type, mapped_path):
    ref = tmp_path / "ref"
    (ref / "genomes").mkdir(parents=True)
    for path in [ref / "genomes" / "hg19.fa", ref / "genomes" / "hg19.fa.fai", tmp_path / "secret"]:
        path.write_text("x")
    mapper = FileActionMapper(_mapped_client(
        {"path": mapped_path.format(ref=ref), "match_type": match_type, "depth": 3, "path_types": "unstructured"}
    ))
    action = mapper.action({"path": str(ref / "genomes" / "hg19.fa")}, "unstructured")
    staged = action.unstructured_map(PathHelper(os.sep))
    assert sorted(staged) == [str(ref / "genomes" / "hg19.fa"), str(ref / "genomes" / "hg19.fa.fai")]


def test_depth_of_glob_with_wildcard_in_directory_name_stays_in_matched_directory(tmp_path):
    (tmp_path / "genomes").mkdir()
    for path in [tmp_path / "genomes" / "hg19.fa", tmp_path / "genomes" / "hg19.fa.fai", tmp_path / "secret"]:
        path.write_text("x")
    mapper = FileActionMapper(_mapped_client(
        {"path": f"{tmp_path}/gen*/hg19.fa", "match_type": "glob", "depth": 3, "path_types": "unstructured"}
    ))
    action = mapper.action({"path": str(tmp_path / "genomes" / "hg19.fa")}, "unstructured")
    staged = action.unstructured_map(PathHelper(os.sep))
    assert sorted(staged) == [str(tmp_path / "genomes" / "hg19.fa"), str(tmp_path / "genomes" / "hg19.fa.fai")]


def _mapped_client(*paths):
    return Bunch(
        default_file_action="none",
        action_config_path=None,
        files_endpoint=None,
        file_actions={"paths": list(paths)},
    )


def _min_client(default_action):
    """Minimal client, missing properties for certain actions."""
    mock_client = Bunch(
        default_file_action=default_action,
        action_config_path=None,
        files_endpoint=None,
        ssh_key=None,
    )
    return mock_client


def _client(default_action):
    mock_client = Bunch(
        default_file_action=default_action,
        action_config_path=None,
        files_endpoint="http://localhost",
        ssh_key="12345",
    )
    return mock_client
