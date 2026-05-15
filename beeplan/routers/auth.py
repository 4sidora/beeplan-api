from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from beeplan.database import get_db
from beeplan.models import User
from beeplan.schemas import TokenOut, UserLogin, UserOut, UserRegister
from beeplan.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(body: UserRegister, db: Session = Depends(get_db)) -> User:
    exists = db.scalars(select(User).where(User.email == body.email)).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/token", response_model=TokenOut)
def login(body: UserLogin, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if user is None or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token(str(user.id))
    return TokenOut(access_token=token)
