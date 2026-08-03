from __future__ import annotations

import getpass
import logging
from collections.abc import Callable

from busylib import BusyBar, BusyBarDevices, exceptions, types
from busylib.devices import BusyBarDevice

logger = logging.getLogger(__name__)

USB_FALLBACK_ADDRESS = "10.0.4.20"


class DeviceDiscoveryError(RuntimeError):
    pass


def device_address(device: BusyBarDevice) -> str | None:
    """Prefer a normal network address, then fall back to USB networking."""
    return device.get_address("over_wifi") or device.get_address("over_usb")


def resolve_device(
    explicit_address: str | None,
    *,
    device_name: str | None = None,
    timeout: float = 1.5,
) -> str:
    if explicit_address:
        logger.info("Using configured BUSY Bar at %s", explicit_address)
        return explicit_address

    logger.info("Discovering BUSY Bar devices")
    devices = BusyBarDevices.discover(timeout=timeout)
    if not devices:
        # Current factory firmware can be reachable over USB without advertising
        # the mDNS service, so this is a compatibility fallback rather than an
        # assumption that discovery failed.
        logger.info(
            "No BUSY Bar found via mDNS; trying USB address %s",
            USB_FALLBACK_ADDRESS,
        )
        return USB_FALLBACK_ADDRESS

    selected = _select_device(devices, device_name)
    address = device_address(selected)
    if address is None:
        raise DeviceDiscoveryError(
            f"Discovered BUSY Bar {selected.name!r} has no usable IPv4 address"
        )
    logger.info("Using discovered BUSY Bar %s at %s", selected.name, address)
    return address


def resolve_access_token(
    address: str,
    configured_token: str | None,
    *,
    prompt: Callable[[str], str] = getpass.getpass,
) -> str | None:
    """Prompt for the device PIN when the selected bar requires one."""
    access = _read_access_info(address, configured_token)
    if access is None or access.mode != "key":
        return configured_token

    if configured_token and _token_is_valid(address, configured_token):
        return configured_token
    if configured_token:
        logger.warning("The configured BUSY Bar access PIN was rejected")

    for _ in range(3):
        try:
            token = prompt("BUSY Bar access PIN: ").strip()
        except (EOFError, KeyboardInterrupt) as error:
            raise DeviceDiscoveryError(
                "BUSY Bar requires an access PIN; set BUSYBAR_TOKEN or "
                "[busybar].token in config.toml"
            ) from error
        if not token:
            raise DeviceDiscoveryError(
                "BUSY Bar requires an access PIN; set BUSYBAR_TOKEN or "
                "[busybar].token in config.toml"
            )
        if _token_is_valid(address, token):
            return token
        print("BUSY Bar rejected that PIN.")
    raise DeviceDiscoveryError("BUSY Bar access PIN was rejected three times")


def _read_access_info(address: str, token: str | None) -> types.HttpAccessInfo | None:
    try:
        with BusyBar(address, token=token, timeout=5.0, max_retries=0) as device:
            return device.access()
    except exceptions.BusyBarError as error:
        logger.warning("Could not read BUSY Bar access mode: %s", error)
        return None


def _token_is_valid(address: str, token: str) -> bool:
    try:
        with BusyBar(address, token=token, timeout=5.0, max_retries=0) as device:
            device.display_brightness()
        return True
    except exceptions.BusyBarAPIError as error:
        if error.status_code == 403:
            return False
        raise DeviceDiscoveryError(
            f"Could not verify BUSY Bar access: {error}"
        ) from error
    except exceptions.BusyBarError as error:
        raise DeviceDiscoveryError(
            f"Could not verify BUSY Bar access: {error}"
        ) from error


def _select_device(
    devices: list[BusyBarDevice], device_name: str | None
) -> BusyBarDevice:
    if device_name:
        wanted = device_name.casefold()
        matches = [
            device
            for device in devices
            if device.name.casefold() == wanted
            or device.temporary_id.casefold() == wanted
        ]
        if len(matches) == 1:
            return matches[0]
        available = ", ".join(sorted(device.name for device in devices))
        raise DeviceDiscoveryError(
            f"No unique BUSY Bar matching {device_name!r}; found: {available}"
        )

    if len(devices) == 1:
        return devices[0]

    print("Found multiple BUSY Bar devices:")
    for index, device in enumerate(devices, start=1):
        address = device_address(device) or "no usable address"
        print(f"  {index}. {device.name} ({address})")
    while True:
        try:
            choice = input(f"Select a device [1-{len(devices)}]: ").strip()
        except EOFError as error:
            raise DeviceDiscoveryError(
                "Multiple BUSY Bars found in a non-interactive session; "
                "set BUSYBAR_NAME or pass --device-name"
            ) from error
        if choice.isdigit() and 1 <= int(choice) <= len(devices):
            return devices[int(choice) - 1]
        print(f"Enter a number between 1 and {len(devices)}.")
