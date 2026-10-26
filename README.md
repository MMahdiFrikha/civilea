# CIVILEA: 3-Tier Intelligent Dam Monitoring & Early Warning System

CIVILEA is a resilient, edge-to-cloud IoT and machine learning infrastructure engineered for autonomous dam structural safety, reservoir telemetry, and real-time hydrological risk triage.

Addressing the limitations of conventional static-threshold alert systems, CIVILEA decouples deterministic mechanical failsafes from multi-stage AI reasoning. It distributes computational intelligence across an on-site ESP32 micro-edge, a local Raspberry Pi fog gateway, and a cloud analytical layer.

---

## 📌 System Highlights

* **3-Tier Compute Hierarchy:** Distributes processing across Edge reflex (sub-second anomaly isolation), Fog triage (real-time risk classification & sensor fault isolation), and Cloud analytics (multi-step time-series horizon forecasting).
* **Hardware-Level Decoupling:** Combines a deterministic physical failsafe (XKC-Y25 non-contact puck) with continuous predictive sensors (ultrasonic clearance, turbine discharge, soil saturation, rain intensity, TDS).
* **Zero Catastrophic Failure Safety Benchmark:** The Fog risk engine achieved a 0% false-negative rate on critical flood events ($0 / 464$ test instances of Risk 2 predicted as Risk 0).
* **Sensor-Fault-Aware Classification:** Employs a 4-class gatekeeper model trained with synthetic anomaly injection to differentiate between genuine hydraulic surges and physical hardware artifacts (e.g., ultrasonic echo loss, probe short circuits).
* **Adaptive Bandwidth Protocol:** Employs event-driven uplink throttling (low-power nominal heartbeats vs. burst-mode streaming during hydrological anomalies) over LoRaWAN and local MQTT backhauls.

---

## 🏗️ System Architecture

```
                      +------------------------------------------+
                      |                CLOUD TIER                |
                      |  - Multi-Horizon Time-Series Forecast    |
                      |    (XGBoost vs. LightGBM: t+1 to t+12)   |
                      |  - Historical Basin Archive & BI Dash    |
                      | |
                      +------------------------------------------+
                                           ▲
                                    MQTT / HTTPS
                                           │
                      +------------------------------------------+
                      |                 FOG TIER                 |
                      |          (Raspberry Pi Gateway)          |
                      |  - MQTT Broker & Store-and-Forward Cache |
                      |  - Protocol Translation (LoRa -> JSON)   |
                      |  - XGBoost Multi-Class Risk Classifier   |
                      |    (Normal / Watch / Surge / Fault)      |
                      +------------------------------------------+
                                           ▲
                                    LoRaWAN / UART
                                           │
                      +------------------------------------------+
                      |                EDGE TIER                 |
                      |            (ESP32 DevKit V1)             |
                      |  - Dual-Rail Perception Layer (3.3V/5V)  |
                      |  - Hard-Interrupt Flow Debouncing (2000µs|
                      |  - Embedded C++ Isolation Forest         |
                      |  - Deterministic Mechanical Failsafe     |
                      +------------------------------------------+
```

---

## 📐 Architectural Design Patterns

CIVILEA integrates distributed systems and embedded software patterns across its three tiers:

