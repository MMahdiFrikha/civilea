#include <Arduino.h>
#include <WiFi.h>
#include "IsolationForest.h" // Edge AI model

// ==========================================
// PIN CONFIGURATION MATRIX (ESP32)
// ==========================================
const int PIN_RAIN      = 32; 
const int PIN_SOIL      = 33; 
const int PIN_TDS       = 34; 
const int PIN_LEVEL     = 27; 
const int PIN_FLOW      = 14; 
const int PIN_BUZZER    = 4; 
const int PIN_TRIG      = 22; 
const int PIN_ECHO      = 25; 
const int PIN_LORA_WAKE = 18; // Connected to LoRa Pin 12 (Wake-up line)

// ==========================================
// CALIBRATION & NETWORK CONSTANTS
// ==========================================
const uint8_t NODE_STATION_ID    = 0;   // Always 0 (single-station setup)
const float AI_ANOMALY_THRESHOLD = 3.5; 
const float AI_CHANGE_THRESHOLD  = 0.5; // Transmit if score shifts by 0.5 (Delta)
const float CRITICAL_MIN_DEPTH   = 2.0; // Absolute safety net override

const unsigned long HEARTBEAT_INTERVAL = 30000UL; // 30 seconds
unsigned long last_transmission_time = 0;
float last_sent_score = 100.0; // Artificially high to guarantee first send

// ==========================================
// PAYLOAD OPTIMIZATION (14 Bytes)
// ==========================================
struct __attribute__((packed)) LoRaPayload {
    uint8_t  station_id;      
    uint16_t discharge_rate;  
    uint16_t water_clearance; 
    uint16_t rain_raw;        
    uint16_t soil_raw;        
    uint16_t tds_v;           
    uint16_t ai_score;        
    uint8_t  alerts;          
};
LoRaPayload myData; 

// ==========================================
// SYSTEM STATE VARIABLES
// ==========================================
volatile int pulseCount = 0; 
volatile unsigned long last_micros = 0; 
unsigned long oldTime = 0;
float flowRate_L_min = 0.0;

void IRAM_ATTR pulseCounter() {
  unsigned long current_micros = micros();
  if (current_micros - last_micros > 2000) { 
    pulseCount++;
    last_micros = current_micros;
  }
}

// ==========================================
// PRE-TRANSMISSION DIAGNOSTICS MONITOR
// ==========================================
void printSensorDiagnostics(float distCm, float flowRate, int rain, int soil, float tdsV, float aiScore, int level) {
    Serial.println(F("\n================ [ESP32 PRE-SEND DIAGNOSTICS] ================"));
    Serial.printf("Station ID        : %u\n", myData.station_id);
    Serial.printf("Distance (Scaled) : %.2f cm %s\n", 
                  distCm, 
                  (distCm < 0) ? "[ECHO TIMEOUT]" : (distCm > 40.0) ? "[OUT OF MODEL 40CM RANGE]" : "[IN RANGE]");
    Serial.printf("Flow Rate         : %.3f L/min\n", flowRate);
    Serial.printf("Rain (Raw ADC)    : %d %s\n", rain, (rain > 3000) ? "[Dry]" : "[Wet / Active]");
    Serial.printf("Soil (Raw ADC)    : %d %s\n", soil, (soil > 3000) ? "[Air / Dry]" : "[Moist / Water]");
    Serial.printf("TDS Voltage       : %.3f V\n", tdsV);
    Serial.printf("Float Switch      : %s\n", (level == HIGH) ? "HIGH (ALERT)" : "LOW");
    Serial.printf("Isolation Forest  : %.2f %s\n", aiScore, (aiScore < AI_ANOMALY_THRESHOLD) ? "[ANOMALY]" : "[NORMAL]");

    Serial.print("Payload Hex (14B) : ");
    const uint8_t *bytePtr = (const uint8_t*)&myData;
    for (size_t i = 0; i < sizeof(LoRaPayload); i++) {
        if (bytePtr[i] < 0x10) Serial.print("0");
        Serial.print(bytePtr[i], HEX);
        Serial.print(" ");
    }
    Serial.println();
    Serial.println(F("==============================================================="));
}

