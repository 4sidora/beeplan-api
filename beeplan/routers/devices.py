from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from beeplan.schemas import (
    EdgeDeviceCreate,
    EdgeDeviceOut,
    EdgeDeviceUpdate,
    SetColonyBody,
    TelemetryBatchIn,
    TelemetryBatchOut,
    TelemetryPointOut,
)

router = APIRouter(prefix="/v1", tags=["devices"])


def _device_out(device: EdgeDevice, db: Session) -> EdgeDeviceOut:
    conc = db.get(Concentrator, device.concentrator_id)
    return EdgeDeviceOut(
        id=device.id,
        concentrator_id=device.concentrator_id,
        concentrator_name=conc.name if conc else None,
        public_id=device.public_id,
        label=device.label,
        current_colony_id=device.current_colony_id,
    )


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


def _ensure_concentrator_owned(db: Session, user: User, concentrator_id: int) -> Concentrator:
    conc = db.get(Concentrator, concentrator_id)
    if conc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Concentrator not found")
    apiary = db.get(Apiary, conc.apiary_id)
    if apiary is None or apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return conc


def _apply_colony_assignment(
    db: Session,
    device: EdgeDevice,
    colony_id: int | None,
    *,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)

    if colony_id is not None:
        colony = db.get(Colony, colony_id)
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

    if colony_id is not None:
        db.add(EdgeDeviceColonyAssignment(device_id=device.id, colony_id=colony_id, attached_at=now))
        device.current_colony_id = colony_id
    else:
        device.current_colony_id = None


@router.get("/edge-devices", response_model=list[EdgeDeviceOut])
def list_edge_devices(
    apiary_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EdgeDeviceOut]:
    apiary = db.get(Apiary, apiary_id)
    if apiary is None or apiary.user_id != user.id:
        return []
    conc_ids = list(
        db.scalars(select(Concentrator.id).where(Concentrator.apiary_id == apiary_id)).all()
    )
    if not conc_ids:
        return []
    devices = list(
        db.scalars(select(EdgeDevice).where(EdgeDevice.concentrator_id.in_(conc_ids))).all()
    )
    return [_device_out(d, db) for d in devices]


@router.post("/edge-devices", response_model=EdgeDeviceOut, status_code=status.HTTP_201_CREATED)
def create_edge_device(
    body: EdgeDeviceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EdgeDeviceOut:
    _ensure_concentrator_owned(db, user, body.concentrator_id)
    device = EdgeDevice(
        concentrator_id=body.concentrator_id,
        public_id=body.public_id,
        label=body.label,
    )
    db.add(device)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Device public_id already exists")

    if body.colony_id is not None:
        _apply_colony_assignment(db, device, body.colony_id)

    db.add(device)
    db.commit()
    db.refresh(device)
    return _device_out(device, db)


@router.patch("/edge-devices/{device_id}", response_model=EdgeDeviceOut)
def update_edge_device(
    device_id: int,
    body: EdgeDeviceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EdgeDevice:
    device = _ensure_device_owned(db, user, device_id)
    if body.public_id is not None:
        device.public_id = body.public_id
    if body.label is not None:
        device.label = body.label
    db.add(device)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Device public_id already exists")
    db.refresh(device)
    return _device_out(device, db)


@router.delete("/edge-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    device = _ensure_device_owned(db, user, device_id)
    db.delete(device)
    db.commit()


@router.put("/edge-devices/{device_id}/colony", response_model=EdgeDeviceOut)
def set_device_colony(
    device_id: int,
    body: SetColonyBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EdgeDevice:
    device = _ensure_device_owned(db, user, device_id)
    _apply_colony_assignment(db, device, body.colony_id)
    db.add(device)
    db.commit()
    db.refresh(device)
    return _device_out(device, db)


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
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TelemetrySample]:
    colony = db.get(Colony, colony_id)
    if colony is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colony not found")
    apiary = db.get(Apiary, colony.apiary_id)
    if apiary is None or apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

    stmt = select(TelemetrySample).where(TelemetrySample.colony_id == colony_id)
    if metric:
        stmt = stmt.where(TelemetrySample.metric == metric)
    if from_ts is not None:
        stmt = stmt.where(TelemetrySample.ts >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(TelemetrySample.ts <= to_ts)
    stmt = stmt.order_by(TelemetrySample.ts.desc()).limit(min(limit, 5000))
    rows = list(db.scalars(stmt).all())
    rows.reverse()
    return rows
