from datetime import UTC, datetime, timedelta

from busybar_msteams.models import (
    Meeting,
    ScreenMode,
    TeamsPresence,
    build_screen_state,
    format_hours,
)

NOW = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)


def meeting(start_hours: float, end_hours: float) -> Meeting:
    return Meeting(
        event_id=str(start_hours),
        subject="Architecture review",
        start=NOW + timedelta(hours=start_hours),
        end=NOW + timedelta(hours=end_hours),
    )


def test_live_call_wins_even_without_a_calendar_event() -> None:
    presence = TeamsPresence("Busy", "InACall")
    assert build_screen_state([], presence, NOW).mode is ScreenMode.ON_CALL


def test_live_call_is_not_labeled_with_an_unrelated_future_meeting() -> None:
    state = build_screen_state([meeting(2, 3)], TeamsPresence("Busy", "InACall"), NOW)
    assert state.mode is ScreenMode.ON_CALL
    assert state.meeting is None


def test_presenting_is_on_call_but_calendar_in_meeting_is_not() -> None:
    assert TeamsPresence("DoNotDisturb", "Presenting").is_on_call
    assert not TeamsPresence("Busy", "InAMeeting").is_on_call


def test_scheduled_meeting_does_not_claim_user_is_on_call() -> None:
    state = build_screen_state(
        [meeting(-0.5, 0.5)], TeamsPresence("Busy", "InAMeeting"), NOW
    )
    assert state.mode is ScreenMode.MEETING_NOW


def test_next_meeting_and_hours_are_selected() -> None:
    state = build_screen_state(
        [meeting(3, 4), meeting(1.21, 2)], TeamsPresence("Available", "Available"), NOW
    )
    assert state.mode is ScreenMode.UPCOMING
    assert state.meeting and state.meeting.start == NOW + timedelta(hours=1.21)
    assert format_hours(state.meeting.start, NOW) == "1.3h"
