"""Tests for radio_plan slot assignment."""

import pytest

from beeplan.radio_plan import (
    MAX_DEVICES_PER_CONCENTRATOR,
    SLOT_DURATION_SEC,
    assign_telemetry_slot,
)


def test_slot_assignment_no_collision_first_100() -> None:
    slots = [assign_telemetry_slot(i) for i in range(MAX_DEVICES_PER_CONCENTRATOR)]
    assert len(set(slots)) == MAX_DEVICES_PER_CONCENTRATOR
    assert slots[1] - slots[0] == SLOT_DURATION_SEC


def test_slot_at_capacity_raises() -> None:
    with pytest.raises(ValueError):
        assign_telemetry_slot(MAX_DEVICES_PER_CONCENTRATOR)


def test_find_free_slot_skips_occupied() -> None:
    from beeplan.radio_plan import find_free_telemetry_slot

    occupied = {assign_telemetry_slot(0), assign_telemetry_slot(2)}
    assert find_free_telemetry_slot(occupied) == assign_telemetry_slot(1)
