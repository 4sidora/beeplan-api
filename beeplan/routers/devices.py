from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from beeplan.database import get_db
from beeplan.deps import get_current_user, require_concentrator
from beeplan.models import (
    Apiary,
    Colony,
    Concentrator,
    EdgeDevice,
    EdgeDeviceColonyAssignment,
    TelemetrySample,
    User,
)
from beeplan.schemas import EdgeDeviceOut, SetColonyBody, TelemetryBatchIn, TelemetryBatchOut, TelemetryPointOut

router = APIRouter(prefix="/v1", tags=["devices"])


def _ensure_device_owned(db: Session, user: User, device_id: int) -> EdgeDevice:
    device = db.get(EdgeDevice, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    conc = db.get(Concentrator, device.concentrator_id)
    if conc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Concentrator not found")
    apiary = db.get(Apiary, conc.apiary_id)
    if apiary is None or apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return device


@router.get("/edge-devices", response_model=list[EdgeDeviceOut])
def list_edge_devices(
    apiary_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EdgeDevice]:
    apiary = db.get(Apiary, apiary_id)
    if apiary is None or apiary.user_id != user.id:
        return []
    conc_ids = list(
        db.scalars(select(Concentrator.id).where(Concentrator.apiary_id == apiary_id)).all()
    )
    if not conc_ids:
        return []
    return list(db.scalars(select(EdgeDevice).where(EdgeDevice.concentrator_id.in_(conc_ids))).all())


@router.put("/edge-devices/{device_id}/colony", response_model=EdgeDeviceOut)
def set_device_colony(
    device_id: int,
    body: SetColonyBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EdgeDevice:
    device = _ensure_device_owned(db, user, device_id)
    now = datetime.now(timezone.utc)

    if body.colony_id is not None:
        colony = db.get(Colony, body.colony_id)
        if colony is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Colony not found")
        conc = db.get(Concentrator, device.concentrator_id)
        if conc is None or colony.apiary_id != conc.apiary_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Colony must belong to the same apiary as the device")

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

    if body.colony_id is not None:
        db.add(EdgeDeviceColonyAssignment(device_id=device.id, colony_id=body.colony_id, attached_at=now))
        device.current_colony_id = body.colony_id
    else:
        device.current_colony_id = None

    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.post("/telemetry/batch", response_model=TelemetryBatchOut)
def ingest_telemetry(
    body: TelemetryBatchIn,
    db: Session = Depends(get_db),
    concentrator: Concentrator = Depends(require_concentrator),
) -> TelemetryBatchOut:
    inserted = 0
    skipped = 0
    errors: list[str] = []

    for s in body.samples:
        device = db.scalars(
            select(EdgeDevice).where(
                EdgeDevice.concentrator_id == concentrator.id,
                EdgeDevice.public_id == s.device_public_id,
            )
        ).first()
        if device is None:
            skipped += 1
            errors.append(f"unknown device {s.device_public_id}")
            continue
        if device.current_colony_id is None:
            skipped += 1
            errors.append(f"device {s.device_public_id} has no active colony")
            continue
        db.add(
            TelemetrySample(
                colony_id=device.current_colony_id,
                source_device_id=device.id,
                metric=s.metric,
                ts=s.ts,
                value=s.value if isinstance(s.value, (dict, list)) else {"v": s.value},
            )
        )
        inserted += 1

    db.commit()
    return TelemetryBatchOut(inserted=inserted, skipped=skipped, errors=errors[:50])


@router.get("/colonies/{colony_id}/telemetry", response_model=list[TelemetryPointOut])
def get_colony_telemetry(
    colony_id: int,
    metric: str | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TelemetrySample]:
    colony = db.get(Colony, colony_id)
    if colony is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colony not found")
    apiary = db.get(Apiary, colony.apiary_id)
    if apiary is None or apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

    stmt = select(TelemetrySample).where(TelemetrySample.colony_id == colony_id).order_by(TelemetrySample.ts.desc())
    if metric:
        stmt = stmt.where(TelemetrySample.metric == metric)
    stmt = stmt.limit(min(limit, 5000))
    rows = list(db.scalars(stmt).all())
    rows.reverse()
    return rows
