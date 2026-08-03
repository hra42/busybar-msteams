from datetime import UTC, datetime, timedelta

from busybar_msteams.display import build_payload
from busybar_msteams.models import Meeting, ScreenMode, ScreenState, TeamsPresence


def test_on_call_payload_is_red_and_mentions_on_call() -> None:
    now = datetime(2026, 8, 3, 10, tzinfo=UTC)
    state = ScreenState(
        ScreenMode.ON_CALL,
        presence=TeamsPresence("Busy", "InACall"),
    )
    payload = build_payload(state, now)
    dumped = payload.model_dump()
    assert dumped["priority"] == 90
    assert dumped["led_notification_color"] == "#B00020FF"
    assert any(element.get("text") == "ON CALL" for element in dumped["elements"])


def test_upcoming_payload_displays_countdown_in_hours() -> None:
    now = datetime(2026, 8, 3, 10, tzinfo=UTC)
    state = ScreenState(
        ScreenMode.UPCOMING,
        meeting=Meeting(
            "1",
            "Roadmap",
            now + timedelta(hours=2.01),
            now + timedelta(hours=3),
        ),
        presence=TeamsPresence("Available", "Available"),
    )
    payload = build_payload(state, now).model_dump()
    assert any(element.get("text") == "NEXT 2.1h" for element in payload["elements"])
