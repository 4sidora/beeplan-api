"""Tests for concentrator capacity limits."""

from beeplan.radio_plan import MAX_DEVICES_PER_CONCENTRATOR


def test_max_devices_per_concentrator() -> None:
    assert MAX_DEVICES_PER_CONCENTRATOR == 100
