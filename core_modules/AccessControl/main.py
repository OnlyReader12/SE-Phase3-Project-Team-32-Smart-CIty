from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import httpx

app = FastAPI()

# Example stakeholder roles and allowed engines
ROLE_ENGINES = {
    "energy": ["EnergyManagementEngine"],
    "ehs": ["EHSEngine"],
    "researcher": ["EHSEngine", "EnergyManagementEngine"],
    "resident": ["EHSEngine"]
}

class AccessRequest(BaseModel):
    stakeholder: str
    engine: str
    endpoint: str
    params: dict = {}

@app.post("/route")
async def route_request(req: AccessRequest):
    allowed = ROLE_ENGINES.get(req.stakeholder, [])
    if req.engine not in allowed:
        raise HTTPException(status_code=403, detail="Access denied to this engine.")
    # Forward the request to the appropriate engine (example: localhost)
    url = f"http://localhost:8000/{req.endpoint}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=req.params)
        return response.json()

@app.get("/health")
def health():
    return {"status": "ok"}
