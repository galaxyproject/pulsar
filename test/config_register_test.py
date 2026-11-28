"""Tests for the app.yml that ``pulsar-config --register-with-galaxy`` writes."""

import types

import yaml

from pulsar.scripts import config


def test_register_puts_staging_and_persistence_beside_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config,
        "register_with_galaxy",
        lambda **kwargs: {"relay_url": "https://relay.test", "manager_name": "cr-0123abcd"},
    )
    args = types.SimpleNamespace(
        register_with_galaxy="https://galaxy.test",
        galaxy_token="token",
        relay_url="https://relay.test",
        force=False,
    )
    assert config._run_register_with_galaxy(args, str(tmp_path)) == 0

    app = yaml.safe_load((tmp_path / "app.yml").read_text())
    assert app["staging_directory"] == str(tmp_path / "staging")
    assert app["persistence_directory"] == str(tmp_path / "persisted_data")
    assert (tmp_path / "staging").is_dir()
    assert (tmp_path / "persisted_data").is_dir()
