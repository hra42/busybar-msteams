from datetime import UTC, datetime, timedelta

from busybar_msteams.models import (
    Meeting,
    ScreenMode,
    TeamsPresence,
    build_screen_state,
    format_countdown,
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
    assert state.mode is ScreenMode.IDLE


def test_meeting_in_progress_is_skipped_for_the_next_one() -> None:
    state = build_screen_state(
        [meeting(-0.5, 0.5), meeting(2, 3)],
        TeamsPresence("Available", "Available"),
        NOW,
    )
    assert state.mode is ScreenMode.UPCOMING
    assert state.meeting and state.meeting.start == NOW + timedelta(hours=2)


def test_next_meeting_and_hours_are_selected() -> None:
    state = build_screen_state(
        [meeting(3, 4), meeting(1.21, 2)], TeamsPresence("Available", "Available"), NOW
    )
    assert state.mode is ScreenMode.UPCOMING
    assert state.meeting and state.meeting.start == NOW + timedelta(hours=1.21)
    assert format_countdown(state.meeting.start, NOW) == "1.3h"


def test_countdown_under_an_hour_shows_minutes_and_seconds() -> None:
    assert format_countdown(NOW + timedelta(minutes=59, seconds=59), NOW) == "59:59"
    assert format_countdown(NOW + timedelta(minutes=5, seconds=30), NOW) == "5:30"
    assert format_countdown(NOW + timedelta(seconds=45), NOW) == "0:45"
    assert format_countdown(NOW + timedelta(seconds=5), NOW) == "0:05"
    assert format_countdown(NOW, NOW) == "NOW"


def test_countdown_at_and_above_an_hour_stays_in_hours() -> None:
    assert format_countdown(NOW + timedelta(hours=1), NOW) == "1.0h"
    assert format_countdown(NOW + timedelta(hours=12), NOW) == "12h"
