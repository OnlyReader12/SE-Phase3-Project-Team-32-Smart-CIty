from sqlalchemy import Column, Integer, String, Text
from database.db_core import Base

class TelemetryRecord(Base):
    """
    SQLAlchemy model for persisting the SmartCityObject safely 
    at the edge before pushing it to the overarching domains.
    """
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String, index=True)
    domain = Column(String, index=True)
    protocol_source = Column(String)
    timestamp = Column(String)
    payload_json = Column(Text)  # Store dict as JSON string
