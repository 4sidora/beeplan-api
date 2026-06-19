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

from beeplan.colony_names import generate_colony_name
from beeplan.database import SessionLocal
from beeplan.firmware_catalog import EDGE_VERSION
from beeplan.models import (
    Apiary,
    Colony,
    Concentrator,
    ConcentratorTelemetrySample,
    EdgeDevice,
    EdgeDeviceColonyAssignment,
    TelemetrySample,
    User,
)
from beeplan.seed_dev import DEV_EMAIL
from beeplan.radio_plan import MAX_DEVICES_PER_CONCENTRATOR

APIARY_NAME = "Демо-пасека"
CONCENTRATOR_NAME = "Базовая станция Бердск"

_rng = random.Random(42)
DEMO_COLONY_NAMES = [generate_colony_name(_rng) for _ in range(5)]

# name, public_id, edge_name, breed, colony_type, hive_type, body_count, frames, volume
COLONIES = [
    (DEMO_COLONY_NAMES[0], "dev-edge-1", "Мультидатчик dev-edge-1", "Карникола", "colony", "dadant", 2, 10, None),
    (DEMO_COLONY_NAMES[1], "dev-edge-2", "Мультидатчик dev-edge-2", "Бакфаст", "colony", "magazin", 1, 8, None),
    (DEMO_COLONY_NAMES[2], "dev-edge-3", "Мультидатчик dev-edge-3", "Среднерусская", "nucleus", "ruta", None, 10, None),
    (DEMO_COLONY_NAMES[3], "dev-edge-4", "Мультидатчик dev-edge-4", "Карпатская", "split", "dadant_laying", 1, 20, None),
    (DEMO_COLONY_NAMES[4], "dev-edge-5", "Мультидатчик dev-edge-5", "Местная", "colony", "koloda", None, None, 0.35),
]

INTERVAL_MINUTES = 30
DAYS_BACK = 14
# Устройство для демонстрации «серых областей» на графиках (public_id).
GAP_DEMO_DEVICE_ID = "dev-edge-1"


def _is_gap_demo_ts(ts: datetime, now: datetime) -> bool:
    """Интервалы без телеметрии для демо-графиков (пропуски ≥ 1.5 ч при шаге 30 мин)."""
    age = now - ts
    # Первые ~2 суток периода — нет данных с начала выбранного интервала.
    if age >= timedelta(days=DAYS_BACK - 2):
        return True
    # ~6 ч «тишины» около 5–6 суток назад.
    if timedelta(days=5, hours=12) <= age <= timedelta(days=6, hours=6):
        return True
    # ~4 ч около 10 суток назад.
    if timedelta(days=9, hours=18) <= age <= timedelta(days=10, hours=6):
        return True
    return False


def _find_demo_colony(
    db,
    apiary: Apiary,
    colony_name: str,
    public_id: str,
    legacy_names: list[str],
) -> Colony | None:
    """Найти существующую демо-семью по устройству или старому имени."""
    device = db.scalars(select(EdgeDevice).where(EdgeDevice.public_id == public_id)).first()
    if device is not None and device.current_colony_id is not None:
        colony = db.get(Colony, device.current_colony_id)
        if colony is not None and colony.apiary_id == apiary.id:
            return colony

    for old_name in legacy_names:
        legacy = db.scalars(
            select(Colony).where(Colony.apiary_id == apiary.id, Colony.name == old_name)
        ).first()
        if legacy is not None:
            return legacy

    return db.scalars(
        select(Colony).where(Colony.apiary_id == apiary.id, Colony.name == colony_name)
    ).first()


def _ensure_colony_and_device(
    db,
    apiary: Apiary,
    conc: Concentrator,
    colony_name: str,
    public_id: str,
    edge_name: str,
    bee_breed: str | None = None,
    colony_type: str | None = None,
    hive_type: str | None = None,
    body_count: int | None = None,
    frames_per_body: int | None = None,
    hive_volume_m3: float | None = None,
    *,
    legacy_names: list[str] | None = None,
) -> tuple[Colony, EdgeDevice]:
    colony = _find_demo_colony(db, apiary, colony_name, public_id, legacy_names or [])

    if colony is None:
        colony = Colony(
            apiary_id=apiary.id,
            name=colony_name,
            bee_breed=bee_breed,
            description=f"Демо-семья {colony_name}",
            colony_type=colony_type,
            hive_type=hive_type,
            body_count=body_count,
            frames_per_body=frames_per_body,
            hive_volume_m3=hive_volume_m3,
        )
        db.add(colony)
        db.flush()
    else:
        colony.name = colony_name
        colony.bee_breed = bee_breed
        colony.description = colony.description or f"Демо-семья {colony_name}"
        colony.colony_type = colony_type
        colony.hive_type = hive_type
        colony.body_count = body_count
        colony.frames_per_body = frames_per_body
        colony.hive_volume_m3 = hive_volume_m3
        db.add(colony)

    device = db.scalars(select(EdgeDevice).where(EdgeDevice.public_id == public_id)).first()
    active_on_conc = db.scalar(
        select(func.count())
        .select_from(EdgeDevice)
        .where(EdgeDevice.concentrator_id == conc.id, EdgeDevice.deleted_at.is_(None))
    )
    if device is None:
        device = EdgeDevice(
            concentrator_id=conc.id,
            public_id=public_id,
            name=edge_name,
            current_colony_id=colony.id,
            wake_interval_sec=3600,
        )
        db.add(device)
        db.flush()
        db.add(EdgeDeviceColonyAssignment(device_id=device.id, colony_id=colony.id))
    else:
        device.deleted_at = None
        device.concentrator_id = conc.id
        device.current_colony_id = colony.id
        device.name = edge_name
        db.add(device)

    return colony, device


