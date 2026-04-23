"""
Persistent Middleware — main application entry point.

Boots the SQLite database, starts the AMQP consumer in a background
thread, and serves the REST API (history, node list, domain view, dashboard).
"""
import threading
import uvicorn
from fastapi import FastAPI

from database import db_core, models
from api import routes
from services.amqp_consumer import start_amqp_consumer

# ── Create / migrate SQLite schema ────────────────────────────────────────
# NOTE: SQLAlchemy create_all does NOT add new columns to existing tables.
# If upgrading from a previous version, delete edge_persistence.db first:
#   rm edge_persistence.db
models.Base.metadata.create_all(bind=db_core.engine)

# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Smart City — Persistent Middleware",
    description=(
        "Single source of truth for all IoT telemetry. "
        "Consumes from RabbitMQ, persists to SQLite, routes to Domain Engines."
    ),
    version="2.0.0",
)

app.include_router(routes.router)


@app.on_event("startup")
def startup_event():
    """Start the blocking AMQP consumer in a daemon thread."""
    consumer_thread = threading.Thread(
        target=start_amqp_consumer,
        args=("127.0.0.1",),
        daemon=True,
        name="amqp-consumer",
    )
    consumer_thread.start()


# ── Banner ─────────────────────────────────────────────────────────────────
print("=" * 55)
print("  Persistent Middleware — Storage Active")
print("  Dashboard : http://localhost:8001/view")
print("  Nodes API : http://localhost:8001/nodes")
print("  Domain API: http://localhost:8001/domain/{energy|water|air}")
print("=" * 55)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
