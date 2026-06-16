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


def find_free_telemetry_slot(occupied_slots: set[int]) -> int:
    """Pick the first TDMA slot not in *occupied_slots*."""
    for i in range(MAX_DEVICES_PER_CONCENTRATOR):
        slot = assign_telemetry_slot(i)
        if slot not in occupied_slots:
            return slot
    raise ValueError(f"concentrator at capacity ({MAX_DEVICES_PER_CONCENTRATOR} devices)")
