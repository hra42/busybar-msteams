from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import msal

from busybar_msteams.models import Meeting, TeamsPresence, clean_subject

logger = logging.getLogger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPES = ("Calendars.Read", "Presence.Read")


class GraphError(RuntimeError):
    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TokenProvider:
    """Acquire delegated Graph tokens and persist MSAL's refresh-token cache."""

    def __init__(self, client_id: str, tenant_id: str, cache_path: Path) -> None:
        self.cache_path = cache_path.expanduser()
        self.cache = msal.SerializableTokenCache()
        self._load_cache()
        self.app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self.cache,
        )

    def _load_cache(self) -> None:
        try:
            self.cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            logger.warning("Ignoring unreadable Microsoft token cache")

    def _save_cache(self) -> None:
        if not self.cache.has_state_changed:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(self.cache.serialize(), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.cache_path)

    def access_token(self, *, force_refresh: bool = False) -> str:
        accounts = self.app.get_accounts()
        result: dict[str, Any] | None = None
        if accounts:
            result = self.app.acquire_token_silent(
                list(SCOPES),
                account=accounts[0],
                force_refresh=force_refresh,
            )

        if not result:
            flow = self.app.initiate_device_flow(scopes=list(SCOPES))
            if "user_code" not in flow:
                raise GraphError("Microsoft sign-in could not be started")
            print(flow["message"], flush=True)
            result = self.app.acquire_token_by_device_flow(flow)

        self._save_cache()
        if result and "access_token" in result:
            return str(result["access_token"])

        detail = (result or {}).get("error_description", "authentication failed")
        raise GraphError(f"Microsoft authentication failed: {detail}")


class GraphClient:
    def __init__(self, tokens: TokenProvider, *, timeout: float = 10.0) -> None:
        self.tokens = tokens
        self.client = httpx.Client(base_url=GRAPH_ROOT, timeout=timeout)

    def __enter__(self) -> GraphClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.client.close()

    def _get(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        token = self.tokens.access_token()
        try:
            response = self.client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError as error:
            raise GraphError(f"Could not reach Microsoft Graph: {error}") from error
        if response.status_code == 401:
            token = self.tokens.access_token(force_refresh=True)
            try:
                response = self.client.get(
                    path,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.RequestError as error:
                raise GraphError(f"Could not reach Microsoft Graph: {error}") from error
        if response.is_error:
            retry_header = response.headers.get("Retry-After")
            try:
                retry_after = float(retry_header) if retry_header else None
            except ValueError:
                retry_after = None
            try:
                error = response.json().get("error", {}).get("message")
            except json.JSONDecodeError:
                error = None
            raise GraphError(
                f"Microsoft Graph returned HTTP {response.status_code}"
                + (f": {error}" if error else ""),
                retry_after=retry_after,
            )
        try:
            data = response.json()
        except json.JSONDecodeError as error:
            raise GraphError("Microsoft Graph returned invalid JSON") from error
        if not isinstance(data, dict):
            raise GraphError("Microsoft Graph returned an unexpected response")
        return data

    def get_presence(self) -> TeamsPresence:
        data = self._get("/me/presence")
        return TeamsPresence(
            availability=str(data.get("availability", "presenceUnknown")),
            activity=str(data.get("activity", "presenceUnknown")),
        )

    def get_teams_meetings(
        self, now: datetime, *, lookahead_days: int
    ) -> list[Meeting]:
        start = now.astimezone(UTC) - timedelta(hours=12)
        end = now.astimezone(UTC) + timedelta(days=lookahead_days)
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$select": (
                "id,subject,start,end,isCancelled,isAllDay,isOnlineMeeting,"
                "onlineMeetingProvider,onlineMeeting,responseStatus"
            ),
            "$orderby": "start/dateTime",
            "$top": "100",
        }

        data = self._get("/me/calendarView", params=params)
        first_page = data.get("value", [])
        if not isinstance(first_page, list):
            raise GraphError("Microsoft Graph returned an invalid calendar page")
        events: list[object] = list(first_page)
        # A seven-day personal view normally fits one page. Follow a bounded number
        # of pages so a pathological calendar cannot trap the ambient display.
        for _ in range(4):
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            data = self._get(str(next_link))
            page = data.get("value", [])
            if not isinstance(page, list):
                raise GraphError("Microsoft Graph returned an invalid calendar page")
            events.extend(page)

        meetings = [
            meeting
            for event in events
            if isinstance(event, dict) and (meeting := parse_event(event))
        ]
        return sorted(meetings, key=lambda meeting: meeting.start)


def parse_graph_datetime(value: object) -> datetime:
    if not isinstance(value, dict) or not value.get("dateTime"):
        raise ValueError("event has no dateTime")
    raw = str(value["dateTime"])
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    # Requests ask Graph for UTC. Some Graph responses still omit the offset while
    # carrying a separate `timeZone: UTC` field, so normalize naive values here.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def parse_event(event: dict[str, Any]) -> Meeting | None:
    if event.get("isCancelled") or event.get("isAllDay"):
        return None
    response_status = event.get("responseStatus")
    response = (
        str(response_status.get("response", "")).casefold()
        if isinstance(response_status, dict)
        else ""
    )
    if response == "declined":
        return None

    provider = str(event.get("onlineMeetingProvider", "")).casefold()
    online = event.get("onlineMeeting") or {}
    join_url = online.get("joinUrl") if isinstance(online, dict) else None
    is_teams = provider == "teamsforbusiness" or (
        isinstance(join_url, str)
        and ("teams.microsoft.com/" in join_url or "teams.live.com/" in join_url)
    )
    if not event.get("isOnlineMeeting") or not is_teams:
        return None

    try:
        start = parse_graph_datetime(event.get("start"))
        end = parse_graph_datetime(event.get("end"))
    except (TypeError, ValueError):
        logger.warning("Skipping a Teams event with invalid dates")
        return None
    if end <= start:
        return None
    return Meeting(
        event_id=str(event.get("id", "")),
        subject=clean_subject(event.get("subject")),
        start=start,
        end=end,
        join_url=join_url if isinstance(join_url, str) else None,
    )
