from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

from busybar_msteams.app import AppConfig, run
from busybar_msteams.config_file import (
    ConfigFileError,
    config_value,
    default_config_path,
    implicit_config_path,
    load_config,
)
from busybar_msteams.discovery import DeviceDiscoveryError
from busybar_msteams.graph import GraphError


def _default_cache_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "busybar-msteams" / "msal-token-cache.json"


def _env_or_config(
    env_name: str,
    config: dict[str, dict[str, Any]],
    section: str,
    key: str,
    default: Any,
) -> Any:
    return os.environ.get(env_name, config_value(config, section, key, default))


def build_parser(
    config: dict[str, dict[str, Any]] | None = None,
    *,
    config_path: Path | None = None,
) -> argparse.ArgumentParser:
    config = config or {}
    parser = argparse.ArgumentParser(
        description="Show the next Teams meeting and live call state on a BUSY Bar."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=config_path or default_config_path(),
        help="TOML config path (default: %(default)s)",
    )
    parser.add_argument(
        "--client-id",
        default=_env_or_config("MS_CLIENT_ID", config, "microsoft", "client_id", None),
    )
    parser.add_argument(
        "--tenant-id",
        default=_env_or_config(
            "MS_TENANT_ID", config, "microsoft", "tenant_id", "organizations"
        ),
    )
    parser.add_argument(
        "--token-cache",
        type=Path,
        default=Path(
            _env_or_config(
                "MS_TOKEN_CACHE",
                config,
                "microsoft",
                "token_cache",
                _default_cache_path(),
            )
        ).expanduser(),
    )
    parser.add_argument(
        "--device",
        default=_env_or_config("BUSYBAR_HOST", config, "busybar", "host", None),
        help="BUSY Bar IP/hostname; by default the app discovers one",
    )
    parser.add_argument(
        "--device-name",
        default=_env_or_config("BUSYBAR_NAME", config, "busybar", "name", None),
        help="Name or temporary ID to select when several bars are discovered",
    )
    parser.add_argument(
        "--discovery-timeout",
        type=float,
        default=config_value(config, "busybar", "discovery_timeout", 1.5),
    )
    parser.add_argument(
        "--device-token",
        default=_env_or_config("BUSYBAR_TOKEN", config, "busybar", "token", None),
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=config_value(config, "polling", "presence_seconds", 20.0),
    )
    parser.add_argument(
        "--calendar-refresh-seconds",
        type=float,
        default=config_value(config, "polling", "calendar_seconds", 300.0),
    )
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=config_value(config, "polling", "lookahead_days", 7),
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Authenticate, print one display payload, and do not contact BUSY Bar",
    )
    clear_group = parser.add_mutually_exclusive_group()
    clear_group.add_argument(
        "--clear",
        dest="clear_on_exit",
        action="store_true",
        help="Clear this app's BUSY Bar screen when stopping",
    )
    clear_group.add_argument(
        "--no-clear",
        dest="clear_on_exit",
        action="store_false",
        help="Leave the last app screen on the bar when stopping",
    )
    parser.set_defaults(
        clear_on_exit=config_value(config, "app", "clear_on_exit", True)
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default=config_value(config, "app", "log_level", "INFO"),
    )
    return parser


def parse_config(argv: list[str] | None = None) -> tuple[AppConfig, str]:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=Path)
    known, _ = bootstrap.parse_known_args(argv)
    env_path = os.environ.get("BUSYBAR_MSTEAMS_CONFIG")
    config_path = known.config or (
        Path(env_path) if env_path else implicit_config_path()
    )
    required = known.config is not None or env_path is not None
    try:
        file_config = load_config(config_path, required=required)
    except ConfigFileError as error:
        bootstrap.error(str(error))

    parser = build_parser(file_config, config_path=config_path)
    args = parser.parse_args(argv)
    if not args.client_id:
        parser.error(
            "set [microsoft].client_id in config.toml, --client-id, or MS_CLIENT_ID"
        )
    if args.poll_seconds < 5:
        parser.error("--poll-seconds must be at least 5")
    if args.discovery_timeout <= 0:
        parser.error("--discovery-timeout must be greater than 0")
    if args.calendar_refresh_seconds < 60:
        parser.error("--calendar-refresh-seconds must be at least 60")
    if not 1 <= args.lookahead_days <= 30:
        parser.error("--lookahead-days must be between 1 and 30")

    return (
        AppConfig(
            client_id=args.client_id,
            tenant_id=args.tenant_id,
            token_cache=args.token_cache,
            device_host=args.device,
            device_name=args.device_name,
            discovery_timeout=args.discovery_timeout,
            device_token=args.device_token,
            poll_seconds=args.poll_seconds,
            calendar_refresh_seconds=args.calendar_refresh_seconds,
            lookahead_days=args.lookahead_days,
            once=args.once,
            dry_run=args.dry_run,
            clear_on_exit=args.clear_on_exit,
        ),
        args.log_level,
    )


def main(argv: list[str] | None = None) -> int:
    config, log_level = parse_config(argv)
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        run(config)
    except (GraphError, DeviceDiscoveryError) as error:
        logging.getLogger(__name__).error("%s", error)
        return 1
    return 0
