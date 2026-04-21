import os
from fastapi import FastAPI

app = FastAPI(title="Alerting Engine Placeholder", version="0.1.0")


@app.get("/")
def root():
    return {
        "service": "alerting-engine-placeholder",
        "status": "running",
        "note": "Placeholder service for uniform deployment.",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "alerting-engine-placeholder",
        "subscribe_binding_key": os.getenv("ALERTING_RABBITMQ_SUBSCRIBE_BINDING_KEY", "alerts.#"),
        "notification_gateway": os.getenv("ALERTING_NOTIFICATION_GATEWAY", "mock"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
