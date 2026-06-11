from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from beeplan.database import get_db
from beeplan.deps import get_current_user
from beeplan.models import Apiary, BeeBreed, Colony, Concentrator, EdgeDevice, User
from beeplan.colony_catalog import apply_colony_payload, validate_colony_fields
from beeplan.base_station_names import generate_base_station_name
from beeplan.colony_names import generate_colony_name
from beeplan.schemas import (
    ApiaryCreate,
    ApiaryOut,
    ApiaryUpdate,
    BeeBreedOut,
    ColonyCreate,
    ColonyNameOut,
    ColonyOut,
    ColonyUpdate,
    ConcentratorCreate,
    ConcentratorNameOut,
    ConcentratorOut,
    ConcentratorUpdate,
    BulkWakeIntervalBody,
    BulkWakeIntervalOut,
)
from beeplan.soft_delete import (
    concentrator_active,
    edge_active,
    require_active_concentrator,
    soft_delete_concentrator,
)

router = APIRouter(prefix="/v1", tags=["catalog"])


def _ensure_apiary_owned(db: Session, user: User, apiary_id: int) -> Apiary:
    apiary = db.get(Apiary, apiary_id)
    if apiary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Apiary not found")
    if apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return apiary


def _ensure_colony_owned(db: Session, user: User, colony_id: int) -> Colony:
    colony = db.get(Colony, colony_id)
    if colony is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colony not found")
    _ensure_apiary_owned(db, user, colony.apiary_id)
    return colony


def _ensure_concentrator_owned(db: Session, user: User, concentrator_id: int) -> Concentrator:
    conc = db.get(Concentrator, concentrator_id)
    require_active_concentrator(conc)
    _ensure_apiary_owned(db, user, conc.apiary_id)
    return conc


def _validate_bee_breed(db: Session, bee_breed: str | None) -> None:
    if bee_breed is None:
        return
    exists = db.scalars(select(BeeBreed).where(BeeBreed.name == bee_breed)).first()
    if exists is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown bee breed")


@router.get("/bee-breeds", response_model=list[BeeBreedOut])
def list_bee_breeds(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BeeBreed]:
    return list(db.scalars(select(BeeBreed).order_by(BeeBreed.name)).all())


@router.get("/apiaries", response_model=list[ApiaryOut])
def list_apiaries(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Apiary]:
    return list(db.scalars(select(Apiary).where(Apiary.user_id == user.id)).all())


