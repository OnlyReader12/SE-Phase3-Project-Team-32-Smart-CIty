import json
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse
from database.db_core import get_db
from database.models import TelemetryRecord
from services.message_broker import RabbitMQPublisher

router = APIRouter()
publisher = RabbitMQPublisher()


@router.get("/history/{node_id}")
def get_node_history(node_id: str, limit: int = 50, db: Session = Depends(get_db)):
    """
    Access point to pull historical records for a specific node directly from 
    the Persistent Middleware source of truth.
    """
    records = db.query(TelemetryRecord).filter(TelemetryRecord.node_id == node_id).order_by(TelemetryRecord.id.desc()).limit(limit).all()
    return {"node_id": node_id, "history": [
        {"ts": r.timestamp, "data": json.loads(r.payload_json), "source": r.protocol_source} for r in records
    ]}

@router.get("/view", response_class=HTMLResponse)
def view_live_dashboard(db: Session = Depends(get_db)):
    """
    Generates a simple HTML view to see all distinct nodes checking in. 
    """
    unique_nodes = db.query(TelemetryRecord.node_id, TelemetryRecord.domain, TelemetryRecord.protocol_source).distinct().all()
    
    html_content = "<html><head><title>Edge Live View</title></head><body style='font-family:sans-serif'>"
    html_content += "<h2>🌐 Persistent Middleware: Live IoT Dashboard</h2>"
    html_content += "<ul>"
    for node in unique_nodes:
        html_content += f"<li><strong>{node.node_id}</strong> ({node.domain}) - Arriving via {node.protocol_source} <a href='/history/{node.node_id}'>[View History]</a></li>"
    html_content += "</ul></body></html>"
    
    return HTMLResponse(content=html_content)
