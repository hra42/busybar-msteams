from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from busylib import BusyBar, exceptions

from busybar_msteams.discovery import resolve_access_token, resolve_device
from busybar_msteams.display import APP_NAME, build_payload
from busybar_msteams.graph import GraphClient, GraphError, TokenProvider
from busybar_msteams.models import (
    Meeting,
    ScreenMode,
    ScreenState,
    TeamsPresence,
    build_screen_state,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppConfig:
    client_id: str
    tenant_id: str
    token_cache: Path
    device_host: str | None
    device_name: str | None
    discovery_timeout: float
    device_token: str | None
    poll_seconds: float
    calendar_refresh_seconds: float
    lookahead_days: int
    once: bool = False
    dry_run: bool = False
    clear_on_exit: bool = True


def run(config: AppConfig) -> None:
    tokens = TokenProvider(config.client_id, config.tenant_id, config.token_cache)
    with GraphClient(tokens) as graph:
        if config.dry_run:
            _run_dry(graph, config)
            return
        _run_device(graph, config)


def _run_dry(graph: GraphClient, config: AppConfig) -> None:
    now = datetime.now(UTC)
    presence = graph.get_presence()
    meetings = graph.get_teams_meetings(now, lookahead_days=config.lookahead_days)
    state = build_screen_state(meetings, presence, now)
    print(build_payload(state, now).model_dump_json(indent=2))


def _run_device(graph: GraphClient, config: AppConfig) -> None:
    meetings: list[Meeting] | None = None
    presence: TeamsPresence | None = None
    next_calendar_refresh = datetime.min.replace(tzinfo=UTC)
    last_payload: str | None = None
    retry_after = 0.0
    device_host = resolve_device(
        config.device_host,
        device_name=config.device_name,
        timeout=config.discovery_timeout,
    )
    device_token = resolve_access_token(device_host, config.device_token)

    with BusyBar(
        device_host,
        token=device_token,
        timeout=10.0,
        max_retries=2,
        compatibility_mode="warn",
    ) as device:
        try:
            version = device.version()
            logger.info(
                "Connected to BUSY Bar firmware %s",
                version.version or version.api_semver or "unknown",
            )
        except exceptions.BusyBarError as error:
            logger.warning(
                "BUSY Bar startup check failed; will keep retrying: %s", error
            )

        try:
            while True:
                now = datetime.now(UTC)
                error_message: str | None = None
                try:
                    presence = graph.get_presence()
                except GraphError as error:
                    logger.warning("Presence refresh failed: %s", error)
                    error_message = str(error)
                    retry_after = max(retry_after, error.retry_after or 0.0)

                if now >= next_calendar_refresh:
                    try:
                        meetings = graph.get_teams_meetings(
                            now, lookahead_days=config.lookahead_days
                        )
                        next_calendar_refresh = now + timedelta(
                            seconds=config.calendar_refresh_seconds
                        )
                    except GraphError as error:
                        logger.warning("Calendar refresh failed: %s", error)
                        error_message = error_message or str(error)
                        retry_after = max(retry_after, error.retry_after or 0.0)

                # Keep the last positive on-call presence through transient Graph
                # failures. A stale red light is safer than falsely inviting an
                # interruption while a call is still in progress.
                if presence is not None and (
                    meetings is not None or presence.is_on_call
                ):
                    state = build_screen_state(meetings or [], presence, now)
                else:
                    state = ScreenState(
                        ScreenMode.ERROR,
                        presence=presence,
                        message=error_message,
                    )

                payload = build_payload(state, now)
                serialized = payload.model_dump_json()
                if serialized != last_payload:
                    try:
                        device.display_draw(payload, sanitize_text=True)
                        last_payload = serialized
                        logger.info("BUSY Bar screen: %s", state.mode.value)
                    except exceptions.BusyBarError as error:
                        logger.warning("BUSY Bar update failed; will retry: %s", error)

                if config.once:
                    break
                delay = max(config.poll_seconds, retry_after)
                retry_after = 0.0
                time.sleep(delay)
        except KeyboardInterrupt:
            logger.info("Stopping")
        finally:
            if config.clear_on_exit:
                try:
                    device.display_clear(application_name=APP_NAME)
                except exceptions.BusyBarError as error:
                    logger.warning("Could not clear the BUSY Bar display: %s", error)
