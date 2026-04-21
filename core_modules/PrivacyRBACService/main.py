import os
from fastapi import FastAPI

app = FastAPI(title="Privacy RBAC Service Placeholder", version="0.1.0")


@app.get("/")
def root():
    return {
        "service": "privacy-rbac-placeholder",
        "status": "running",
        "note": "Placeholder service for uniform deployment.",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "privacy-rbac-placeholder",
        "api_base": os.getenv("PRIVACY_API_BASE", "http://privacy-rbac:8005"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
