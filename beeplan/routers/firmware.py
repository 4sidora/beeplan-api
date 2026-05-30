"""Firmware build orchestration and artifact proxy."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from beeplan.builder_client import BuilderClient
from beeplan.config import get_settings
from beeplan.database import SessionLocal, get_db
from beeplan.deps import get_current_user, get_current_user_optional
from beeplan.models import Apiary, Concentrator, EdgeDevice, FirmwareBuild, User
from beeplan.schemas import FirmwareBuildCreate, FirmwareBuildOut

router = APIRouter(prefix="/v1/firmware", tags=["firmware"])


def _download_token(build_id: str) -> str:
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, build_id.encode(), hashlib.sha256).hexdigest()[:32]


def _verify_download_access(build_id: str, token: str | None, user: User | None) -> None:
    if user is not None:
        return
    if token and secrets.compare_digest(token, _download_token(build_id)):
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


def _ensure_concentrator_owned(db: Session, user: User, concentrator_id: int) -> Concentrator:
    conc = db.get(Concentrator, concentrator_id)
    if conc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Concentrator not found")
    apiary = db.get(Apiary, conc.apiary_id)
    if apiary is None or apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return conc


def _ensure_edge_owned(db: Session, user: User, edge_device_id: int) -> EdgeDevice:
    device = db.get(EdgeDevice, edge_device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edge device not found")
    _ensure_concentrator_owned(db, user, device.concentrator_id)
    return device


def _check_rate_limit(db: Session, user_id: int) -> None:
    settings = get_settings()
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    count = db.scalar(
        select(func.count())
        .select_from(FirmwareBuild)
        .where(FirmwareBuild.user_id == user_id, FirmwareBuild.created_at >= since)
    )
    if count is not None and count >= settings.firmware_builds_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Firmware build rate limit exceeded")


def _to_out(row: FirmwareBuild, request: Request) -> FirmwareBuildOut:
    manifest_url = None
    if row.status == "ready":
        base = str(request.base_url).rstrip("/")
        token = _download_token(row.id)
        manifest_url = f"{base}/v1/firmware/builds/{row.id}/manifest.json?token={token}"
    return FirmwareBuildOut(
        id=row.id,
        device_type=row.device_type,
        board=row.board,
        concentrator_id=row.concentrator_id,
        edge_device_id=row.edge_device_id,
        status=row.status,
        error=row.error,
        manifest_url=manifest_url,
        expires_at=row.expires_at,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


def _poll_builder(build_id: str) -> None:
    client = BuilderClient()
    db = SessionLocal()
    try:
        for _ in range(600):
            remote = client.get_build(build_id)
            remote_status = remote.get("status")
            row = db.get(FirmwareBuild, build_id)
            if row is None:
                return
            if remote_status == "ready":
                row.status = "ready"
                row.finished_at = datetime.now(timezone.utc)
                row.error = None
                db.commit()
                return
            if remote_status == "failed":
                row.status = "failed"
                row.error = remote.get("error") or "Build failed"
                row.finished_at = datetime.now(timezone.utc)
                db.commit()
                return
            time.sleep(2)
        row = db.get(FirmwareBuild, build_id)
        if row is not None:
            row.status = "failed"
            row.error = "Build timed out"
            row.finished_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        row = db.get(FirmwareBuild, build_id)
        if row is not None:
            row.status = "failed"
            row.error = str(exc)
            row.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


@router.post("/builds", response_model=FirmwareBuildOut, status_code=status.HTTP_202_ACCEPTED)
def create_firmware_build(
    body: FirmwareBuildCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FirmwareBuildOut:
    _check_rate_limit(db, user.id)
    conc = _ensure_concentrator_owned(db, user, body.concentrator_id)
    settings = get_settings()

    build_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.firmware_build_ttl_minutes)

    payload: dict = {
        "build_id": build_id,
        "profile": body.device_type,
        "board": body.board,
    }

    if body.device_type == "gateway":
        if not body.wifi_ssid or not body.wifi_password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "wifi_ssid and wifi_password required")
        api_url = (body.api_base_url or settings.public_api_base_url).rstrip("/")
        payload["gateway_config"] = {
            "wifi_ssid": body.wifi_ssid,
            "wifi_password": body.wifi_password,
            "api_base_url": api_url,
            "ingest_token": conc.ingest_token,
            "firmware_version": "0.1.0",
        }
        edge_device_id = None
    else:
        if body.edge_device_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "edge_device_id required for edge builds")
        device = _ensure_edge_owned(db, user, body.edge_device_id)
        if device.concentrator_id != conc.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "edge device belongs to another concentrator")
        if not conc.gateway_mac:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Concentrator has no gateway_mac — flash gateway first",
            )
        edge_device_id = device.id
        payload["edge_config"] = {
            "gateway_mac": conc.gateway_mac,
            "device_public_id": device.public_id,
            "wake_interval_sec": body.wake_interval_sec,
        }

    row = FirmwareBuild(
        id=build_id,
        user_id=user.id,
        device_type=body.device_type,
        board=body.board,
        concentrator_id=conc.id,
        edge_device_id=edge_device_id,
        status="queued",
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    try:
        client = BuilderClient()
        client.start_build(payload)
        row.status = "building"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        row.status = "failed"
        row.error = str(exc)
        row.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return _to_out(row, request)

    thread = threading.Thread(target=_poll_builder, args=(build_id,), daemon=True)
    thread.start()
    db.refresh(row)
    return _to_out(row, request)


@router.get("/builds/{build_id}", response_model=FirmwareBuildOut)
def get_firmware_build(
    build_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FirmwareBuildOut:
    row = db.get(FirmwareBuild, build_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build not found")
    if row.expires_at < datetime.now(timezone.utc) and row.status != "ready":
        raise HTTPException(status.HTTP_410_GONE, "Build expired")
    return _to_out(row, request)


def _get_ready_build(db: Session, user: User, build_id: str) -> FirmwareBuild:
    row = db.get(FirmwareBuild, build_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build not found")
    if row.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Build status is {row.status}")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "Build expired")
    return row


def _get_ready_build_public(db: Session, user: User | None, build_id: str) -> FirmwareBuild:
    row = db.get(FirmwareBuild, build_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Build not found")
    if user is not None and row.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    if row.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Build status is {row.status}")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "Build expired")
    return row


@router.get("/builds/{build_id}/manifest.json")
def get_firmware_manifest(
    build_id: str,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> Response:
    _verify_download_access(build_id, token, user)
    _get_ready_build_public(db, user, build_id)
    client = BuilderClient()
    raw = client.fetch_manifest(build_id)
    manifest = json.loads(raw)
    dl_token = token or _download_token(build_id)
    for build in manifest.get("builds", []):
        for part in build.get("parts", []):
            path = part.get("path", "")
            if path and "?" not in path:
                part["path"] = f"{path}?token={dl_token}"
    return Response(content=json.dumps(manifest), media_type="application/json")


ALLOWED_FLASH_ARTIFACTS = frozenset(
    {"bootloader.bin", "partitions.bin", "boot_app0.bin", "firmware.bin"}
)


@router.get("/builds/{build_id}/{artifact_name}")
def get_firmware_artifact(
    build_id: str,
    artifact_name: str,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> Response:
    if artifact_name not in ALLOWED_FLASH_ARTIFACTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    _verify_download_access(build_id, token, user)
    _get_ready_build_public(db, user, build_id)
    client = BuilderClient()
    content = client.fetch_artifact(build_id, artifact_name)
    return Response(content=content, media_type="application/octet-stream")