| Pattern Name | Architecture Tier | Exact Implementation in CIVILEA System |
| :--- | :--- | :--- |
| **Publish / Subscribe (Pub/Sub)** | Tier 2 (Fog) & Tier 3 (Cloud) | Uses a Mosquitto MQTT broker on the Raspberry Pi to publish structured JSON telemetry to regional and cloud topics, decoupling physical nodes from consumers. |
| **Event-Driven & Heartbeat** | Tier 1 (Edge Node) | The ESP32 triggers emergency burst transmission when an anomaly occurs (iForest score $< 3.50$ or float switch trip). Under nominal conditions, it transmits low-frequency heartbeat pings to save power and LPWAN duty cycle. |
| **Data Aggregation & Bit Packing** | Tier 1 (Edge Node) | Packs the 5-dimensional float payload (`tds_v`, `flow_rate`, `distance_cm`, `rain_raw`, `soil_raw`) into an optimized binary C++ struct, minimizing LoRaWAN airtime and meeting regional duty-cycle limits. |
| **Store-and-Forward** | Tier 1 (Edge) & Tier 2 (Fog) | If radio connectivity between the ESP32 and Fog node drops, telemetry buffers into SPI Flash memory. Upon reconnection, packets flush in FIFO sequence to prevent gaps. |
| **Circuit Breaker** | Tier 1 (Edge Node) | When LoRaWAN ACKs fail repeatedly past a set retry threshold, the system trips the radio and switches the network stack to Wi-Fi/cellular failover routes. |
| **Protocol Translation** | Tier 2 (Fog Gateway) | Raspberry Pi ingests raw LoRaWAN radio frames, unpacks the binary struct, enriches the payload, and translates it into standard MQTT/JSON topics. |
| **Edge Intelligence (TinyML)** | Tier 1 (Edge) & Tier 2 (Fog) | ESP32 executes an offline C++ Isolation Forest inference every second ($1\,\text{Hz}$). Raspberry Pi executes an XGBoost Classifier for real-time risk triage. |
| **Time-Sensitive Networking (TSN Priority)** | Tier 1 (Edge) & Tier 2 (Fog) | Deterministic puck alerts bypass standard sensor queues and take top transmission priority over ambient metrics. |
| **Lambda Architecture** | Tier 2 (Fog) & Tier 3 (Cloud) | **Speed/Hot Path:** Routes immediate emergency triggers directly to edge alerts and SMS. **Batch/Cold Path:** Streams raw time-series matrices to cloud storage for horizon forecasting. |
| **Device Shadow** | Tier 3 (Cloud) | Maintains a virtual JSON state of the edge node and basin attributes in the cloud, allowing client apps to query system status without waking edge nodes. |

---

## 🔌 Hardware & Pinout Specifications

The Edge Node runs on the **ESP32 DevKit V1** (3.3V logic). Because the sensor suite integrates mixed-voltage peripherals, a dual-rail topology with passive voltage division prevents overvoltage to the GPIOs:

* **Low-Voltage Rail (3.3V):** Directly fed by the ESP32 `3V3` regulator pin for analog sensors.
* **High-Voltage Rail (5.0V):** Fed by `VIN` for acoustic and digital sensors.
* **Protective Voltage Divider Shields:** Two 1:1 resistor shields ($R_1 = 220\,\Omega$, $R_2 = 220\,\Omega$) step 5V return signals down to a safe $2.5\,\text{V}$ (Logic HIGH) for the ESP32 GPIOs.

### Pinout Matrix

| Subsystem | Sensor Hardware | Power (VCC) | Ground | Signal Routing | ESP32 GPIO | Logic Level |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Precipitation** | FR-04 Rain Plate + LM393 | 3.3V Rail | GND | Direct Analog Line | `GPIO 32` (ADC1_CH4) | 3.3V Native (Inverted) |
| **Soil Saturation** | Capacitive Hygrometer Probe | 3.3V Rail | GND | Direct Analog Line | `GPIO 33` (ADC1_CH5) | 3.3V Native |
| **Water Quality** | TDS Meter (Purity/Turbidity) | 3.3V Rail | GND | Direct Analog Line | `GPIO 34` (ADC1_CH6) | 3.3V Native |
| **Dam Clearance** | JSN-SR04T / HC-SR04 Ultrasonic | 5.0V (VIN) | GND | Direct Output Trigger | `GPIO 05` | 3.3V Out |
| **Echo Pulse** | JSN-SR04T / HC-SR04 Ultrasonic | 5.0V (VIN) | GND | **2-Resistor Shield** ($220\,\Omega \times 2$) | `GPIO 18` | 2.5V Safe In |
| **Water Level** | XKC-Y25-PNP (Float Switch/Puck) | 5.0V (VIN) | GND | **2-Resistor Shield** ($220\,\Omega \times 2$) | `GPIO 27` (PULLDOWN)| 2.5V Safe In |
| **Inflow Rate** | YF-S201 Turbine (Hall Effect) | 5.0V (VIN) | GND | Direct Open-Collector (`PULLUP`) | `GPIO 14` (Interrupt) | 3.3V Clamped |
| **Acoustic Alarm** | Passive Piezoelectric Buzzer | 3.3V Rail | GND | Hardware PWM Frequency | `GPIO 04` (PWM Tone) | 2000 Hz Out |

