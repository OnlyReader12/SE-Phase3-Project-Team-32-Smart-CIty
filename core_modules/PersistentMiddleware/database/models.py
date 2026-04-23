from sqlalchemy import Column, Integer, String, Text
from database.db_core import Base

class TelemetryRecord(Base):
    """
    SQLAlchemy model for persisting the SmartCityObject safely 
    at the edge before pushing it to the overarching domains.
    
    The ehs_node_type field classifies EHS telemetry records by sensor type
    (air_quality, water_quality, noise_monitor, weather_station, soil_sensor,
    radiation_gas) enabling efficient domain-specific queries from the middleware.
    """
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String, index=True)
    domain = Column(String, index=True)
    protocol_source = Column(String)
    timestamp = Column(String)
    payload_json = Column(Text)  # Store dict as JSON string
    ehs_node_type = Column(String, index=True, nullable=True)  # air_quality, water_quality, noise_monitor, etc.
