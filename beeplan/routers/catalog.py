from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from beeplan.database import get_db
from beeplan.deps import get_current_user
from beeplan.models import Apiary, BeeBreed, Colony, Concentrator, User
from beeplan.schemas import (
    ApiaryCreate,
    ApiaryOut,
    ApiaryUpdate,
    BeeBreedOut,
    ColonyCreate,
    ColonyOut,
    ColonyUpdate,
    ConcentratorCreate,
    ConcentratorOut,
    ConcentratorUpdate,
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
    if conc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Concentrator not found")
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
    colony = Colony(apiary_id=body.apiary_id, name=body.name, bee_breed=body.bee_breed)
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
    colony.name = body.name
    colony.bee_breed = body.bee_breed
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


@router.get("/concentrators", response_model=list[ConcentratorOut])
def list_concentrators(
    apiary_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Concentrator]:
    _ensure_apiary_owned(db, user, apiary_id)
    return list(db.scalars(select(Concentrator).where(Concentrator.apiary_id == apiary_id)).all())


@router.post("/concentrators", response_model=ConcentratorOut, status_code=status.HTTP_201_CREATED)
def create_concentrator(
    body: ConcentratorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Concentrator:
    _ensure_apiary_owned(db, user, body.apiary_id)
    conc = Concentrator(
        apiary_id=body.apiary_id,
        name=body.name,
        ingest_token=str(uuid.uuid4()),
    )
    db.add(conc)
    db.commit()
    db.refresh(conc)
    return conc


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
    return conc


@router.delete("/concentrators/{concentrator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_concentrator(
    concentrator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    conc = _ensure_concentrator_owned(db, user, concentrator_id)
    db.delete(conc)
    db.commit()
