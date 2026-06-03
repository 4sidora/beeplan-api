"""Мягкое удаление базовых станций и edge-устройств."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from beeplan.models import Concentrator, EdgeDevice, EdgeDeviceColonyAssignment


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def concentrator_active() -> bool:
    return Concentrator.deleted_at.is_(None)


def edge_active() -> bool:
    return EdgeDevice.deleted_at.is_(None)


def require_active_concentrator(conc: Concentrator | None) -> Concentrator:
    if conc is None or conc.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Concentrator not found")
    return conc


def require_active_edge(device: EdgeDevice | None) -> EdgeDevice:
    if device is None or device.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


def soft_delete_edge(db: Session, device: EdgeDevice, *, now: datetime | None = None) -> None:
    now = now or utc_now()
    open_rows = list(
        db.scalars(
            select(EdgeDeviceColonyAssignment).where(
                EdgeDeviceColonyAssignment.device_id == device.id,
                EdgeDeviceColonyAssignment.detached_at.is_(None),
            )
        ).all()
    )
    for row in open_rows:
        row.detached_at = now
    device.current_colony_id = None
    device.deleted_at = now
    db.add(device)


def soft_delete_concentrator(db: Session, conc: Concentrator, *, now: datetime | None = None) -> None:
    now = now or utc_now()
    edges = list(
        db.scalars(
            select(EdgeDevice).where(
                EdgeDevice.concentrator_id == conc.id,
                edge_active(),
            )
        ).all()
    )
    for device in edges:
        soft_delete_edge(db, device, now=now)
    conc.deleted_at = now
    db.add(conc)
