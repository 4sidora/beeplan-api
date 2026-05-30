from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from beeplan.config import get_settings
from beeplan.deps import get_current_user
from beeplan.models import User
from beeplan.schemas import UserOut
from beeplan.routers import auth, catalog, devices, firmware, health

settings = get_settings()

app = FastAPI(title="BeePlan API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(devices.router)
app.include_router(firmware.router)


@app.get("/v1/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