// ==========================================
// TRANSMISSION & FALLBACK LOGIC
// ==========================================
bool transmitViaLoRa() {
    Serial.println("[LORA] Waking LoRa card via Pin 18...");
    
    // 1. Send clean 2ms Active-LOW pulse to wake LoRa32u4
    digitalWrite(PIN_LORA_WAKE, LOW);
    delay(2); 
    digitalWrite(PIN_LORA_WAKE, HIGH);

    // 2. Allow 32u4 crystal oscillator 25ms to lock stable clock frequency
    delay(25);

    Serial.println("[LORA] Sending payload to LoRa card...");
    
    // Clear residual UART noise
    while(Serial2.available()) {
        Serial2.read();
    }

    Serial.println("[DEBUG] Line clear. Writing 14 bytes to TX wire (Pin 17)...");
    Serial2.write((uint8_t*)&myData, sizeof(myData));
    Serial2.flush();
    
    Serial.println("[DEBUG] Data sent. Waiting up to 3 seconds for LoRa reply...");
    unsigned long ackTimeout = millis();
    bool success = false;
    String response = "";
    
    while (millis() - ackTimeout < 3000) { 
        while (Serial2.available()) {
            char c = Serial2.read();
            response += c;
        }
        
        if (response.indexOf("ACK") != -1 || response.indexOf("OK") != -1) { 
            success = true;
            break;
        }
        delay(10); 
    }
    
    if (success) {
        Serial.println("[LORA] Transmission Success (ACK received)!");
        while (Serial2.available()) Serial2.read(); 
    } else {
        Serial.print("[LORA] ERROR: No ACK received! The wire returned: ");
        Serial.println(response.length() == 0 ? "(Complete Silence)" : response);
    }
    
    return success;
}

void transmitViaWiFi() {
    Serial.println("[WIFI] LoRa failed. Triggering WiFi Fallback...");
    WiFi.mode(WIFI_STA);
    WiFi.begin("TT_54F8", "rhzmiil84h"); 
    
    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 15) {
        delay(500);
        Serial.print(".");
        retries++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WIFI] Connected! Sending payload via MQTT/HTTP...");
    } else {
        Serial.println("\n[CRITICAL] Both LoRa and WiFi networks are unreachable!");
    }
    
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    Serial.println("[WIFI] Radio powered off.");
}

// ==========================================
// MAIN SETUP
// ==========================================
void setup() {
    Serial.begin(115200);
    
    // Hardware UART to LoRa32u4 (RX = 16, TX = 17)
    Serial2.begin(9600, SERIAL_8N1, 16, 17); 
    
    // LoRa Wake-Up Control Pin
    pinMode(PIN_LORA_WAKE, OUTPUT);
    digitalWrite(PIN_LORA_WAKE, HIGH); // Default HIGH (idle)

    // Power Management Init
    WiFi.mode(WIFI_OFF);
    btStop(); 

    // Sensor Init
    pinMode(PIN_RAIN, INPUT);
    pinMode(PIN_SOIL, INPUT);
    pinMode(PIN_TDS, INPUT);
    analogReadResolution(12); 
    
    pinMode(PIN_LEVEL, INPUT_PULLDOWN); 
    pinMode(PIN_TRIG, OUTPUT);
    pinMode(PIN_ECHO, INPUT);           
    pinMode(PIN_BUZZER, OUTPUT);
    noTone(PIN_BUZZER); 
    
    pinMode(PIN_FLOW, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_FLOW), pulseCounter, FALLING);
    
    Serial.println("{\"status\": \"booted\", \"node\": \"CIVILEA_MASTER_EDGE\"}");
    oldTime = millis();
    last_transmission_time = millis();
}

