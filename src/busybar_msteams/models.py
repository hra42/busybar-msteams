from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ScreenMode(StrEnum):
    ON_CALL = "on_call"
    MEETING_NOW = "meeting_now"
    UPCOMING = "upcoming"
    IDLE = "idle"
    ERROR = "error"


@dataclass(frozen=True)
class Meeting:
    event_id: str
    subject: str
    start: datetime
    end: datetime
    join_url: str | None = None


@dataclass(frozen=True)
class TeamsPresence:
    availability: str
    activity: str

    @property
    def is_on_call(self) -> bool:
        # InAMeeting is deliberately excluded: Teams derives it from the calendar,
        # while these values mean the user is actually in a call or presenting.
        return self.activity.casefold() in {
            "inacall",
            "inaconferencecall",
            "presenting",
        }


@dataclass(frozen=True)
class ScreenState:
    mode: ScreenMode
    meeting: Meeting | None = None
    presence: TeamsPresence | None = None
    message: str | None = None


def select_current_or_next(
    meetings: list[Meeting], now: datetime
) -> tuple[Meeting | None, bool]:
    """Return the current meeting, otherwise the next meeting, and whether current."""
    current = [meeting for meeting in meetings if meeting.start <= now < meeting.end]
    if current:
        return min(current, key=lambda meeting: meeting.end), True

    upcoming = [meeting for meeting in meetings if meeting.start > now]
    if upcoming:
        return min(upcoming, key=lambda meeting: meeting.start), False
    return None, False


def build_screen_state(
    meetings: list[Meeting], presence: TeamsPresence, now: datetime
) -> ScreenState:
    meeting, is_current = select_current_or_next(meetings, now)
    if presence.is_on_call:
        # An upcoming appointment is not necessarily the call currently in
        # progress. Only attach calendar details while their time range overlaps.
        return ScreenState(
            ScreenMode.ON_CALL,
            meeting=meeting if is_current else None,
            presence=presence,
        )
    if is_current:
        return ScreenState(ScreenMode.MEETING_NOW, meeting=meeting, presence=presence)
    if meeting:
        return ScreenState(ScreenMode.UPCOMING, meeting=meeting, presence=presence)
    return ScreenState(ScreenMode.IDLE, presence=presence)


def format_hours(until: datetime, now: datetime) -> str:
    """Format a future instant as a conservative hours countdown."""
    hours = max(0.0, (until - now).total_seconds() / 3600)
    if hours == 0:
        return "NOW"
    if hours < 0.1:
        return "<0.1h"
    if hours < 10:
        return f"{math.ceil(hours * 10) / 10:.1f}h"
    return f"{math.ceil(hours):d}h"


def clean_subject(value: str | None, limit: int = 120) -> str:
    subject = " ".join((value or "Teams meeting").split())
    return subject[:limit] or "Teams meeting"
