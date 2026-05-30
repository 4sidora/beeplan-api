"""Seed development user, apiary, concentrator, colony, edge device. Run after migrations."""

from __future__ import annotations

import uuid

from sqlalchemy import select

import random

from beeplan.colony_names import generate_colony_name
from beeplan.database import SessionLocal
from beeplan.models import Apiary, Colony, Concentrator, EdgeDevice, EdgeDeviceColonyAssignment, User
from beeplan.security import hash_password

DEV_EMAIL = "dev@example.com"
LEGACY_DEV_EMAIL = "dev@beeplan.local"
DEV_PASSWORD = "devpassword"


def main() -> None:
    db = SessionLocal()
    try:
        email = DEV_EMAIL
        existing = db.scalars(select(User).where(User.email == email)).first()
        if existing:
            print("Seed already applied (user exists).")
            print(f"  User: {email} / {DEV_PASSWORD}")
            print("  Для тестовых графиков: python -m beeplan.seed_demo_data")
            return

        legacy = db.scalars(select(User).where(User.email == LEGACY_DEV_EMAIL)).first()
        if legacy:
            legacy.email = email
            db.commit()
            print("BeePlan dev seed: migrated legacy user email.")
            print(f"  User: {email} / {DEV_PASSWORD}")
            return

        user = User(email=email, hashed_password=hash_password(DEV_PASSWORD))
        db.add(user)
        db.flush()

        apiary = Apiary(user_id=user.id, name="Демо-пасека")
        db.add(apiary)
        db.flush()

        token = str(uuid.uuid4())
        conc = Concentrator(apiary_id=apiary.id, name="Демо-концентратор", ingest_token=token)
        db.add(conc)
        db.flush()

        colony = Colony(
            apiary_id=apiary.id,
            name=generate_colony_name(random.Random(42)),
            bee_breed="Карникола",
        )
        db.add(colony)
        db.flush()

        device = EdgeDevice(
            concentrator_id=conc.id,
            public_id="dev-edge-1",
            label="Улей демо",
            current_colony_id=colony.id,
        )
        db.add(device)
        db.flush()
        db.add(
            EdgeDeviceColonyAssignment(
                device_id=device.id,
                colony_id=colony.id,
            )
        )
        db.commit()

        print("BeePlan dev seed created.")
        print(f"  User: {email} / {DEV_PASSWORD}")
        print("  Authorization for gateway (ingest):")
        print(f"    Authorization: Bearer {token}")
        print("  Edge device public_id for telemetry: dev-edge-1")
        print("  Демо-графики: python -m beeplan.seed_demo_data")
    finally:
        db.close()


if __name__ == "__main__":
    main()
