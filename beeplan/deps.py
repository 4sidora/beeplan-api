from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from beeplan.database import get_db
from beeplan.models import Concentrator, User
from beeplan.security import safe_decode_token

security = HTTPBearer(auto_error=False)


def get_concentrator_from_ingest_token(
    db: Session,
    token: str | None,
) -> Concentrator | None:
    if not token:
        return None
    row = db.query(Concentrator).filter(Concentrator.ingest_token == token).one_or_none()
    if row is None:
        return None
    if not secrets.compare_digest(row.ingest_token, token):
        return None
    return row


def require_concentrator(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Concentrator:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    conc = get_concentrator_from_ingest_token(db, token)
    if conc is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid concentrator token")
    return conc


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = safe_decode_token(creds.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def get_current_user_optional(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None or creds.scheme.lower() != "bearer":
        return None
    payload = safe_decode_token(creds.credentials)
    if payload is None or "sub" not in payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    return db.get(User, user_id)
