from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}


class ApiaryOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class ApiaryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiaryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class BeeBreedOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class ColonyOut(BaseModel):
    id: int
    apiary_id: int
    name: str
    bee_breed: str | None = None
    description: str | None = None
    colony_type: str | None = None
    hive_type: str | None = None
    body_count: int | None = None
    frames_per_body: int | None = None
    hive_volume_m3: float | None = None

    model_config = {"from_attributes": True}


class ColonyNameOut(BaseModel):
    name: str


class ColonyCreate(BaseModel):
    apiary_id: int
    name: str = Field(min_length=1, max_length=255)
    bee_breed: str | None = Field(default=None, max_length=255)
    description: str | None = None
    colony_type: str | None = Field(default=None, max_length=32)
    hive_type: str | None = Field(default=None, max_length=64)
    body_count: int | None = Field(default=None, ge=1)
    frames_per_body: int | None = Field(default=None, ge=1)
    hive_volume_m3: float | None = Field(default=None, gt=0)


class ColonyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    bee_breed: str | None = Field(default=None, max_length=255)
    description: str | None = None
    colony_type: str | None = Field(default=None, max_length=32)
    hive_type: str | None = Field(default=None, max_length=64)
    body_count: int | None = Field(default=None, ge=1)
    frames_per_body: int | None = Field(default=None, ge=1)
    hive_volume_m3: float | None = Field(default=None, gt=0)


class ConcentratorOut(BaseModel):
    id: int
    apiary_id: int
    apiary_name: str | None = None
    name: str
    ingest_token: str
    gateway_mac: str | None = None
    last_seen_at: datetime | None = None
    firmware_version: str | None = None
    edge_device_count: int = 0

    model_config = {"from_attributes": True}


class ConcentratorCreate(BaseModel):
    apiary_id: int
    name: str = Field(min_length=1, max_length=255)


class ConcentratorUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TelemetryPointOut(BaseModel):
    ts: datetime
    metric: str
    value: dict | list | str | float | int | bool | None

    model_config = {"from_attributes": True}


class EdgeDeviceOut(BaseModel):
    id: int
    concentrator_id: int
    concentrator_name: str | None = None
    public_id: str
    label: str | None
    current_colony_id: int | None
    last_seen_at: datetime | None = None
    recent_unbound_telemetry: list[TelemetryPointOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TelemetrySampleIn(BaseModel):
    device_public_id: str
    metric: str = Field(max_length=64)
    ts: datetime
    value: dict | list | str | float | int | bool | None


class TelemetryBatchIn(BaseModel):
    samples: list[TelemetrySampleIn]


class TelemetryBatchOut(BaseModel):
    inserted: int
    skipped: int
    errors: list[str] = []


class EdgeDeviceCreate(BaseModel):
    concentrator_id: int
    public_id: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=255)
    colony_id: int | None = None


class EdgeDeviceUpdate(BaseModel):
    public_id: str | None = Field(default=None, min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=255)


class SetColonyBody(BaseModel):
    colony_id: int | None = Field(description="Active colony for this device; null to detach")


class ConcentratorHeartbeatIn(BaseModel):
    mac: str = Field(min_length=11, max_length=17)
    firmware_version: str | None = Field(default=None, max_length=32)


class ConcentratorHeartbeatOut(BaseModel):
    ok: bool = True
    gateway_mac: str


class FirmwareBuildCreate(BaseModel):
    device_type: str = Field(pattern="^(gateway|edge)$")
    board: str = Field(default="esp32dev", pattern="^(esp32dev|esp32c3|esp32c3-usb)$")
    concentrator_id: int
    edge_device_id: int | None = None
    wifi_ssid: str | None = Field(default=None, max_length=64)
    wifi_password: str | None = Field(default=None, max_length=128)
    api_base_url: str | None = Field(default=None, max_length=256)
    wake_interval_sec: int = Field(default=600, ge=10, le=86400)


class FirmwareBuildOut(BaseModel):
    id: str
    device_type: str
    board: str
    concentrator_id: int
    edge_device_id: int | None
    status: str
    error: str | None = None
    manifest_url: str | None = None
    firmware_version: str | None = None
    serial_tag: str | None = None
    expires_at: datetime
    created_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class FirmwareReleaseOut(BaseModel):
    firmware_version: str
    gateway_version: str
    edge_version: str
    gateway_serial_tag: str
    edge_serial_tag: str
