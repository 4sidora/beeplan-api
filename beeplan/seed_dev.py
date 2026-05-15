"""Seed development user, apiary, concentrator, colony, edge device. Run after migrations."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from beeplan.database import SessionLocal
from beeplan.models import Apiary, Colony, Concentrator, EdgeDevice, EdgeDeviceColonyAssignment, User
from beeplan.security import hash_password


def main() -> None:
    db = SessionLocal()
    try:
        email = "dev@beeplan.local"
        existing = db.scalars(select(User).where(User.email == email)).first()
        if existing:
            print("Seed already applied (user exists).")
            return

        user = User(email=email, hashed_password=hash_password("devpassword"))
        db.add(user)
        db.flush()

        apiary = Apiary(user_id=user.id, name="Демо-пасека")
        db.add(apiary)
        db.flush()

        token = str(uuid.uuid4())
        conc = Concentrator(apiary_id=apiary.id, name="Демо-концентратор", ingest_token=token)
        db.add(conc)
        db.flush()

        colony = Colony(apiary_id=apiary.id, name="Семья №1")
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
        print(f"  User: {email} / devpassword")
        print("  Authorization for gateway (ingest):")
        print(f"    Authorization: Bearer {token}")
        print("  Edge device public_id for telemetry: dev-edge-1")
    finally:
        db.close()


if __name__ == "__main__":
    main()
