"""Справочники типов семьи и улья — единый источник правил валидации."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COLONY_TYPES = frozenset({"split", "nucleus", "colony", "swarm"})

COLONY_TYPE_LABELS = {
    "split": "Отводок",
    "nucleus": "Нуклеус",
    "colony": "Семья",
    "swarm": "Рой",
}


@dataclass(frozen=True)
class HiveTypeSpec:
    code: str
    label: str
    frame_options: tuple[int, ...]  # empty = volume-only (koloda)
    fixed_frames: int | None
    allows_body_count: bool
    uses_volume: bool


HIVE_TYPES: dict[str, HiveTypeSpec] = {
    "dadant_laying": HiveTypeSpec(
        "dadant_laying",
        "Лежак Дадан",
        (16, 20, 24),
        None,
        True,
        False,
    ),
    "dadant": HiveTypeSpec(
        "dadant",
        "Дадан",
        (6, 8, 10, 12),
        None,
        True,
        False,
    ),
    "ruta": HiveTypeSpec("ruta", "Рута", (), 10, False, False),
    "magazin": HiveTypeSpec(
        "magazin",
        "Магазинка",
        (6, 8, 10, 12),
        None,
        True,
        False,
    ),
    "udav": HiveTypeSpec("udav", "Удав", (), 9, False, False),
    "mfu": HiveTypeSpec("mfu", "МФУ", (), 8, False, False),
    "koloda": HiveTypeSpec("koloda", "Колода", (), None, False, True),
}


def normalize_hive_fields(
    hive_type: str | None,
    body_count: int | None,
    frames_per_body: int | None,
    hive_volume_m3: float | None,
) -> tuple[int | None, int | None, float | None]:
    """Применить фиксированные рамки и сбросить лишние поля по типу улья."""
    if hive_type is None:
        return body_count, frames_per_body, hive_volume_m3
    spec = HIVE_TYPES.get(hive_type)
    if spec is None:
        return body_count, frames_per_body, hive_volume_m3
    if spec.uses_volume:
        return None, None, hive_volume_m3
    if spec.fixed_frames is not None:
        return 1, spec.fixed_frames, None
    return body_count, frames_per_body, None


def validate_colony_fields(
    *,
    colony_type: str | None,
    hive_type: str | None,
    body_count: int | None,
    frames_per_body: int | None,
    hive_volume_m3: float | None,
) -> None:
    from fastapi import HTTPException, status

    if colony_type is not None and colony_type not in COLONY_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown colony type")

    if hive_type is None:
        return

    spec = HIVE_TYPES.get(hive_type)
    if spec is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown hive type")

    if spec.uses_volume:
        if hive_volume_m3 is None or hive_volume_m3 <= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "hive_volume_m3 is required for koloda",
            )
        if body_count is not None or frames_per_body is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "body_count and frames_per_body must be null for koloda",
            )
        return

    if body_count is not None and body_count < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body_count must be >= 1")

    if spec.fixed_frames is not None:
        if frames_per_body is not None and frames_per_body != spec.fixed_frames:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"frames_per_body must be {spec.fixed_frames} for {spec.label}",
            )
        return

    if spec.frame_options:
        if frames_per_body is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "frames_per_body is required for this hive type",
            )
        if frames_per_body not in spec.frame_options:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"frames_per_body must be one of {list(spec.frame_options)}",
            )
    if spec.allows_body_count and body_count is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "body_count is required for this hive type",
        )


def apply_colony_payload(colony: Any, data: dict[str, Any]) -> None:
    """Записать поля семьи с нормализацией улья."""
    for key in (
        "name",
        "description",
        "bee_breed",
        "colony_type",
        "hive_type",
    ):
        if key in data:
            setattr(colony, key, data[key])

    hive_type = data.get("hive_type", colony.hive_type)
    body_count = data.get("body_count", colony.body_count)
    frames = data.get("frames_per_body", colony.frames_per_body)
    volume = data.get("hive_volume_m3", colony.hive_volume_m3)

    body_count, frames, volume = normalize_hive_fields(
        hive_type, body_count, frames, volume
    )
    colony.body_count = body_count
    colony.frames_per_body = frames
    colony.hive_volume_m3 = volume
