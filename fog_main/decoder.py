import struct
import base64
from typing import Any, Dict, Optional

# C++ Struct: uint8_t, uint16_t x 6, uint8_t (Total 14 bytes)
PAYLOAD_FORMAT = "<BHHHHHHB"
EXPECTED_SIZE = struct.calcsize(PAYLOAD_FORMAT)  # 14 bytes

def decode_lora_payload(raw_payload: Any) -> Optional[Dict[str, Any]]:
    """Unpacks a 14-byte binary (or base64) payload into a structured JSON-ready dictionary."""
    
    # 1. Handle base64 encoding if coming from a standard LoRa MQTT JSON payload
    if isinstance(raw_payload, str):
        try:
            raw_bytes = base64.b64decode(raw_payload)
        except Exception:
            raw_bytes = raw_payload.encode('utf-8')
    else:
        raw_bytes = raw_payload

    # 2. Validate Length (Graceful fail instead of crashing)
    if len(raw_bytes) != EXPECTED_SIZE:
        print(f"[Decoder Error] Expected {EXPECTED_SIZE} bytes, got {len(raw_bytes)}")
        return None

    # 3. Unpack into named variables
    (
        station_id,
        raw_flow,
        raw_dist,
        rain_raw,
        soil_raw,
        raw_tds,
        raw_ai_score,
        alert_bitfield,
    ) = struct.unpack(PAYLOAD_FORMAT, raw_bytes[:14])

    # 4. Reconstruct floating-point values with clean rounding
    return {
        "station_id": station_id,
        "flow_rate_l_min": round(raw_flow / 100.0, 2),
        "distance_cm": round(raw_dist / 10.0, 1),
        "rain_raw": rain_raw,
        "soil_raw": soil_raw,
        "tds_voltage": round(raw_tds / 1000.0, 3),
        "edge_ai_score": round(raw_ai_score / 100.0, 2),
        "alerts": {
            "overflow": bool(alert_bitfield & 0x01),
            "ai_anomaly": bool(alert_bitfield & 0x02),
        },
    }
