#include <Arduino.h>
#include <lmic.h>
#include <hal/hal.h>
#include <SPI.h>

#define STATUS_LED 13
#define PAYLOAD_SIZE 14

// --- ThingPark Credentials ---
// APPEUI / JoinEUI: Little-Endian (LSB reversed)
static const u1_t PROGMEM APPEUI[8] = { 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22 };
void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8); }

// DEVEUI: Little-Endian (LSB reversed)
static const u1_t PROGMEM DEVEUI[8] = { 0x44, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x44 };
void os_getDevEui (u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }

// APPKEY: Big-Endian (MSB)
static const u1_t PROGMEM APPKEY[16] = { 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22 };
void os_getDevKey (u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

// Pin mapping matching Send_otaa.ino
const lmic_pinmap lmic_pins = {
    .nss = 8,
    .rxtx = LMIC_UNUSED_PIN,
    .rst = 4,
    .dio = {7, 5, LMIC_UNUSED_PIN},
};

static uint8_t loraPayload[PAYLOAD_SIZE];
static osjob_t sendjob;
static bool networkJoined = false;
static bool hasNewData = false;

void onEvent (ev_t ev) {
    switch(ev) {
        case EV_JOINING:
            Serial.println(F("[LMIC] Joining network..."));
            break;
        case EV_JOINED:
            Serial.println(F("[LMIC] Successfully JOINED network!"));
            networkJoined = true;
            LMIC_setLinkCheckMode(0);
            break;
        case EV_JOIN_FAILED:
            Serial.println(F("[LMIC] Join failed"));
            break;
        case EV_TXCOMPLETE:
            Serial.println(F("[LMIC] Uplink complete"));
            digitalWrite(STATUS_LED, LOW);
            break;
        default:
            break;
    }
}

void do_send(osjob_t* j) {
    if (LMIC.opmode & OP_TXRXPEND) {
        Serial.println(F("[LMIC] Radio busy, packet waiting"));
    } else {
        // Queue unconfirmed uplink on port 1
        LMIC_setTxData2(1, loraPayload, PAYLOAD_SIZE, 0);
        digitalWrite(STATUS_LED, HIGH);
        Serial.println(F("[LMIC] Payload queued to radio"));
        hasNewData = false;
    }
}

void setup() {
    Serial.begin(115200);   // USB Monitor
    Serial1.begin(9600);    // UART to ESP32 (Pins 0 & 1)

    pinMode(STATUS_LED, OUTPUT);

    // Visual Boot Check: Blink 3 times to prove code started
    for (int i = 0; i < 3; i++) {
        digitalWrite(STATUS_LED, HIGH); delay(100);
        digitalWrite(STATUS_LED, LOW);  delay(100);
    }

    // Initialize LMIC radio stack
    os_init();
    LMIC_reset();
    LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100);

    Serial.println(F("[SYS] LoRa card ready. Listening for ESP32..."));
}

void loop() {
    // Keep LMIC scheduler running
    os_runloop_once();

    // Check for incoming data from ESP32
    if (Serial1.available() >= PAYLOAD_SIZE) {
        for (int i = 0; i < PAYLOAD_SIZE; i++) {
            loraPayload[i] = Serial1.read();
        }

        // Flush any trailing noise
        while (Serial1.available()) {
            Serial1.read();
        }

        delay(15);

        // Send ACK back to ESP32
        Serial1.print("ACK");
        Serial1.flush();

        Serial.println(F("[UART] 14 bytes received, ACK sent"));
        hasNewData = true;

        // Transmit via LoRaWAN (starts OTAA join automatically if not joined)
        do_send(&sendjob);
    }
}