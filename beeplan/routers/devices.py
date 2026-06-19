from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from beeplan.database import get_db
from beeplan.deps import get_current_user, require_concentrator
from beeplan.soft_delete import (
    concentrator_active,
    edge_active,
    require_active_concentrator,
    require_active_edge,
    soft_delete_edge,
)
from beeplan.models import (
    Apiary,
    Colony,
    Concentrator,
    ConcentratorTelemetrySample,
    EdgeDevice,
    EdgeDeviceColonyAssignment,
    EdgeDeviceTelemetrySample,
    TelemetryIngestLog,
    TelemetrySample,
    User,
)
from beeplan.radio_plan import MAX_DEVICES_PER_CONCENTRATOR
from beeplan.schemas import (
    ConcentratorHeartbeatIn,
    ConcentratorHeartbeatOut,
    EdgeDeviceCreate,
    EdgeDeviceOut,
    EdgeDeviceUpdate,
    EdgeHeartbeatConfigOut,
    GatewayBatchStatusIn,
    SetColonyBody,
    TelemetryBatchIn,
    TelemetryBatchOut,
    TelemetryPointOut,
)

router = APIRouter(prefix="/v1", tags=["devices"])

_UNBOUND_TELEMETRY_PREVIEW = 8
_PUBLIC_ID_RETRIES = 5


_EDGE_TYPE_LABELS: dict[str, str] = {
    "multisensor": "Мультидатчик",
    "scales": "Весы",
}


def _generate_public_id() -> str:
    return f"edge-{uuid.uuid4().hex[:8]}"


def _public_id_suffix(public_id: str) -> str:
    prefix = "edge-"
    return public_id[len(prefix) :] if public_id.startswith(prefix) else public_id


def _default_edge_name(public_id: str, device_type: str = "multisensor") -> str:
    type_label = _EDGE_TYPE_LABELS.get(device_type, "Мультидатчик")
    return f"{type_label} {_public_id_suffix(public_id)}"


def _normalize_mac(mac: str) -> str:
    cleaned = mac.strip().upper().replace("-", ":")
    if ":" not in cleaned and len(cleaned) == 12 and all(c in "0123456789ABCDEF" for c in cleaned):
        cleaned = ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
    parts = cleaned.split(":")
    if len(parts) != 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid MAC address format")
    normalized: list[str] = []
    for part in parts:
        if len(part) == 1 and part in "0123456789ABCDEF":
            part = f"0{part}"
        if len(part) != 2 or not all(c in "0123456789ABCDEF" for c in part):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid MAC address format")
        normalized.append(part)
    return ":".join(normalized)


def _telemetry_point(
    row: EdgeDeviceTelemetrySample | TelemetrySample | ConcentratorTelemetrySample,
) -> TelemetryPointOut:
    return TelemetryPointOut(ts=row.ts, metric=row.metric, value=row.value)


def _firmware_version_from_value(value: dict | list | str | float | int | bool | None) -> str | None:
    if isinstance(value, dict):
        ver = value.get("version")
        if isinstance(ver, str) and ver.strip():
            return ver.strip()[:32]
    return None


def _apply_edge_metric_side_effects(
    device: EdgeDevice,
    metric: str,
    value: dict | list | str | float | int | bool | None,
) -> None:
    if metric == "firmware_version":
        ver = _firmware_version_from_value(value)
        if ver:
            device.firmware_version = ver


def _recent_concentrator_telemetry(db: Session, concentrator_id: int) -> list[TelemetryPointOut]:
    rows = list(
        db.scalars(
            select(ConcentratorTelemetrySample)
            .where(ConcentratorTelemetrySample.concentrator_id == concentrator_id)
            .order_by(ConcentratorTelemetrySample.ts.desc())
            .limit(_UNBOUND_TELEMETRY_PREVIEW)
        ).all()
    )
    rows.reverse()
    return [_telemetry_point(r) for r in rows]


