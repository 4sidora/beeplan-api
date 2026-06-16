"""TDMA slot assignment for edge devices (DB-backed)."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from beeplan.models import EdgeDevice
from beeplan.radio_plan import MAX_DEVICES_PER_CONCENTRATOR, find_free_telemetry_slot
from beeplan.soft_delete import edge_active


def ensure_edge_telemetry_slot(db: Session, device: EdgeDevice) -> int:
    """Assign TDMA slot if missing (legacy/demo devices)."""
    if device.telemetry_slot_sec is not None:
        return device.telemetry_slot_sec
    occupied = set(
        db.scalars(
            select(EdgeDevice.telemetry_slot_sec).where(
                EdgeDevice.concentrator_id == device.concentrator_id,
                edge_active(),
                EdgeDevice.telemetry_slot_sec.isnot(None),
                EdgeDevice.id != device.id,
            )
        ).all()
    )
    try:
        slot = find_free_telemetry_slot(occupied)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No free telemetry slots on concentrator ({MAX_DEVICES_PER_CONCENTRATOR} max)",
        ) from exc
    device.telemetry_slot_sec = slot
    db.add(device)
    return slot
