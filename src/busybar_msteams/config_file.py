from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

ALLOWED_KEYS = {
    "microsoft": {"client_id", "tenant_id", "token_cache"},
    "busybar": {"host", "name", "token", "discovery_timeout"},
    "polling": {"presence_seconds", "calendar_seconds", "lookahead_days"},
    "app": {"clear_on_exit", "log_level"},
}
EXPECTED_TYPES: dict[tuple[str, str], type | tuple[type, ...]] = {
    ("microsoft", "client_id"): str,
    ("microsoft", "tenant_id"): str,
    ("microsoft", "token_cache"): str,
    ("busybar", "host"): str,
    ("busybar", "name"): str,
    ("busybar", "token"): str,
    ("busybar", "discovery_timeout"): (int, float),
    ("polling", "presence_seconds"): (int, float),
    ("polling", "calendar_seconds"): (int, float),
    ("polling", "lookahead_days"): int,
    ("app", "clear_on_exit"): bool,
    ("app", "log_level"): str,
}


class ConfigFileError(ValueError):
    pass


def default_config_path() -> Path:
    return Path.home() / ".config" / "busybar-msteams" / "config.toml"


def implicit_config_path() -> Path:
    """Use a project-local config when present, otherwise the user config."""
    local_path = Path.cwd() / "config.toml"
    return local_path if local_path.is_file() else default_config_path()


def load_config(path: Path, *, required: bool) -> dict[str, dict[str, Any]]:
    path = path.expanduser()
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        if required:
            raise ConfigFileError(f"Config file does not exist: {path}") from None
        return {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigFileError(f"Could not read config file {path}: {error}") from error

    unknown_sections = set(data) - set(ALLOWED_KEYS)
    if unknown_sections:
        names = ", ".join(sorted(unknown_sections))
        raise ConfigFileError(f"Unknown config section(s): {names}")

    result: dict[str, dict[str, Any]] = {}
    for section, allowed_keys in ALLOWED_KEYS.items():
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ConfigFileError(f"Config section [{section}] must be a table")
        unknown_keys = set(values) - allowed_keys
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            raise ConfigFileError(f"Unknown key(s) in [{section}]: {names}")
        for key, value in values.items():
            expected = EXPECTED_TYPES[(section, key)]
            # bool is a subclass of int, but it is never a useful polling value.
            if isinstance(value, bool) and expected is not bool:
                valid = False
            else:
                valid = isinstance(value, expected)
            if not valid:
                raise ConfigFileError(
                    f"Invalid value type for [{section}].{key}: "
                    f"got {type(value).__name__}"
                )
        result[section] = values
    return result


def config_value(
    config: dict[str, dict[str, Any]], section: str, key: str, default: Any = None
) -> Any:
    return config.get(section, {}).get(key, default)
