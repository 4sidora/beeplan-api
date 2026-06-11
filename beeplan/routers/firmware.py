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
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from beeplan.builder_client import BuilderClient
from beeplan.config import get_settings
from beeplan.database import SessionLocal, get_db
from beeplan.deps import get_current_user, get_current_user_optional
from beeplan.firmware_catalog import (
    EDGE_SERIAL_TAG,
    EDGE_VERSION,
    FIRMWARE_VERSION,
    GATEWAY_SERIAL_TAG,
    GATEWAY_VERSION,
    serial_tag,
    version_for,
)
from beeplan.models import Apiary, Concentrator, EdgeDevice, FirmwareBuild, User
from beeplan.soft_delete import require_active_concentrator, require_active_edge
from beeplan.schemas import FirmwareBuildCreate, FirmwareBuildOut, FirmwareReleaseOut

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
    require_active_concentrator(conc)
    apiary = db.get(Apiary, conc.apiary_id)
    if apiary is None or apiary.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return conc


def _ensure_edge_owned(db: Session, user: User, edge_device_id: int) -> EdgeDevice:
    device = db.get(EdgeDevice, edge_device_id)
    require_active_edge(device)
    _ensure_concentrator_owned(db, user, device.concentrator_id)
    return device


def _check_rate_limit(db: Session, user_id: int) -> None:
    settings = get_settings()
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    limit = settings.firmware_builds_per_hour
    # Failed builds (builder down, compile error) should not block retries.
    count = db.scalar(
        select(func.count())
        .select_from(FirmwareBuild)
        .where(
            FirmwareBuild.user_id == user_id,
            FirmwareBuild.created_at >= since,
            FirmwareBuild.status != "failed",
        )
    )
    if count is not None and count >= limit:
        oldest = db.scalar(
            select(func.min(FirmwareBuild.created_at)).where(
                FirmwareBuild.user_id == user_id,
                FirmwareBuild.created_at >= since,
                FirmwareBuild.status != "failed",
            )
        )
        retry_min = 60
        if oldest is not None:
            retry_at = oldest + timedelta(hours=1)
            delta = retry_at - datetime.now(timezone.utc)
            retry_min = max(1, int(delta.total_seconds() // 60) + 1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Лимит сборок прошивки: {count}/{limit} за час. "
            f"Повторите через ~{retry_min} мин или увеличьте FIRMWARE_BUILDS_PER_HOUR в .env API.",
        )


def _friendly_builder_error(exc: Exception) -> str:
    msg = str(exc)
    if "No address associated with hostname" in msg or "Errno -5" in msg or "getaddrinfo failed" in msg:
        settings = get_settings()
        return (
            f"Не удалось подключиться к серверу сборки ({settings.builder_url}). "
            "Если API запущен на ПК (не в Docker), укажите в .env: "
            "BUILDER_URL=http://localhost:9000. Если API в Docker — BUILDER_URL=http://builder:9000 "
            "и контейнер beeplan-builder должен быть запущен."
        )
    return msg


def _manifest_base_url(request: Request) -> str:
    """URL для manifest.json — должен открываться из браузера на ПК пользователя."""
    settings = get_settings()
    configured = settings.public_api_base_url.strip().rstrip("/")
    if configured:
        try:
            host = (urlparse(configured).hostname or "").lower()
        except ValueError:
            host = ""
        if host not in ("localhost", "127.0.0.1", "host.docker.internal", ""):
            return configured
    return str(request.base_url).rstrip("/")


def _resolve_firmware_releases() -> FirmwareReleaseOut:
    try:
        data = BuilderClient().get_releases()
        return FirmwareReleaseOut(
            firmware_version=data.get("firmware_version", FIRMWARE_VERSION),
            gateway_version=data.get("gateway_version", GATEWAY_VERSION),
            edge_version=data.get("edge_version", EDGE_VERSION),
            gateway_serial_tag=data.get("gateway_serial_tag", GATEWAY_SERIAL_TAG),
            edge_serial_tag=data.get("edge_serial_tag", EDGE_SERIAL_TAG),
        )
    except Exception:  # noqa: BLE001
        return FirmwareReleaseOut(
            firmware_version=FIRMWARE_VERSION,
            gateway_version=GATEWAY_VERSION,
            edge_version=EDGE_VERSION,
            gateway_serial_tag=GATEWAY_SERIAL_TAG,
            edge_serial_tag=EDGE_SERIAL_TAG,
        )


def _parse_builder_progress(remote: dict) -> dict:
    updated_raw = remote.get("updated_at")
    updated_at = None
    if updated_raw:
        try:
            updated_at = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
        except ValueError:
            updated_at = None
    return {
        "phase": remote.get("phase"),
        "log_tail": remote.get("log_tail"),
        "progress_pct": remote.get("progress_pct"),
        "updated_at": updated_at,
    }


def _builder_progress_for(row: FirmwareBuild) -> dict:
    if row.status not in ("queued", "building"):
        return {}
    try:
        remote = BuilderClient().get_build(row.id)
    except Exception:  # noqa: BLE001
        return {}
    return _parse_builder_progress(remote)


def _to_out(row: FirmwareBuild, request: Request, *, progress: dict | None = None) -> FirmwareBuildOut:
    manifest_url = None
    if row.status == "ready":
        base = _manifest_base_url(request)
        token = _download_token(row.id)
        manifest_url = f"{base}/v1/firmware/builds/{row.id}/manifest.json?token={token}"
    extra = progress if progress is not None else _builder_progress_for(row)
    return FirmwareBuildOut(
        id=row.id,
        device_type=row.device_type,
        board=row.board,
        concentrator_id=row.concentrator_id,
        edge_device_id=row.edge_device_id,
        status=row.status,
        error=row.error,
        manifest_url=manifest_url,
        firmware_version=version_for(row.device_type),
        serial_tag=serial_tag(row.device_type),
        expires_at=row.expires_at,
        created_at=row.created_at,
        finished_at=row.finished_at,
        phase=extra.get("phase"),
        log_tail=extra.get("log_tail"),
        progress_pct=extra.get("progress_pct"),
        updated_at=extra.get("updated_at"),
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
            if remote_status == "building" and row.status == "queued":
                row.status = "building"
                db.commit()
            if remote_status == "ready":
                row.status = "ready"
                row.finished_at = datetime.now(timezone.utc)
                row.error = None
                if row.edge_device_id is not None and row.device_type == "edge":
                    device = db.get(EdgeDevice, row.edge_device_id)
                    if device is not None:
                        device.firmware_version = version_for("edge")
                        db.add(device)
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
            row.error = _friendly_builder_error(exc)
            row.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


@router.get("/releases", response_model=FirmwareReleaseOut)
def get_firmware_releases(
    _user: User = Depends(get_current_user),
) -> FirmwareReleaseOut:
    """Актуальная версия прошивки на сервере сборки (для мастера прошивки)."""
    return _resolve_firmware_releases()


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
            "firmware_version": version_for(body.device_type),
            "firmware_serial_tag": serial_tag(body.device_type),
            "debug_serial": body.debug_serial,
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
        if conc.wifi_channel is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Concentrator has no wifi_channel — connect gateway to Wi-Fi first",
            )
        if device.telemetry_slot_sec is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Edge device has no telemetry_slot_sec assigned",
            )
        device.wake_interval_sec = body.wake_interval_sec
        db.add(device)
        edge_device_id = device.id
        payload["edge_config"] = {
            "gateway_mac": conc.gateway_mac,
            "device_public_id": device.public_id,
            "wake_interval_sec": body.wake_interval_sec,
            "telemetry_slot_sec": device.telemetry_slot_sec,
            "gateway_wifi_channel": conc.wifi_channel,
            "device_type": "multisensor",
            "firmware_version": version_for("edge"),
            "firmware_serial_tag": serial_tag("edge"),
            "debug_serial": body.debug_serial,
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
        row.error = _friendly_builder_error(exc)
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