@router.post("/apiaries", response_model=ApiaryOut, status_code=status.HTTP_201_CREATED)
def create_apiary(
    body: ApiaryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Apiary:
    apiary = Apiary(user_id=user.id, name=body.name)
    db.add(apiary)
    db.commit()
    db.refresh(apiary)
    return apiary


@router.patch("/apiaries/{apiary_id}", response_model=ApiaryOut)
def update_apiary(
    apiary_id: int,
    body: ApiaryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Apiary:
    apiary = _ensure_apiary_owned(db, user, apiary_id)
    apiary.name = body.name
    db.add(apiary)
    db.commit()
    db.refresh(apiary)
    return apiary


@router.delete("/apiaries/{apiary_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_apiary(
    apiary_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    apiary = _ensure_apiary_owned(db, user, apiary_id)
    db.delete(apiary)
    db.commit()


@router.get("/colonies/suggested-name", response_model=ColonyNameOut)
def suggested_colony_name(
    user: User = Depends(get_current_user),
) -> ColonyNameOut:
    del user
    return ColonyNameOut(name=generate_colony_name())


@router.get("/colonies", response_model=list[ColonyOut])
def list_colonies(
    apiary_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Colony]:
    _ensure_apiary_owned(db, user, apiary_id)
    return list(db.scalars(select(Colony).where(Colony.apiary_id == apiary_id)).all())


@router.get("/colonies/{colony_id}", response_model=ColonyOut)
def get_colony(
    colony_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Colony:
    return _ensure_colony_owned(db, user, colony_id)


@router.post("/colonies", response_model=ColonyOut, status_code=status.HTTP_201_CREATED)
def create_colony(
    body: ColonyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Colony:
    _ensure_apiary_owned(db, user, body.apiary_id)
    _validate_bee_breed(db, body.bee_breed)
    validate_colony_fields(
        colony_type=body.colony_type,
        hive_type=body.hive_type,
        body_count=body.body_count,
        frames_per_body=body.frames_per_body,
        hive_volume_m3=body.hive_volume_m3,
    )
    colony = Colony(apiary_id=body.apiary_id, name=body.name, bee_breed=body.bee_breed)
    apply_colony_payload(
        colony,
        body.model_dump(exclude={"apiary_id"}),
    )
    db.add(colony)
    db.commit()
    db.refresh(colony)
    return colony


@router.patch("/colonies/{colony_id}", response_model=ColonyOut)
def update_colony(
    colony_id: int,
    body: ColonyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Colony:
    colony = _ensure_colony_owned(db, user, colony_id)
    _validate_bee_breed(db, body.bee_breed)
    validate_colony_fields(
        colony_type=body.colony_type,
        hive_type=body.hive_type,
        body_count=body.body_count,
        frames_per_body=body.frames_per_body,
        hive_volume_m3=body.hive_volume_m3,
    )
    apply_colony_payload(colony, body.model_dump())
    db.add(colony)
    db.commit()
    db.refresh(colony)
    return colony


@router.delete("/colonies/{colony_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_colony(
    colony_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    colony = _ensure_colony_owned(db, user, colony_id)
    db.delete(colony)
    db.commit()


def _to_concentrator_out(conc: Concentrator, db: Session) -> ConcentratorOut:
    from beeplan.routers.devices import _recent_concentrator_telemetry

    apiary = db.get(Apiary, conc.apiary_id)
    device_count = db.scalar(
        select(func.count())
        .select_from(EdgeDevice)
        .where(EdgeDevice.concentrator_id == conc.id, edge_active())
    )
    return ConcentratorOut(
        id=conc.id,
        apiary_id=conc.apiary_id,
        apiary_name=apiary.name if apiary else None,
        name=conc.name,
        ingest_token=conc.ingest_token,
        gateway_mac=conc.gateway_mac,
        wifi_channel=conc.wifi_channel,
        spool_pending_count=conc.spool_pending_count or 0,
        last_seen_at=conc.last_seen_at,
        firmware_version=conc.firmware_version,
        edge_device_count=int(device_count or 0),
        recent_telemetry=_recent_concentrator_telemetry(db, conc.id),
    )


@router.get("/concentrators/suggested-name", response_model=ConcentratorNameOut)
def suggested_concentrator_name(
    user: User = Depends(get_current_user),
) -> ConcentratorNameOut:
    del user
    return ConcentratorNameOut(name=generate_base_station_name())


@router.get("/concentrators", response_model=list[ConcentratorOut])
def list_concentrators(
    apiary_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConcentratorOut]:
    if apiary_id is not None:
        _ensure_apiary_owned(db, user, apiary_id)
        rows = list(
            db.scalars(
                select(Concentrator).where(
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
        rows = list(
            db.scalars(
                select(Concentrator).where(
                    Concentrator.apiary_id.in_(apiary_ids),
                    concentrator_active(),
                )
            ).all()
        )
    return [_to_concentrator_out(c, db) for c in rows]


@router.post("/concentrators", response_model=ConcentratorOut, status_code=status.HTTP_201_CREATED)
def create_concentrator(
    body: ConcentratorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Concentrator:
    _ensure_apiary_owned(db, user, body.apiary_id)
    raw_name = (body.name or "").strip()
    conc = Concentrator(
        apiary_id=body.apiary_id,
        name=raw_name or generate_base_station_name(),
        ingest_token=str(uuid.uuid4()),
    )
    db.add(conc)
    db.commit()
    db.refresh(conc)
    return _to_concentrator_out(conc, db)


@router.get("/concentrators/{concentrator_id}", response_model=ConcentratorOut)
def get_concentrator(
    concentrator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConcentratorOut:
    conc = _ensure_concentrator_owned(db, user, concentrator_id)
    return _to_concentrator_out(conc, db)


@router.patch("/concentrators/{concentrator_id}", response_model=ConcentratorOut)
def update_concentrator(
    concentrator_id: int,
    body: ConcentratorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Concentrator:
    conc = _ensure_concentrator_owned(db, user, concentrator_id)
    conc.name = body.name
    db.add(conc)
    db.commit()
    db.refresh(conc)
    return _to_concentrator_out(conc, db)


@router.patch(
    "/concentrators/{concentrator_id}/edge-devices/wake-interval",
    response_model=BulkWakeIntervalOut,
)
def bulk_set_edge_wake_interval(
    concentrator_id: int,
    body: BulkWakeIntervalBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BulkWakeIntervalOut:
    conc = _ensure_concentrator_owned(db, user, concentrator_id)
    devices = list(
        db.scalars(
            select(EdgeDevice).where(
                EdgeDevice.concentrator_id == conc.id,
                edge_active(),
            )
        ).all()
    )
    for device in devices:
        device.wake_interval_sec = body.wake_interval_sec
        db.add(device)
    db.commit()
    return BulkWakeIntervalOut(updated=len(devices))


@router.delete("/concentrators/{concentrator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_concentrator(
    concentrator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    conc = _ensure_concentrator_owned(db, user, concentrator_id)
    soft_delete_concentrator(db, conc)
    db.commit()
