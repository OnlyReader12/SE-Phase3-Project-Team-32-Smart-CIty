import os
from fastapi import FastAPI

app = FastAPI(title="Energy Engine Placeholder", version="0.1.0")


@app.get("/")
def root():
    return {
        "service": "energy-engine-placeholder",
        "status": "running",
        "note": "Placeholder service for uniform deployment.",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "energy-engine-placeholder",
        "amqp_exchange": os.getenv("ENERGY_RABBITMQ_EXCHANGE", "smartcity_exchange"),
        "subscribe_binding_key": os.getenv("ENERGY_RABBITMQ_SUBSCRIBE_BINDING_KEY", "telemetry.energy.#"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
