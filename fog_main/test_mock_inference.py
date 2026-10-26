import xgboost as xgb
import pandas as pd
import numpy as np

print("1. Loading production fog gatekeeper model...")
model = xgb.XGBClassifier()
model.load_model("fog_gatekeeper_xgboost.json")

# Define class mappings for clear interpretation
class_labels = {
    0: "SAFE / NOMINAL (Class 0) -> 15-min Heartbeat",
    1: "WARNING (Class 1) -> 1-min Intermediate Stream",
    2: "DANGER / SURGE (Class 2) -> 5-sec Burst + Local Actuation",
    3: "SENSOR FAULT (Class 3) -> Maintenance Flag / Ignore Alert"
}

# Define test payloads representing different real-world scenarios
test_scenarios = [
    {
        "name": "Scenario 1: Baseline Dry & Safe",
        "payload": {"distance_cm": 38.5, "rain_raw": 15, "flow_rate_l_min": 0.0, "soil_raw": 3900, "tds_voltage": 0.45}
    },
    {
        "name": "Scenario 2: Warning / Rising Water",
        "payload": {"distance_cm": 12.5, "rain_raw": 1600, "flow_rate_l_min": 210.0, "soil_raw": 1500, "tds_voltage": 1.2}
    },
    {
        "name": "Scenario 3: Severe Flood / Critical Danger",
        "payload": {"distance_cm": 8.0, "rain_raw": 2500, "flow_rate_l_min": 350.0, "soil_raw": 1100, "tds_voltage": 2.8}
    },
    {
        "name": "Scenario 4: Ultrasonic Glitch / Ghost Echo (Class 3)",
        "payload": {"distance_cm": 3.0, "rain_raw": 0, "flow_rate_l_min": 0.0, "soil_raw": 4000, "tds_voltage": 0.4}
    },
    {
        "name": "Scenario 5: Short-Circuited Soil Probe (Class 3)",
        "payload": {"distance_cm": 38.0, "rain_raw": 0, "flow_rate_l_min": 0.0, "soil_raw": 50, "tds_voltage": 0.4}
    }
]

print("\n2. Executing Mock Inference Scenarios...")
for test in test_scenarios:
    # Convert single dictionary payload to a DataFrame matching feature names
    input_df = pd.DataFrame([test["payload"]])
    
    # Predict class and probabilities
    pred_class = model.predict(input_df)[0]
    probabilities = model.predict_proba(input_df)[0]
    
    print(f"\n>> {test['name']}")
    print(f"   Payload: {test['payload']}")
    print(f"   Decision: {class_labels[pred_class]}")
    print(f"   Confidence Breakdown -> [Safe: {probabilities[0]*100:.1f}%, Warning: {probabilities[1]*100:.1f}%, Danger: {probabilities[2]*100:.1f}%, Fault: {probabilities[3]*100:.1f}%]")

print("\nMock inference tests completed successfully!")