def _fetch_concentrator_telemetry(
    db: Session,
    concentrator_id: int,
    *,
    metric: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int,
) -> list[TelemetryPointOut]:
    cap = min(limit, 5000)
    stmt = select(ConcentratorTelemetrySample).where(
        ConcentratorTelemetrySample.concentrator_id == concentrator_id
    )
    if metric:
        stmt = stmt.where(ConcentratorTelemetrySample.metric == metric)
    if from_ts is not None:
        stmt = stmt.where(ConcentratorTelemetrySample.ts >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(ConcentratorTelemetrySample.ts <= to_ts)
    stmt = stmt.order_by(ConcentratorTelemetrySample.ts.desc()).limit(cap)
    rows = list(db.scalars(stmt).all())
    rows.reverse()
    return [_telemetry_point(r) for r in rows]


def _store_concentrator_telemetry(
    db: Session,
    concentrator_id: int,
    metric: str,
    value: dict | list | str | float | int | bool | None,
    ts: datetime,
) -> None:
    db.add(
        ConcentratorTelemetrySample(
            concentrator_id=concentrator_id,
            metric=metric,
            ts=ts,
            value=value,
        )
    )


def _apply_gateway_batch_status(
    db: Session,
    concentrator_id: int,
    gateway: GatewayBatchStatusIn | None,
    ts: datetime,
) -> None:
    if gateway is None:
        return
    if gateway.signal_dbm is not None:
        _store_concentrator_telemetry(
            db,
            concentrator_id,
            "signal_level",
            {"dbm": gateway.signal_dbm},
            ts,
        )
    if gateway.battery_volts is not None:
        _store_concentrator_telemetry(
            db,
            concentrator_id,
            "battery_voltage",
            {"volts": round(gateway.battery_volts, 2)},
            ts,
        )


def _recent_device_telemetry(db: Session, device: EdgeDevice) -> list[TelemetryPointOut]:
    if device.current_colony_id is None:
        rows = list(
            db.scalars(
                select(EdgeDeviceTelemetrySample)
                .where(EdgeDeviceTelemetrySample.device_id == device.id)
                .order_by(EdgeDeviceTelemetrySample.ts.desc())
                .limit(_UNBOUND_TELEMETRY_PREVIEW)
            ).all()
        )
    else:
        rows = list(
            db.scalars(
                select(TelemetrySample)
                .where(TelemetrySample.source_device_id == device.id)
                .order_by(TelemetrySample.ts.desc())
                .limit(_UNBOUND_TELEMETRY_PREVIEW)
            ).all()
        )
    rows.reverse()
    return [_telemetry_point(r) for r in rows]


def _fetch_device_telemetry(
    db: Session,
    device_id: int,
    *,
    metric: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int,
) -> list[TelemetryPointOut]:
    cap = min(limit, 5000)

    unbound_stmt = select(EdgeDeviceTelemetrySample).where(
        EdgeDeviceTelemetrySample.device_id == device_id
    )
    if metric:
        unbound_stmt = unbound_stmt.where(EdgeDeviceTelemetrySample.metric == metric)
    if from_ts is not None:
        unbound_stmt = unbound_stmt.where(EdgeDeviceTelemetrySample.ts >= from_ts)
    if to_ts is not None:
        unbound_stmt = unbound_stmt.where(EdgeDeviceTelemetrySample.ts <= to_ts)

    colony_stmt = select(TelemetrySample).where(TelemetrySample.source_device_id == device_id)
    if metric:
        colony_stmt = colony_stmt.where(TelemetrySample.metric == metric)
    if from_ts is not None:
        colony_stmt = colony_stmt.where(TelemetrySample.ts >= from_ts)
    if to_ts is not None:
        colony_stmt = colony_stmt.where(TelemetrySample.ts <= to_ts)

    merged: list[EdgeDeviceTelemetrySample | TelemetrySample] = list(db.scalars(unbound_stmt).all())
    merged.extend(db.scalars(colony_stmt).all())
    merged.sort(key=lambda r: r.ts, reverse=True)
    merged = merged[:cap]
    merged.reverse()
    return [_telemetry_point(r) for r in merged]


def _device_out(device: EdgeDevice, db: Session) -> EdgeDeviceOut:
    conc = db.get(Concentrator, device.concentrator_id)
    conc_name = conc.name if conc and conc.deleted_at is None else None
    return EdgeDeviceOut(
        id=device.id,
        concentrator_id=device.concentrator_id,
        concentrator_name=conc_name,
        public_id=device.public_id,
        name=device.name,
        telemetry_slot_sec=device.telemetry_slot_sec,
        wake_interval_sec=device.wake_interval_sec,
        current_colony_id=device.current_colony_id,
        last_seen_at=device.last_seen_at,
        firmware_version=device.firmware_version,
        recent_telemetry=_recent_device_telemetry(db, device),
    )


def _ensure_device_owned(db: Session, user: User, device_id: int) -> EdgeDevice:
    device = db.get(EdgeDevice, device_id)
    require_active_edge(device)
    conc = db.get(Concentrator, device.concentrator_id)
    require_active_concentrator(conc)
    apiary = db.get(Apiary, conc.apiary_id)
    if apiary is None or apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return device


def _ensure_concentrator_owned(db: Session, user: User, concentrator_id: int) -> Concentrator:
    conc = db.get(Concentrator, concentrator_id)
    require_active_concentrator(conc)
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


def _normalize_value(value: dict | list | str | float | int | bool | None) -> dict | list | str | float | int | bool | None:
    if isinstance(value, (dict, list)):
        return value
    return {"v": value}


@router.get("/edge-devices", response_model=list[EdgeDeviceOut])
def list_edge_devices(
    apiary_id: int | None = Query(default=None),
    concentrator_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EdgeDeviceOut]:
    if concentrator_id is not None:
        _ensure_concentrator_owned(db, user, concentrator_id)
        devices = list(
            db.scalars(
                select(EdgeDevice)
                .where(
                    EdgeDevice.concentrator_id == concentrator_id,
                    edge_active(),
                )
                .order_by(EdgeDevice.created_at.asc())
            ).all()
        )
        return [_device_out(d, db) for d in devices]

    if apiary_id is not None:
        apiary = db.get(Apiary, apiary_id)
        if apiary is None or apiary.user_id != user.id:
            return []
        conc_ids = list(
            db.scalars(
                select(Concentrator.id).where(
                    Concentrator.apiary_id == apiary_id,
                    concentrator_active(),
                )
            ).all()
        )
    else:
        apiary_ids = list(
            db.scalars(select(Apiary.id).where(Apiary.user_id == user.id)).all()
        )
        if not apiary_ids:
            return []
        conc_ids = list(
            db.scalars(
                select(Concentrator.id).where(
                    Concentrator.apiary_id.in_(apiary_ids),
                    concentrator_active(),
                )
            ).all()
        )

    if not conc_ids:
        return []
    devices = list(
        db.scalars(
            select(EdgeDevice)
            .where(
                EdgeDevice.concentrator_id.in_(conc_ids),
                edge_active(),
            )
            .order_by(EdgeDevice.created_at.asc())
        ).all()
    )
    return [_device_out(d, db) for d in devices]


@router.get("/edge-devices/{device_id}", response_model=EdgeDeviceOut)
def get_edge_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EdgeDeviceOut:
    device = _ensure_device_owned(db, user, device_id)
    return _device_out(device, db)


@router.get("/edge-devices/{device_id}/telemetry", response_model=list[TelemetryPointOut])
def get_edge_device_telemetry(
    device_id: int,
    metric: str | None = None,
    limit: int = 100,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TelemetryPointOut]:
    _ensure_device_owned(db, user, device_id)
    return _fetch_device_telemetry(
        db,
        device_id,
        metric=metric,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )


@router.post("/edge-devices", response_model=EdgeDeviceOut, status_code=status.HTTP_201_CREATED)
def create_edge_device(
    body: EdgeDeviceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EdgeDeviceOut:
    _ensure_concentrator_owned(db, user, body.concentrator_id)
    active_count = db.scalar(
        select(func.count())
        .select_from(EdgeDevice)
        .where(EdgeDevice.concentrator_id == body.concentrator_id, edge_active())
    )
    if active_count is not None and active_count >= MAX_DEVICES_PER_CONCENTRATOR:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Concentrator at capacity ({MAX_DEVICES_PER_CONCENTRATOR} edge devices)",
        )
    raw_name = (body.name or "").strip()

    device: EdgeDevice | None = None
    for _ in range(_PUBLIC_ID_RETRIES):
        public_id = _generate_public_id()
        device_name = raw_name or _default_edge_name(public_id)
        candidate = EdgeDevice(
            concentrator_id=body.concentrator_id,
            public_id=public_id,
            name=device_name,
            wake_interval_sec=3600,
        )
        db.add(candidate)
        try:
            db.flush()
            device = candidate
            break
        except IntegrityError:
            db.rollback()
            device = None
    if device is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Could not allocate device public_id")

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
) -> EdgeDeviceOut:
    device = _ensure_device_owned(db, user, device_id)
    if body.name is not None:
        device.name = body.name.strip() or device.name
    if body.wake_interval_sec is not None:
        device.wake_interval_sec = body.wake_interval_sec
    db.add(device)
    db.commit()
    db.refresh(device)
    return _device_out(device, db)