> **Firmware Notes:**
> 1. *Flow Interrupt:* The YF-S201 uses an internal `INPUT_PULLUP` configuration with a $2000\,\mu\text{s}$ hardware debounce routine to eliminate electromagnetic false triggers.
> 2. *Soil Calibration:* The capacitive soil probe is calibrated to a dry-air baseline ADC of $2700$ ($\approx 2.2\,\text{V}$), rather than the absolute $4095$, ensuring realistic volumetric soil saturation readings.
> 3. *Prototype Depth Scaling:* A physical 20 cm test vessel is mapped to a 40 cm hydraulic training profile by applying an exact $2.0\times$ software multiplier to ultrasonic readings.

---

## 📊 Experimental Results & Machine Learning Benchmarks

### 1. Functional Safety Decoupling
During dataset engineering, the deterministic binary flag `overflow_alert` was isolated from the continuous predictive feature matrix:
* **The Problem:** Including `overflow_alert` gave models an artificial cheat sheet, driving training accuracy to an unrealistic $99.94\%$ while blinding the model to early warning signs when the switch was open.
* **The Solution:** Decoupling the binary failsafe forces the models to evaluate multivariate continuous hydrology (`distance_cm`, `flow_rate`, `rain_raw`, `soil_raw`, `tds_v`), preserving the puck as an independent hardware override.

### 2. Target Variable Evolution (Deterministic vs. Probabilistic)

```
[ Phase 1: Static Rules ]             [ Phase 2: Probabilistic Calibration ]
Strict IF/THEN boundaries            Stochastic distributions via KNIME Python node
Overfitted to threshold cuts         Simulates environmental noise & sensor margin
Test Accuracy: 99.94% (Memorized)   Test Accuracy: 95.61% (Real-World Generalization)
```

In Phase 2, bounded sensor intervals were converted into probabilistic ground-truth distributions (e.g., $10 < \text{Distance} \le 12\,\text{cm}$, heavy inflow, and turbidity maps to an $80\%$ probability of Risk 2, $18\%$ Risk 1, and $2\%$ Risk 0). An absolute safety condition ($\text{Distance} < 5\,\text{cm}$) assigned a $98\%$ probability to critical danger to maintain structural safety boundaries.

### 3. Fog-Tier XGBoost Performance (Segura River Basin Telemetry)

* **Overall Test Accuracy:** **95.61%**
* **Inference Overhead:** $< 12\,\text{ms}$ on Raspberry Pi Fog Gateway.

#### Test Classification Report
```
              precision    recall  f1-score   support

     Class 0     0.9912    0.9854    0.9883      1782
     Class 1     0.6421    0.7386    0.6870       176
     Class 2     0.9620    0.9784    0.9701       464

    accuracy                         0.9561      2422
   macro avg     0.8651    0.9008    0.8818      2422
weighted avg     0.9602    0.9561    0.9578      2422
```

#### Confusion Matrix & Safety Analysis
```
               Predicted 0    Predicted 1    Predicted 2
Actual 0 [        1756            25              1     ]
Actual 1 [          41           130              5     ]
Actual 2 [           0            10            454     ]
```

* **Zero Catastrophic Failures:** Out of $464$ test instances of critical danger (Risk 2), **$0$ instances were misclassified as safe (Risk 0)**.
* **Realistic Boundary Uncertainty:** Class 1 (Warning) exhibits expected borderline hesitation ($\approx 64\%$ precision, $74\%$ recall), behaving like a human hydrologist in transitional states.
* **High Specificity:** False alarm rate under nominal reservoir operations (Class 0) was under $1.5\%$.

### 4. Edge-Tier Isolation Forest Anomaly Detection
The ESP32 runs an offline C++ Isolation Forest inference every second:
* Evaluates multivariate anomalies across all 5 continuous dimensions simultaneously.
* **False Alarm Filtering:** A high water level accompanied by zero inflow and dry rain/soil is recognized as a static, controlled reservoir state rather than a flood.
* **Preemptive Warning:** Fully saturated soil combined with an incoming rainfall spike drops the anomaly safety score below the $3.50$ baseline, sounding the local 2000Hz buzzer hours before physical clearance reaches flood limits.