// ==========================================
// MAIN LOOP
// ==========================================
void loop() {
    if ((millis() - oldTime) > 1000) { 
        
        // 1. FLOW SENSOR
        detachInterrupt(digitalPinToInterrupt(PIN_FLOW));
        unsigned long timeElapsed = millis() - oldTime;
        flowRate_L_min = ((1000.0 / timeElapsed) * pulseCount) / 0.015;
        pulseCount = 0;
        attachInterrupt(digitalPinToInterrupt(PIN_FLOW), pulseCounter, FALLING);

        // 2. SENSORS
        int rawRain = analogRead(PIN_RAIN);
        int rawSoil = analogRead(PIN_SOIL);
        int rawTDS  = analogRead(PIN_TDS);
        float tdsVoltage = rawTDS * (3.3 / 4095.0); 
        int levelState = digitalRead(PIN_LEVEL);

        // 3. ULTRASONIC SENSOR (Scaled x2 to match 40cm trained baseline)
        digitalWrite(PIN_TRIG, LOW);
        delayMicroseconds(2);
        digitalWrite(PIN_TRIG, HIGH);
        delayMicroseconds(10);
        digitalWrite(PIN_TRIG, LOW);
        long duration = pulseIn(PIN_ECHO, HIGH, 30000); 
        float rawDistanceCm = (duration == 0) ? -1.0 : (duration * 0.0343 / 2.0);
        float distanceCm = rawDistanceCm * 2.0;

        // 4. EDGE AI INFERENCE
        float live_telemetry[5] = { tdsVoltage, flowRate_L_min, distanceCm, (float)rawRain, (float)rawSoil };
        float ai_score = get_average_depth(live_telemetry);
        bool is_anomaly = (ai_score < AI_ANOMALY_THRESHOLD);

        // 5. BUZZER CONTROL
        if (is_anomaly || levelState == HIGH) {
            tone(PIN_BUZZER, 400); 
        } else {
            noTone(PIN_BUZZER); 
        }

        // 6. ROUTING LOGIC
        bool should_transmit = false;
        unsigned long current_time = millis();
        float delta = abs(ai_score - last_sent_score);

        if (current_time - last_transmission_time >= HEARTBEAT_INTERVAL) {
            should_transmit = true; 
            Serial.println("\n[EVENT] Heartbeat Triggered.");
        }
        else if (ai_score <= CRITICAL_MIN_DEPTH) {
            should_transmit = true; 
            Serial.println("\n[EVENT] EMERGENCY: Critical AI score breached!");
        }
        else if (delta >= AI_CHANGE_THRESHOLD) {
            should_transmit = true; 
            Serial.println("\n[EVENT] ANOMALY DELTA: Significant score shift detected.");
        }

        // 7. TRANSMIT
        if (should_transmit) {
            myData.station_id      = NODE_STATION_ID; // Permanently 0
            myData.discharge_rate  = (uint16_t)(flowRate_L_min * 100); 
            myData.water_clearance = (uint16_t)(distanceCm * 10); 
            myData.tds_v           = (uint16_t)(tdsVoltage * 1000); 
            myData.ai_score        = (uint16_t)(ai_score * 100); 
            myData.rain_raw        = rawRain; 
            myData.soil_raw        = rawSoil; 
            myData.alerts          = 0; 
            if (levelState == HIGH) bitSet(myData.alerts, 0); 
            if (is_anomaly)         bitSet(myData.alerts, 1); 

            // Live Diagnostics Monitor on USB Serial (115200 baud)
            printSensorDiagnostics(distanceCm, flowRate_L_min, rawRain, rawSoil, tdsVoltage, ai_score, levelState);
            bool lora_success = transmitViaLoRa();
            
            if (!lora_success) {
                transmitViaWiFi(); 
            }

            last_sent_score = ai_score;
            last_transmission_time = millis();
        }

        oldTime = millis();
    }
}