def _temp_c(ts: datetime, base: float, phase: float, day_index: int) -> float:
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
    simulate_gaps: bool = False,
) -> list[TelemetrySample]:
    rows: list[TelemetrySample] = []
    steps = int(DAYS_BACK * 24 * 60 / INTERVAL_MINUTES)
    for step in range(steps, 0, -1):
        ts = now - timedelta(minutes=INTERVAL_MINUTES * step)
        if simulate_gaps and _is_gap_demo_ts(ts, now):
            continue
        day_index = (now.date() - ts.date()).days
        t = ts.timestamp()

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
        rows.append(
            TelemetrySample(
                colony_id=colony.id,
                source_device_id=device.id,
                metric="signal_level",
                ts=ts,
                value={"dbm": round(-55 - colony_index * 3 + 4 * math.sin(t / 6 + phase), 1)},
            )
        )
        rows.append(
            TelemetrySample(
                colony_id=colony.id,
                source_device_id=device.id,
                metric="battery_voltage",
                ts=ts,
                value={
                    "volts": round(
                        3.30
                        + (72 + colony_index * 4 + 6 * math.sin(t / 12 + phase)) / 100 * 0.90,
                        2,
                    )
                },
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
            rows.append(
                TelemetrySample(
                    colony_id=colony.id,
                    source_device_id=device.id,
                    metric="firmware_version",
                    ts=ts,
                    value={"version": EDGE_VERSION},
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
        conc.deleted_at = None
        db.add(conc)

        colony_profiles = [
            (34.2, 58.0, 0.0),
            (33.8, 56.5, 0.6),
            (32.4, 62.0, 1.2),
            (33.5, 57.0, 1.8),
            (34.0, 55.5, 2.4),
        ]

        pairs: list[tuple[Colony, EdgeDevice]] = []
        legacy_by_device = {
            "dev-edge-1": ["Семья №1 — сильная", "Семья №1"],
            "dev-edge-2": ["Семья №2"],
            "dev-edge-3": ["Семья №3 — послабее", "Семья №3"],
            "dev-edge-4": ["Семья №4"],
            "dev-edge-5": ["Семья №5 (северный ряд)", "Семья №5"],
        }
        for idx, row in enumerate(COLONIES):
            cname, pid, edge_name, breed, ctype, htype, bodies, frames, vol = row
            legacy = legacy_by_device.get(pid, [])
            colony, device = _ensure_colony_and_device(
                db,
                apiary,
                conc,
                cname,
                pid,
                edge_name,
                breed,
                ctype,
                htype,
                bodies,
                frames,
                vol,
                legacy_names=legacy,
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
            print("  Имена семей обновлены:", ", ".join(c.name for c, _ in pairs))
            _print_summary(apiary, pairs, conc)
            return

        if args.force:
            db.execute(delete(TelemetrySample).where(TelemetrySample.colony_id.in_(colony_ids)))

        now = datetime.now(timezone.utc)
        all_rows: list[TelemetrySample] = []
        for idx, ((colony, device), (tb, rb, ph)) in enumerate(zip(pairs, colony_profiles)):
            device.firmware_version = EDGE_VERSION
            db.add(device)
            all_rows.extend(
                _generate_telemetry(
                    colony,
                    device,
                    temp_base=tb,
                    rh_base=rb,
                    phase=ph,
                    colony_index=idx,
                    now=now,
                    simulate_gaps=device.public_id == GAP_DEMO_DEVICE_ID,
                )
            )

        conc_rows: list[ConcentratorTelemetrySample] = []
        steps = int(DAYS_BACK * 24 * 60 / INTERVAL_MINUTES)
        for step in range(steps, 0, -1):
            ts = now - timedelta(minutes=INTERVAL_MINUTES * step)
            t = ts.timestamp()
            conc_rows.append(
                ConcentratorTelemetrySample(
                    concentrator_id=conc.id,
                    metric="signal_level",
                    ts=ts,
                    value={"dbm": round(-58 + 5 * math.sin(t / 8), 1)},
                )
            )
        if args.force:
            db.execute(
                delete(ConcentratorTelemetrySample).where(
                    ConcentratorTelemetrySample.concentrator_id == conc.id
                )
            )
        db.add_all(conc_rows)

        db.add_all(all_rows)
        db.commit()

        print("BeePlan demo data created.")
        print(f"  Пасека: {apiary.name} (id={apiary.id})")
        print(f"  Семей: {len(pairs)}, точек телеметрии: {len(all_rows)}")
        print(f"  Период: последние {DAYS_BACK} дн., шаг {INTERVAL_MINUTES} мин")
        print("  Имена семей:", ", ".join(c.name for c, _ in pairs))
        gap_device = next((d for _, d in pairs if d.public_id == GAP_DEMO_DEVICE_ID), None)
        if gap_device is not None:
            print(
                f"  Демо пропусков на графиках: {gap_device.name} ({GAP_DEMO_DEVICE_ID}) "
                f"→ /devices/edge/{gap_device.id}"
            )
        _print_summary(apiary, pairs, conc)
    finally:
        db.close()


def _print_summary(apiary: Apiary, pairs: list[tuple[Colony, EdgeDevice]], conc: Concentrator) -> None:
    print("  Семьи и устройства:")
    for colony, device in pairs:
        print(f"    - {colony.name} ← {device.public_id} ({device.name})")
    print("  В веб-интерфейсе: откройте карточку семьи — параметры, устройства и графики.")


if __name__ == "__main__":
    main()
