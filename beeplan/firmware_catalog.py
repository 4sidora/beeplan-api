"""Версии прошивок BeePlan — синхронизировать с beeplan-builder/builder/firmware_versions.py."""

from __future__ import annotations

PROJECT_SLUG = "beeplan"

GATEWAY_TYPE = "Gateway"
EDGE_TYPE = "Edge"

GATEWAY_VERSION = "0.2.30"
EDGE_VERSION = "0.3.0"


def profile_type(profile: str) -> str:
    if profile == "gateway":
        return GATEWAY_TYPE
    if profile == "edge":
        return EDGE_TYPE
    raise ValueError(f"Unknown profile: {profile}")


def version_for(profile: str) -> str:
    if profile == "gateway":
        return GATEWAY_VERSION
    if profile == "edge":
        return EDGE_VERSION
    raise ValueError(f"Unknown profile: {profile}")


def manifest_name(profile: str) -> str:
    return f"{PROJECT_SLUG}-{profile_type(profile)}"


def serial_tag(profile: str) -> str:
    return f"{manifest_name(profile)}-{version_for(profile)}"


FIRMWARE_VERSION = GATEWAY_VERSION
GATEWAY_SERIAL_TAG = serial_tag("gateway")
EDGE_SERIAL_TAG = serial_tag("edge")
