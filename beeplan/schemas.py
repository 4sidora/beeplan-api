from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


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


class ConcentratorNameOut(BaseModel):
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
    wifi_channel: int | None = None
    spool_pending_count: int = 0
    last_seen_at: datetime | None = None
    firmware_version: str | None = None
    edge_device_count: int = 0
    recent_telemetry: list[TelemetryPointOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ConcentratorCreate(BaseModel):
    apiary_id: int
    name: str | None = Field(default=None, max_length=255)


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
    name: str | None
    telemetry_slot_sec: int | None = None
    wake_interval_sec: int | None = None
    current_colony_id: int | None
    last_seen_at: datetime | None = None
    firmware_version: str | None = None
    recent_telemetry: list[TelemetryPointOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TelemetrySampleIn(BaseModel):
    device_public_id: str
    metric: str = Field(max_length=64)
    ts: datetime
    value: dict | list | str | float | int | bool | None
    report_id: str | None = Field(default=None, max_length=128)


class GatewayBatchStatusIn(BaseModel):
    signal_dbm: int | None = Field(default=None, ge=-120, le=0, description="WiFi RSSI шлюза, dBm")
    battery_volts: float | None = Field(
        default=None, ge=2.0, le=5.0, description="Напряжение батареи шлюза, V"
    )


class TelemetryBatchIn(BaseModel):
    samples: list[TelemetrySampleIn] = Field(default_factory=list)
    gateway: GatewayBatchStatusIn | None = None


class TelemetryBatchOut(BaseModel):
    inserted: int
    skipped: int
    errors: list[str] = []
    accepted_report_ids: list[str] = Field(default_factory=list)


class EdgeDeviceCreate(BaseModel):
    concentrator_id: int
    name: str | None = Field(default=None, max_length=255)
    colony_id: int | None = None


class EdgeDeviceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    wake_interval_sec: int | None = Field(default=None, ge=10, le=86400)


class BulkWakeIntervalBody(BaseModel):
    wake_interval_sec: int = Field(ge=10, le=86400)


class BulkWakeIntervalOut(BaseModel):
    updated: int


class EdgeHeartbeatConfigOut(BaseModel):
    public_id: str
    wake_interval_sec: int


class SetColonyBody(BaseModel):
    colony_id: int | None = Field(description="Active colony for this device; null to detach")


class ConcentratorHeartbeatIn(BaseModel):
    mac: str = Field(min_length=11, max_length=17)
    firmware_version: str | None = Field(default=None, max_length=32)
    wifi_channel: int | None = Field(default=None, ge=1, le=13)
    signal_dbm: int | None = Field(default=None, ge=-120, le=0, description="WiFi RSSI, dBm")
    spool_pending_count: int | None = Field(default=None, ge=0)


class ConcentratorHeartbeatOut(BaseModel):
    ok: bool = True
    gateway_mac: str
    edge_devices: list[EdgeHeartbeatConfigOut] = Field(default_factory=list)


class FirmwareBuildCreate(BaseModel):
    device_type: str = Field(pattern="^(gateway|edge)$")
    board: str = Field(
        default="ttgo-t-energy",
        pattern="^(ttgo-t-energy|ttgo-t-call-v14)$",
    )
    concentrator_id: int
    edge_device_id: int | None = None
    uplink_mode: str = Field(default="wifi", pattern="^(wifi|cellular)$")
    wifi_ssid: str | None = Field(default=None, max_length=64)
    wifi_password: str | None = Field(default=None, max_length=128)
    api_base_url: str | None = Field(default=None, max_length=256)
    gateway_wifi_channel: int = Field(default=6, ge=1, le=13)
    cellular_apn: str | None = Field(default=None, max_length=64)
    cellular_user: str | None = Field(default=None, max_length=64)
    cellular_pass: str | None = Field(default=None, max_length=64)
    wake_interval_sec: int = Field(default=3600, ge=10, le=86400)
    debug_serial: bool = Field(default=True, description="Подробный UART-лог в прошивке")
    edge_product_type: str = Field(default="multisensor", pattern="^(multisensor|scales)$")
    hx711_dout_pin: int = Field(default=1, ge=0, le=21)
    hx711_sck_pin: int = Field(default=3, ge=0, le=21)
    ds18b20_pin: int = Field(default=4, ge=0, le=21)
    weight_mode: str = Field(default="full", pattern="^(full|half)$")

    @model_validator(mode="after")
    def validate_gateway_uplink(self) -> "FirmwareBuildCreate":
        if self.device_type != "gateway":
            return self
        if self.uplink_mode == "wifi":
            if not self.wifi_ssid or not self.wifi_password:
                raise ValueError("wifi_ssid and wifi_password required for wifi uplink")
        elif not self.cellular_apn:
            raise ValueError("cellular_apn required for cellular uplink")
        return self


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
    phase: str | None = None
    log_tail: list[str] | None = None
    progress_pct: int | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class FirmwareReleaseOut(BaseModel):
    firmware_version: str
    gateway_version: str
    edge_version: str
    gateway_serial_tag: str
    edge_serial_tag: str
