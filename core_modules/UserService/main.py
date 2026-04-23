"""
UserService — FastAPI entry point.
Port: 8003
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import engine
from database import models
from routers.auth import router as auth_router
from routers.resident import router as resident_router
from routers.manager import router as manager_router
from routers.servicer import router as servicer_router
from routers.nodes import router as nodes_router
from routers.dashboard_alerts_actuators import dash, alerts_router, actuators_router

# Create all tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart City — UserService",
    description="Auth + RBAC + Dashboard + Actuator Control + Alerts",
    version="1.0.0",
)

# Allow Flutter web/mobile to call this service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(auth_router)
app.include_router(resident_router)
app.include_router(manager_router)
app.include_router(servicer_router)
app.include_router(nodes_router)
app.include_router(dash)
app.include_router(alerts_router)
app.include_router(actuators_router)


# ── Engine alert alias ─────────────────────────────────────────────────────
# Engines POST to /internal/alerts (hardcoded in shared/base_engine.py).
# The actual handler lives at /alerts/internal (prefix + path).
# This alias routes the engine's URL to the same handler without touching engine code.
from typing import Optional
from fastapi import Header, Depends
from sqlalchemy.orm import Session
from database.db import get_db
from schemas import AlertIn
from services import alert_service
from core.config import settings
from fastapi import HTTPException

@app.post("/internal/alerts", status_code=202, tags=["Internal"])
def engine_alert_alias(
    body: AlertIn,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Alias for /alerts/internal — called by Domain Engines."""
    if x_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal API key")
    alert_service.process_alert(body, db)
    return {"status": "queued"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "UserService",
        "port": 8003,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
