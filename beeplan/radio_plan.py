"""TDMA slot assignment for ESP-NOW v2 edge devices."""

from __future__ import annotations

MAX_DEVICES_PER_CONCENTRATOR = 100
SLOT_DURATION_SEC = 36
HOUR_SEC = 3600


def assign_telemetry_slot(active_device_count: int) -> int:
    """Return slot offset (0..3599) for the next device on a concentrator."""
    if active_device_count < 0:
        raise ValueError("active_device_count must be non-negative")
    if active_device_count >= MAX_DEVICES_PER_CONCENTRATOR:
        raise ValueError(f"concentrator at capacity ({MAX_DEVICES_PER_CONCENTRATOR} devices)")
    return (active_device_count % MAX_DEVICES_PER_CONCENTRATOR) * SLOT_DURATION_SEC
