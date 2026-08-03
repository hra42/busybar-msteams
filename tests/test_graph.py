from datetime import UTC, datetime

from busybar_msteams.graph import parse_event


def graph_event(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "id": "event-1",
        "subject": "  Weekly\nstand-up  ",
        "start": {"dateTime": "2026-08-03T10:00:00Z", "timeZone": "UTC"},
        "end": {"dateTime": "2026-08-03T11:00:00Z", "timeZone": "UTC"},
        "isCancelled": False,
        "isAllDay": False,
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/x"},
        "responseStatus": {"response": "accepted"},
    }
    event.update(overrides)
    return event


def test_parses_teams_event() -> None:
    event = parse_event(graph_event())
    assert event is not None
    assert event.subject == "Weekly stand-up"
    assert event.start == datetime(2026, 8, 3, 10, tzinfo=UTC)


def test_ignores_declined_cancelled_and_non_teams_events() -> None:
    assert parse_event(graph_event(responseStatus={"response": "declined"})) is None
    assert parse_event(graph_event(isCancelled=True)) is None
    assert (
        parse_event(
            graph_event(
                onlineMeetingProvider="zoom",
                onlineMeeting={"joinUrl": "https://zoom.us/j/1"},
            )
        )
        is None
    )


def test_accepts_teams_join_url_when_provider_is_missing() -> None:
    assert parse_event(graph_event(onlineMeetingProvider="unknown")) is not None
