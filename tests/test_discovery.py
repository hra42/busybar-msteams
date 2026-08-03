import pytest
from busylib.devices import BusyBarAddress, BusyBarAddressAffinity, BusyBarDevice
from busylib.types import HttpAccessInfo

from busybar_msteams import discovery


def bar(
    name: str,
    wifi: str | None = None,
    usb: str | None = None,
    temporary_id: str = "id",
) -> BusyBarDevice:
    addresses = set()
    if wifi:
        addresses.add(BusyBarAddress(wifi, BusyBarAddressAffinity.OVER_WIFI))
    if usb:
        addresses.add(BusyBarAddress(usb, BusyBarAddressAffinity.OVER_USB))
    return BusyBarDevice(name, temporary_id, addresses)


def test_explicit_address_bypasses_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        discovery.BusyBarDevices,
        "discover",
        lambda timeout: pytest.fail("discovery should not run"),
    )
    assert discovery.resolve_device("192.168.1.7") == "192.168.1.7"


def test_single_device_is_discovered_and_wifi_is_preferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = bar("Office", wifi="192.168.1.7", usb="10.0.4.20")
    monkeypatch.setattr(discovery.BusyBarDevices, "discover", lambda timeout: [device])
    assert discovery.resolve_device(None) == "192.168.1.7"


def test_device_can_be_selected_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    devices = [bar("Office", "192.168.1.7"), bar("Kitchen", "192.168.1.8")]
    monkeypatch.setattr(discovery.BusyBarDevices, "discover", lambda timeout: devices)
    assert discovery.resolve_device(None, device_name="kitchen") == "192.168.1.8"


def test_multiple_devices_prompt_for_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    devices = [bar("Office", "192.168.1.7"), bar("Kitchen", "192.168.1.8")]
    monkeypatch.setattr(discovery.BusyBarDevices, "discover", lambda timeout: devices)
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    assert discovery.resolve_device(None) == "192.168.1.8"


def test_no_discovered_device_uses_usb_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery.BusyBarDevices, "discover", lambda timeout: [])
    assert discovery.resolve_device(None) == "10.0.4.20"


def test_access_pin_is_prompted_and_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        discovery,
        "_read_access_info",
        lambda address, token: HttpAccessInfo(mode="key", key_valid=True),
    )
    monkeypatch.setattr(
        discovery, "_token_is_valid", lambda address, token: token == "1234"
    )

    token = discovery.resolve_access_token(
        "192.168.1.7", None, prompt=lambda message: "1234"
    )

    assert token == "1234"


def test_valid_configured_pin_does_not_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        discovery,
        "_read_access_info",
        lambda address, token: HttpAccessInfo(mode="key", key_valid=True),
    )
    monkeypatch.setattr(discovery, "_token_is_valid", lambda address, token: True)

    token = discovery.resolve_access_token(
        "192.168.1.7",
        "4321",
        prompt=lambda message: pytest.fail("should not prompt"),
    )

    assert token == "4321"
