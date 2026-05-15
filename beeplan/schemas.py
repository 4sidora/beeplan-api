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


class ColonyOut(BaseModel):
    id: int
    apiary_id: int
    name: str

    model_config = {"from_attributes": True}


class EdgeDeviceOut(BaseModel):
    id: int
    concentrator_id: int
    public_id: str
    label: str | None
    current_colony_id: int | None

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


class TelemetryPointOut(BaseModel):
    ts: datetime
    metric: str
    value: dict | list | str | float | int | bool | None

    model_config = {"from_attributes": True}


class SetColonyBody(BaseModel):
    colony_id: int | None = Field(description="Active colony for this device; null to detach")
