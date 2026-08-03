from pathlib import Path

import pytest

from busybar_msteams.cli import parse_config
from busybar_msteams.config_file import ConfigFileError, load_config


def write_config(path: Path) -> None:
    path.write_text(
        """
[microsoft]
client_id = "from-file"
tenant_id = "file-tenant"

[busybar]
name = "Office"
discovery_timeout = 2.5

[polling]
presence_seconds = 30.0
calendar_seconds = 600.0
lookahead_days = 14

[app]
clear_on_exit = false
log_level = "WARNING"
""".strip(),
        encoding="utf-8",
    )


def test_config_file_populates_app_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.toml"
    write_config(path)
    monkeypatch.delenv("MS_CLIENT_ID", raising=False)
    monkeypatch.delenv("MS_TENANT_ID", raising=False)
    monkeypatch.delenv("BUSYBAR_NAME", raising=False)

    config, log_level = parse_config(["--config", str(path)])

    assert config.client_id == "from-file"
    assert config.tenant_id == "file-tenant"
    assert config.device_name == "Office"
    assert config.discovery_timeout == 2.5
    assert config.poll_seconds == 30.0
    assert config.calendar_refresh_seconds == 600.0
    assert config.lookahead_days == 14
    assert not config.clear_on_exit
    assert log_level == "WARNING"


def test_cli_and_environment_override_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.toml"
    write_config(path)
    monkeypatch.setenv("MS_TENANT_ID", "env-tenant")

    config, _ = parse_config(
        [
            "--config",
            str(path),
            "--client-id",
            "from-cli",
            "--lookahead-days",
            "3",
            "--clear",
        ]
    )

    assert config.client_id == "from-cli"
    assert config.tenant_id == "env-tenant"
    assert config.lookahead_days == 3
    assert config.clear_on_exit


def test_project_local_config_is_loaded_implicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.toml"
    write_config(path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BUSYBAR_MSTEAMS_CONFIG", raising=False)
    monkeypatch.delenv("MS_CLIENT_ID", raising=False)
    monkeypatch.delenv("MS_TENANT_ID", raising=False)

    config, _ = parse_config([])

    assert config.client_id == "from-file"
    assert config.tenant_id == "file-tenant"


def test_unknown_config_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[busybar]\ncolour = 'red'\n", encoding="utf-8")
    with pytest.raises(ConfigFileError, match="Unknown key"):
        load_config(path, required=True)


def test_wrong_config_type_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[polling]\nlookahead_days = 'seven'\n", encoding="utf-8")
    with pytest.raises(ConfigFileError, match="Invalid value type"):
        load_config(path, required=True)


def test_missing_default_config_is_optional(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.toml", required=False) == {}
