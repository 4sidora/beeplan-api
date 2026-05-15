from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from beeplan.database import get_db
from beeplan.deps import get_current_user
from beeplan.models import Apiary, Colony, User
from beeplan.schemas import ApiaryOut, ColonyOut

router = APIRouter(prefix="/v1", tags=["catalog"])


@router.get("/apiaries", response_model=list[ApiaryOut])
def list_apiaries(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Apiary]:
    return list(db.scalars(select(Apiary).where(Apiary.user_id == user.id)).all())


@router.get("/colonies", response_model=list[ColonyOut])
def list_colonies(
    apiary_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Colony]:
    apiary = db.get(Apiary, apiary_id)
    if apiary is None or apiary.user_id != user.id:
        return []
    return list(db.scalars(select(Colony).where(Colony.apiary_id == apiary_id)).all())
