from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List

DB_PATH = "telemetry.db"

def init_db():
    """Initializes the SQLite table for local telemetry caching."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                station_id INTEGER NOT NULL,
                flow_rate REAL NOT NULL,
                distance REAL NOT NULL,
                rain_raw INTEGER NOT NULL,
                soil_raw INTEGER NOT NULL,
                tds_voltage REAL NOT NULL,
                edge_ai_score REAL NOT NULL,
                overflow_alert INTEGER NOT NULL,
                ai_anomaly_alert INTEGER NOT NULL,
                fog_class INTEGER NOT NULL,
                synced_to_cloud INTEGER DEFAULT 0
            )
        """
        )
        conn.commit()
    print("Database initialized successfully.")

def save_telemetry(record: Dict[str, Any], fog_class: int) -> int:
    """Saves an unpacked telemetry record and its Fog classification to SQLite."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Class 0 (Safe) doesn't need to be bulk-synced later, so mark it as synced = 1
    # Classes 1, 2, and 3 are marked as 0 (unsynced) in case the internet drops
    is_synced = 1 if fog_class == 0 else 0 

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO telemetry_cache (
                timestamp, station_id, flow_rate, distance,
                rain_raw, soil_raw, tds_voltage, edge_ai_score,
                overflow_alert, ai_anomaly_alert, fog_class, synced_to_cloud
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                now_iso,
                record["station_id"],
                record["flow_rate_l_min"],
                record["distance_cm"],
                record["rain_raw"],
                record["soil_raw"],
                record["tds_voltage"],
                record["edge_ai_score"],
                int(record["alerts"]["overflow"]),
                int(record["alerts"]["ai_anomaly"]),
                fog_class,
                is_synced
            ),
        )
        conn.commit()
        return cursor.lastrowid

def get_unsynced_records(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves records waiting to be pushed to the cloud (Emergencies/Anomalies)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM telemetry_cache WHERE synced_to_cloud = 0 ORDER BY id ASC LIMIT ?
        """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def mark_as_synced(record_ids: List[int]):
    """Marks batch records as synced to prevent redundant re-transmissions."""
    if not record_ids:
        return
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in record_ids)
        cursor.execute(
            f"""
            UPDATE telemetry_cache SET synced_to_cloud = 1 WHERE id IN ({placeholders})
        """,
            record_ids,
        )
        conn.commit()