@router.delete("/edge-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    device = _ensure_device_owned(db, user, device_id)
    soft_delete_edge(db, device)
    db.commit()


@router.put("/edge-devices/{device_id}/colony", response_model=EdgeDeviceOut)
def set_device_colony(
    device_id: int,
    body: SetColonyBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EdgeDeviceOut:
    device = _ensure_device_owned(db, user, device_id)
    _apply_colony_assignment(db, device, body.colony_id)
    db.add(device)
    db.commit()
    db.refresh(device)
    return _device_out(device, db)


@router.get("/concentrators/{concentrator_id}/telemetry", response_model=list[TelemetryPointOut])
def get_concentrator_telemetry(
    concentrator_id: int,
    metric: str | None = None,
    limit: int = 500,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TelemetryPointOut]:
    _ensure_concentrator_owned(db, user, concentrator_id)
    return _fetch_concentrator_telemetry(
        db,
        concentrator_id,
        metric=metric,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )


@router.post("/concentrators/heartbeat", response_model=ConcentratorHeartbeatOut)
def concentrator_heartbeat(
    body: ConcentratorHeartbeatIn,
    db: Session = Depends(get_db),
    concentrator: Concentrator = Depends(require_concentrator),
) -> ConcentratorHeartbeatOut:
    mac = _normalize_mac(body.mac)
    now = datetime.now(timezone.utc)
    concentrator.gateway_mac = mac
    concentrator.last_seen_at = now
    if body.firmware_version:
        concentrator.firmware_version = body.firmware_version
    if body.wifi_channel is not None:
        concentrator.wifi_channel = body.wifi_channel
    if body.spool_pending_count is not None:
        concentrator.spool_pending_count = body.spool_pending_count
    if body.signal_dbm is not None:
        _store_concentrator_telemetry(
            db,
            concentrator.id,
            "signal_level",
            {"dbm": body.signal_dbm},
            now,
        )
    db.add(concentrator)
    db.commit()

    edge_rows = list(
        db.scalars(
            select(EdgeDevice).where(
                EdgeDevice.concentrator_id == concentrator.id,
                edge_active(),
            )
        ).all()
    )
    edge_devices = [
        EdgeHeartbeatConfigOut(
            public_id=device.public_id,
            wake_interval_sec=int(device.wake_interval_sec or 3600),
        )
        for device in edge_rows
    ]
    return ConcentratorHeartbeatOut(gateway_mac=mac, edge_devices=edge_devices)


@router.post("/telemetry/batch", response_model=TelemetryBatchOut)
def ingest_telemetry(
    body: TelemetryBatchIn,
    db: Session = Depends(get_db),
    concentrator: Concentrator = Depends(require_concentrator),
) -> TelemetryBatchOut:
    if not body.samples:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty batch")

    inserted = 0
    skipped = 0
    errors: list[str] = []
    accepted_report_ids: list[str] = []
    now = datetime.now(timezone.utc)
    concentrator.last_seen_at = now
    db.add(concentrator)
    _apply_gateway_batch_status(db, concentrator.id, body.gateway, now)

    def _insert_sample(device: EdgeDevice, s) -> None:
        nonlocal inserted
        value = _normalize_value(s.value)
        _apply_edge_metric_side_effects(device, s.metric, value)
        device.last_seen_at = now
        db.add(device)
        if device.current_colony_id is None:
            db.add(
                EdgeDeviceTelemetrySample(
                    device_id=device.id,
                    metric=s.metric,
                    ts=s.ts,
                    value=value,
                )
            )
        else:
            db.add(
                TelemetrySample(
                    colony_id=device.current_colony_id,
                    source_device_id=device.id,
                    metric=s.metric,
                    ts=s.ts,
                    value=value,
                )
            )
        inserted += 1

    grouped: dict[str, list] = {}
    legacy_samples = []
    for s in body.samples:
        report_id = (s.report_id or "").strip()
        if report_id:
            grouped.setdefault(report_id, []).append(s)
        else:
            legacy_samples.append(s)

    for s in legacy_samples:
        device = db.scalars(
            select(EdgeDevice).where(
                EdgeDevice.concentrator_id == concentrator.id,
                EdgeDevice.public_id == s.device_public_id,
                edge_active(),
            )
        ).first()
        if device is None:
            skipped += 1
            errors.append(f"unknown device {s.device_public_id}")
            continue
        _insert_sample(device, s)

    for report_id, samples in grouped.items():
        if not samples:
            continue
        device = db.scalars(
            select(EdgeDevice).where(
                EdgeDevice.concentrator_id == concentrator.id,
                EdgeDevice.public_id == samples[0].device_public_id,
                edge_active(),
            )
        ).first()
        if device is None:
            skipped += len(samples)
            errors.append(f"unknown device {samples[0].device_public_id}")
            continue
        existing = db.scalars(
            select(TelemetryIngestLog.id).where(
                TelemetryIngestLog.device_id == device.id,
                TelemetryIngestLog.report_id == report_id,
            )
        ).first()
        if existing is not None:
            skipped += len(samples)
            accepted_report_ids.append(report_id)
            continue
        for s in samples:
            _insert_sample(device, s)
        db.add(TelemetryIngestLog(device_id=device.id, report_id=report_id))
        accepted_report_ids.append(report_id)

    db.commit()
    return TelemetryBatchOut(
        inserted=inserted,
        skipped=skipped,
        errors=errors[:50],
        accepted_report_ids=accepted_report_ids,
    )


@router.get("/colonies/{colony_id}/telemetry", response_model=list[TelemetryPointOut])
def get_colony_telemetry(
    colony_id: int,
    metric: str | None = None,
    limit: int = 500,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TelemetryPointOut]:
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
    return [_telemetry_point(r) for r in rows]
