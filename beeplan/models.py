from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oauth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    apiaries: Mapped[list[Apiary]] = relationship(back_populates="owner")


class Apiary(Base):
    __tablename__ = "apiaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    owner: Mapped[User] = relationship(back_populates="apiaries")
    concentrators: Mapped[list[Concentrator]] = relationship(
        back_populates="apiary", passive_deletes=True
    )
    colonies: Mapped[list[Colony]] = relationship(back_populates="apiary", passive_deletes=True)


class Concentrator(Base):
    __tablename__ = "concentrators"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    apiary_id: Mapped[int] = mapped_column(ForeignKey("apiaries.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ingest_token: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    gateway_mac: Mapped[str | None] = mapped_column(String(17), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    apiary: Mapped[Apiary] = relationship(back_populates="concentrators")
    edge_devices: Mapped[list[EdgeDevice]] = relationship(
        back_populates="concentrator", passive_deletes=True
    )


class Colony(Base):
    __tablename__ = "colonies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    apiary_id: Mapped[int] = mapped_column(ForeignKey("apiaries.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bee_breed: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    colony_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hive_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frames_per_body: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hive_volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    apiary: Mapped[Apiary] = relationship(back_populates="colonies")
    assignments: Mapped[list[EdgeDeviceColonyAssignment]] = relationship(
        back_populates="colony",
        foreign_keys="EdgeDeviceColonyAssignment.colony_id",
    )


class BeeBreed(Base):
    __tablename__ = "bee_breeds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class EdgeDevice(Base):
    __tablename__ = "edge_devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    concentrator_id: Mapped[int] = mapped_column(ForeignKey("concentrators.id", ondelete="CASCADE"))
    public_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hardware_mac: Mapped[str | None] = mapped_column(String(17), nullable=True)
    current_colony_id: Mapped[int | None] = mapped_column(ForeignKey("colonies.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    concentrator: Mapped[Concentrator] = relationship(back_populates="edge_devices")
    current_colony: Mapped[Colony | None] = relationship(foreign_keys="EdgeDevice.current_colony_id")
    assignments: Mapped[list[EdgeDeviceColonyAssignment]] = relationship(
        back_populates="device", foreign_keys="EdgeDeviceColonyAssignment.device_id"
    )


class EdgeDeviceColonyAssignment(Base):
    __tablename__ = "edge_device_colony_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("edge_devices.id", ondelete="CASCADE"))
    colony_id: Mapped[int] = mapped_column(ForeignKey("colonies.id", ondelete="CASCADE"))
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    detached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped[EdgeDevice] = relationship(
        back_populates="assignments", foreign_keys=[device_id]
    )
    colony: Mapped[Colony] = relationship(back_populates="assignments")


class TelemetrySample(Base):
    __tablename__ = "telemetry_samples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    colony_id: Mapped[int] = mapped_column(ForeignKey("colonies.id", ondelete="CASCADE"))
    source_device_id: Mapped[int | None] = mapped_column(ForeignKey("edge_devices.id", ondelete="SET NULL"), nullable=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[dict | list | str | float | int | bool | None] = mapped_column(JSON, nullable=False)


class FirmwareBuild(Base):
    __tablename__ = "firmware_builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_type: Mapped[str] = mapped_column(String(16), nullable=False)
    board: Mapped[str] = mapped_column(String(32), nullable=False)
    concentrator_id: Mapped[int] = mapped_column(ForeignKey("concentrators.id", ondelete="CASCADE"))
    edge_device_id: Mapped[int | None] = mapped_column(ForeignKey("edge_devices.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
