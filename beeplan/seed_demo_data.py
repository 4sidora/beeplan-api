"""Правдоподобные тестовые данные для демо-пасеки (семьи, ульи, телеметрия).

Запуск после seed_dev:
  python -m beeplan.seed_demo_data
  python -m beeplan.seed_demo_data --force   # пересоздать телеметрию
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from beeplan.database import SessionLocal
from beeplan.models import (
    Apiary,
    Colony,
    Concentrator,
    EdgeDevice,
    EdgeDeviceColonyAssignment,
    TelemetrySample,
    User,
)
from beeplan.seed_dev import DEV_EMAIL

APIARY_NAME = "Демо-пасека"
CONCENTRATOR_NAME = "Демо-концентратор"

COLONIES = [
    ("Семья №1 — сильная", "dev-edge-1", "Улей 1 (южный ряд)", "Карникола"),
    ("Семья №2", "dev-edge-2", "Улей 2", "Бакфаст"),
    ("Семья №3 — послабее", "dev-edge-3", "Улей 3", "Среднерусская"),
    ("Семья №4", "dev-edge-4", "Улей 4", "Карпатская"),
    ("Семья №5", "dev-edge-5", "Улей 5 (северный ряд)", "Местная"),
]

# Интервал замеров и глубина истории
INTERVAL_MINUTES = 30
DAYS_BACK = 14


def _ensure_colony_and_device(
    db,
    apiary: Apiary,
    conc: Concentrator,
    colony_name: str,
    public_id: str,
    label: str,
    bee_breed: str | None = None,
    *,
    legacy_colony_name: str | None = None,
) -> tuple[Colony, EdgeDevice]:
    colony = db.scalars(
        select(Colony).where(Colony.apiary_id == apiary.id, Colony.name == colony_name)
    ).first()
    if colony is None and legacy_colony_name:
        legacy = db.scalars(
            select(Colony).where(Colony.apiary_id == apiary.id, Colony.name == legacy_colony_name)
        ).first()
        if legacy is not None:
            legacy.name = colony_name
            colony = legacy
    if colony is None:
        colony = Colony(apiary_id=apiary.id, name=colony_name, bee_breed=bee_breed)
        db.add(colony)
        db.flush()
    elif bee_breed is not None:
        colony.bee_breed = bee_breed
        db.add(colony)

    device = db.scalars(select(EdgeDevice).where(EdgeDevice.public_id == public_id)).first()
    if device is None:
        device = EdgeDevice(
            concentrator_id=conc.id,
            public_id=public_id,
            label=label,
            current_colony_id=colony.id,
        )
        db.add(device)
        db.flush()
        db.add(EdgeDeviceColonyAssignment(device_id=device.id, colony_id=colony.id))
    else:
        device.current_colony_id = colony.id
        device.label = label
        db.add(device)

    return colony, device


def _temp_c(ts: datetime, base: float, phase: float, day_index: int) -> float:
    """Температура внутри улья, °C — суточный цикл и лёгкий тренд."""
    hour = ts.hour + ts.minute / 60.0
    daily = 1.8 * math.sin((hour - 8) * math.pi / 12.0 + phase)
    weekly = 0.4 * math.sin(day_index * 0.9 + phase)
    noise = random.gauss(0, 0.25)
    return round(base + daily + weekly + noise, 2)


def _rh_percent(ts: datetime, base: float, phase: float) -> float:
    hour = ts.hour + ts.minute / 60.0
    daily = 6.0 * math.sin((hour - 6) * math.pi / 12.0 + phase * 0.7)
    noise = random.gauss(0, 1.2)
    return round(max(42.0, min(78.0, base + daily + noise)), 1)


def _audio_features(ts: datetime, colony_index: int) -> dict:
    """Компактные признаки «звука» для будущих графиков."""
    t = ts.timestamp() / 3600.0
    return {
        "rms": round(0.12 + 0.04 * math.sin(t / 5 + colony_index), 4),
        "peak_hz": int(180 + 40 * colony_index + 10 * math.sin(t / 3)),
        "activity": round(0.45 + 0.15 * math.sin(t / 8 + colony_index * 0.5), 3),
    }


def _generate_telemetry(
    colony: Colony,
    device: EdgeDevice,
    *,
    temp_base: float,
    rh_base: float,
    phase: float,
    colony_index: int,
    now: datetime,
) -> list[TelemetrySample]:
    rows: list[TelemetrySample] = []
    steps = int(DAYS_BACK * 24 * 60 / INTERVAL_MINUTES)
    for step in range(steps, 0, -1):
        ts = now - timedelta(minutes=INTERVAL_MINUTES * step)
        day_index = (now.date() - ts.date()).days

        rows.append(
            TelemetrySample(
                colony_id=colony.id,
                source_device_id=device.id,
                metric="temperature_c",
                ts=ts,
                value={"celsius": _temp_c(ts, temp_base, phase, day_index)},
            )
        )
        rows.append(
            TelemetrySample(
                colony_id=colony.id,
                source_device_id=device.id,
                metric="relative_humidity",
                ts=ts,
                value={"percent": _rh_percent(ts, rh_base, phase)},
            )
        )
        if step % 12 == 0:
            rows.append(
                TelemetrySample(
                    colony_id=colony.id,
                    source_device_id=device.id,
                    metric="audio_features",
                    ts=ts,
                    value=_audio_features(ts, colony_index),
                )
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed realistic demo telemetry for BeePlan")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Удалить существующую телеметрию демо-пасеки и сгенерировать заново",
    )
    args = parser.parse_args()

    random.seed(42)
    db = SessionLocal()
    try:
        user = db.scalars(select(User).where(User.email == DEV_EMAIL)).first()
        if user is None:
            print(f"Сначала выполните: python -m beeplan.seed_dev (пользователь {DEV_EMAIL})")
            return

        apiary = db.scalars(
            select(Apiary).where(Apiary.user_id == user.id, Apiary.name == APIARY_NAME)
        ).first()
        if apiary is None:
            apiary = db.scalars(select(Apiary).where(Apiary.user_id == user.id)).first()
        if apiary is None:
            print("Пасека не найдена. Запустите seed_dev.")
            return

        conc = db.scalars(
            select(Concentrator).where(
                Concentrator.apiary_id == apiary.id,
                Concentrator.name == CONCENTRATOR_NAME,
            )
        ).first()
        if conc is None:
            conc = db.scalars(select(Concentrator).where(Concentrator.apiary_id == apiary.id)).first()
        if conc is None:
            print("Концентратор не найден. Запустите seed_dev.")
            return

        colony_profiles = [
            (34.2, 58.0, 0.0),
            (33.8, 56.5, 0.6),
            (32.4, 62.0, 1.2),
            (33.5, 57.0, 1.8),
            (34.0, 55.5, 2.4),
        ]

        pairs: list[tuple[Colony, EdgeDevice]] = []
        for idx, (cname, pid, label, breed) in enumerate(COLONIES):
            legacy_name = "Семья №1" if idx == 0 else None
            colony, device = _ensure_colony_and_device(
                db, apiary, conc, cname, pid, label, breed, legacy_colony_name=legacy_name
            )
            pairs.append((colony, device))

        active_colony_ids = {c.id for c, _ in pairs}
        orphans = list(
            db.scalars(
                select(Colony).where(
                    Colony.apiary_id == apiary.id,
                    Colony.id.notin_(active_colony_ids),
                )
            ).all()
        )
        for orphan in orphans:
            db.execute(delete(TelemetrySample).where(TelemetrySample.colony_id == orphan.id))
            db.execute(
                delete(EdgeDeviceColonyAssignment).where(
                    EdgeDeviceColonyAssignment.colony_id == orphan.id
                )
            )
            for dev in db.scalars(
                select(EdgeDevice).where(EdgeDevice.current_colony_id == orphan.id)
            ).all():
                dev.current_colony_id = None
                db.add(dev)
            db.delete(orphan)

        db.commit()

        colony_ids = [c.id for c, _ in pairs]
        count = db.scalar(
            select(func.count())
            .select_from(TelemetrySample)
            .where(TelemetrySample.colony_id.in_(colony_ids))
        )
        if count and not args.force:
            print(f"Телеметрия уже есть ({count} записей). Используйте --force для пересоздания.")
            _print_summary(apiary, pairs, conc)
            return

        if args.force:
            db.execute(delete(TelemetrySample).where(TelemetrySample.colony_id.in_(colony_ids)))

        now = datetime.now(timezone.utc)
        all_rows: list[TelemetrySample] = []
        for idx, ((colony, device), (tb, rb, ph)) in enumerate(zip(pairs, colony_profiles)):
            all_rows.extend(
                _generate_telemetry(
                    colony,
                    device,
                    temp_base=tb,
                    rh_base=rb,
                    phase=ph,
                    colony_index=idx,
                    now=now,
                )
            )

        db.add_all(all_rows)
        db.commit()

        print("BeePlan demo data created.")
        print(f"  Пасека: {apiary.name} (id={apiary.id})")
        print(f"  Семей: {len(pairs)}, точек телеметрии: {len(all_rows)}")
        print(f"  Период: последние {DAYS_BACK} дн., шаг {INTERVAL_MINUTES} мин")
        _print_summary(apiary, pairs, conc)
    finally:
        db.close()


def _print_summary(apiary: Apiary, pairs: list[tuple[Colony, EdgeDevice]], conc: Concentrator) -> None:
    print("  Семьи и устройства:")
    for colony, device in pairs:
        print(f"    - {colony.name} ← {device.public_id} ({device.label})")
    print("  В веб-интерфейсе: выберите пасеку и семью — график температуры обновится.")


if __name__ == "__main__":
    main()
