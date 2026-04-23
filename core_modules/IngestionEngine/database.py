import sqlite3
from datetime import datetime

def get_db_connection():
    conn = sqlite3.connect('ingestion_data.db')
    conn.row_factory = sqlite3.Row
    return conn

def create_table():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT,
            metric TEXT,
            value REAL,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_telemetry(node_id, metric, value, timestamp=None):
    if not timestamp:
        timestamp = datetime.utcnow().isoformat()
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO telemetry (node_id, metric, value, timestamp) VALUES (?, ?, ?, ?)',
        (node_id, metric, value, timestamp)
    )
    conn.commit()
    conn.close()
