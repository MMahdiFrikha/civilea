from collections import deque
from datetime import datetime, timezone
import json
import paho.mqtt.client as mqtt
import pandas as pd
import requests
import xgboost as xgb
from kafka import KafkaConsumer

# Import local modules
import decoder
import storage

# =========================================================================
# 1. NETWORK & TOPIC CONFIGURATION
# =========================================================================
# Inbound LoRaWAN Telemetry Stream (Treetronix / Actility)
KAFKA_BROKER = "kafka.treetronix.com:9095"
KAFKA_TOPIC = "AS.Treetronix.v1"
TARGET_DEVEUI = "4422222222222244"

# Outbound Cloud Broker (HiveMQ)
CLOUD_BROKER = "broker.hivemq.com"
CLOUD_PORT = 1883
CLOUD_TOPIC_TELEMETRY = "civilea/cloud/telemetry"
CLOUD_TOPIC_ALERTS = "civilea/cloud/alerts"
CLOUD_TOPIC_MAINT = "civilea/cloud/maintenance"

RENDER_API_URL = "https://dam-monitor-fg5p.onrender.com/predict"

# 36-step rolling buffer for 7-feature states (36 * 7 = 252 values)
telemetry_sequence_buffer = deque(maxlen=36)

# =========================================================================
# 2. SYSTEM INITIALIZATION
# =========================================================================
print("[SYSTEM] Initializing local SQLite storage...")
storage.init_db()

print("[SYSTEM] Loading XGBoost Gatekeeper Model...")
model = xgb.XGBClassifier()
model.load_model("fog_gatekeeper_xgboost.json")
print("[SYSTEM] Model loaded successfully.")

# Initialize Cloud MQTT Client for Outbound Dashboard Traffic
cloud_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="RPi_Fog_Router")
cloud_client.connect(CLOUD_BROKER, CLOUD_PORT, 60)
cloud_client.loop_start()

# =========================================================================
# 3. CORE PROCESSING & INFERENCE PIPELINE
# =========================================================================
def process_payload(raw_bytes: bytes, station_eui: str):
    """Feeds 14-byte raw telemetry into XGBoost, updates buffer, and publishes to Cloud."""
    try:
        record = decoder.decode_lora_payload(raw_bytes)
        if record is None:
            return

        # 5 Core features for Gatekeeper Classifier
        features = {
            'distance_cm': record['distance_cm'],
            'rain_raw': record['rain_raw'],
            'flow_rate_l_min': record['flow_rate_l_min'],
            'soil_raw': record['soil_raw'],
            'tds_voltage': record['tds_voltage']
        }

        print(
            f"[RAW INCOMING] dist={features['distance_cm']}, "
            f"flow={features['flow_rate_l_min']}, "
            f"rain={features['rain_raw']}, "
            f"soil={features['soil_raw']}, "
            f"tds={features['tds_voltage']}, "
            f"station={record.get('station_id')}"
        )

        input_df = pd.DataFrame([features])

        # Predict Class (0=Safe, 1=Warning, 2=Danger, 3=Fault)
        prediction = int(model.predict(input_df)[0])
        timestamp = datetime.now(timezone.utc).isoformat()
        print(f"\n[{timestamp}] Node: {station_eui} | Station ID: {record['station_id']} | AI Classification: Class {prediction}")

        # Save to Local SQLite Database
        storage.save_telemetry(record, prediction)

        # -----------------------------------------------------------------
        # ROLLING SEQUENCE BUFFER & RENDER CLOUD INFERENCE
        # -----------------------------------------------------------------
        feature_vector_7 = [
            float(record['distance_cm']),
            float(record['rain_raw']),
            float(record['flow_rate_l_min']),
            float(record['soil_raw']),
            float(record['tds_voltage']),
            float(record.get('battery_v', 0.0)),
            float(prediction)
        ]

        telemetry_sequence_buffer.append(feature_vector_7)
        print(f"[BUFFER] Reading cached ({len(telemetry_sequence_buffer)}/36 states)")

        # Trigger Render forecast once buffer holds 36 complete timesteps (252 values)
        if len(telemetry_sequence_buffer) == 36:
            flat_252_sequence = [val for timestep in telemetry_sequence_buffer for val in timestep]

            render_payload = {
                "sequence": flat_252_sequence,
                "layer2_risk": min(prediction, 2),
                "station_id": str(record.get('station_id', "0"))
            }

            print("[RENDER] Sending 252-feature sequence to Render API...")
            try:
                render_res = requests.post(RENDER_API_URL, json=render_payload, timeout=60)
                if render_res.status_code == 200:
                    forecast_data = render_res.json()
                    print("[RENDER SUCCESS] Multi-step Horizon Forecast:", forecast_data)
                else:
                    print(f"[RENDER ERROR {render_res.status_code}]:", render_res.text)
            except requests.exceptions.Timeout:
                print("[RENDER TIMEOUT] Server taking long to respond (cold start).")
            except Exception as req_err:
                print(f"[RENDER NETWORK ERROR]: {req_err}")

        # -----------------------------------------------------------------
        # CLOUD MQTT GATEWAY PUBLISHING (HiveMQ)
        # -----------------------------------------------------------------
        cloud_payload = json.dumps({
            "timestamp": timestamp,
            "station_id": record["station_id"],
            "telemetry": features,
            "alerts": record.get("alerts", {}),
            "classification": prediction
        })

        if prediction == 0:
            print(" -> SAFE: Archived locally. Sending QoS 0 heartbeat to Cloud.")
            cloud_client.publish(CLOUD_TOPIC_TELEMETRY, cloud_payload, qos=0)

        elif prediction == 1:
            print(" -> WARNING: Water rising. Forwarding QoS 1 telemetry to Cloud.")
            cloud_client.publish(CLOUD_TOPIC_TELEMETRY, cloud_payload, qos=1)

        elif prediction == 2:
            print(" -> DANGER (EMERGENCY): Bursting QoS 2 stream to Alert Topic!")
            cloud_client.publish(CLOUD_TOPIC_ALERTS, cloud_payload, qos=2)

        elif prediction == 3:
            print(" -> FAULT: Hardware glitch detected. Flagging Maintenance Topic.")
            maint_payload = json.dumps({
                "timestamp": timestamp,
                "station_id": record["station_id"],
                "error": "Sensor Fault / Out of Bounds",
                "raw_data": features
            })
            cloud_client.publish(CLOUD_TOPIC_MAINT, maint_payload, qos=1)

    except Exception as e:
        print(f"[Error] Engine exception processing payload: {e}")

# =========================================================================
# 4. DIRECT KAFKA INGESTION LOOP
# =========================================================================
print(f"[SYSTEM] Connecting directly to Kafka broker at {KAFKA_BROKER}...")
consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=[KAFKA_BROKER],
    auto_offset_reset="latest",
    enable_auto_commit=True,
    group_id="rpi-civilea-fog-consumer"
)

print(f"[SYSTEM] Fog Engine is LIVE. Consuming '{KAFKA_TOPIC}'...")

try:
    for message in consumer:
        try:
            raw_text = message.value.decode("utf-8")
            data = json.loads(raw_text)

            # Extract Actility ThingPark message container
            uplink = data.get("DevEUI_uplink", data)
            dev_eui = uplink.get("DevEUI", "")

            # Filter for your specific device (skip foreign node traffic)
            if TARGET_DEVEUI and dev_eui.upper() != TARGET_DEVEUI.upper():
                continue

            # Extract the raw payload hex string
            payload_hex = uplink.get("payload_hex", uplink.get("payload", ""))
            if not payload_hex:
                continue

            # Convert hex string to binary bytes for decoder.py
            raw_bytes = bytes.fromhex(payload_hex)
            process_payload(raw_bytes, dev_eui)

        except json.JSONDecodeError:
            print("[Error] Non-JSON payload received on Kafka topic.")
        except Exception as msg_err:
            print(f"[Error] Message parse error: {msg_err}")

except KeyboardInterrupt:
    print("\n[SYSTEM] Shutting down Fog Engine gracefully...")
    consumer.close()
    cloud_client.disconnect()
