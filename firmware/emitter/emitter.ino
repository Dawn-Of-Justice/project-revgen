/*
 * RevGen IR emitter
 * -----------------
 * Sits on the TV cabinet, mains powered, and fires IR when the backend tells
 * it to. It also learns named IR commands during a physically enabled setup
 * session; language understanding stays on the backend.
 *
 * The backend sends complete IR descriptors, so adding her air conditioner
 * later means editing config/commands.json on the server -- not reflashing a
 * board in someone else's house. That is the whole reason this is dumb.
 *
 *   subscribe  revgen/emitter/cmd     {"id":"...","steps":[...]}
 *   publish    revgen/emitter/ack     {"id":"...","ok":true}
 *   publish    revgen/emitter/status  "online" / "offline" (LWT, retained)
 *
 * A step is one of:
 *   {"type":"ir","protocol":"panasonic","address":8,"command":61,"repeat":0}
 *   {"type":"ir","protocol":"nec_raw","raw":2791701215,"repeat":0}
 *   {"type":"delay","ms":2500}
 *
 * LIBRARIES (Arduino Library Manager)
 *   IRremote        >= 4.3   Armin Joachimsmeyer
 *   PubSubClient    >= 2.8   Nick O'Leary
 *   ArduinoJson     >= 7.0   Benoit Blanchon
 *   WiFiManager     >= 2.0   tzapu
 *
 * BOARD: ESP32C3 Dev Module, USB CDC On Boot enabled
 *
 * WIRING
 *   B2 carrier: GPIO4 -> 220R -> AO3400A gate; 10k gate-to-source pull-down.
 *   4x IR LED (940nm) in parallel, EACH with its own 100R resistor, from 5V
 *   to the drain. MOSFET source to GND. Button GPIO27, receiver OUT GPIO15.
 *   Do not share one resistor across the LEDs -- they do not current-share and
 *   one ends up doing all the work.
 *   Fan them across roughly 90 degrees so aiming is designed out of the system.
 *   She cannot be relied on to point anything, which is why this box is
 *   stationary and she holds a microphone instead.
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <WiFiManager.h>
#include <IRremote.hpp>

// ---------------------------------------------------------------- config

/*
 * Pins differ by board. The emitter needs almost nothing -- WiFi, one output
 * for the IR driver, one for a status LED -- so any ESP32 variant works.
 * A C3 Super Mini is a fine choice and cheaper than a DevKit v1.
 */
#if CONFIG_IDF_TARGET_ESP32C3
  #define IR_SEND_PIN      4
  #define STATUS_LED_PIN   8      // onboard LED on most C3 Super Mini boards
  #define STATUS_LED_ACTIVE_LOW 1 // ...and it is wired active-low
#else
  #define IR_SEND_PIN      4
  #define STATUS_LED_PIN   2      // onboard LED on classic ESP32 DevKit v1
  #define STATUS_LED_ACTIVE_LOW 0
#endif

/*
 * Credentials live in secrets.h, which is gitignored. This repo is public.
 *
 *     cp secrets.example.h secrets.h     and fill it in
 *
 * Broker configuration and its issuing root CA are deployment-specific.
 */
#include "secrets.h"

static const char *MQTT_HOST = MQTT_HOST_STR;
static const int   MQTT_PORT = MQTT_PORT_NUM;
static const char *MQTT_USER = MQTT_USER_STR;
static const char *MQTT_PASS = MQTT_PASS_STR;
static const bool  MQTT_TLS  = MQTT_TLS_ON;

static const char *TOPIC_CMD    = "revgen/emitter/cmd";
static const char *TOPIC_ACK    = "revgen/emitter/ack";
static const char *TOPIC_STATUS = "revgen/emitter/status";

static const size_t   MAX_STEPS    = 24;
static const uint32_t MAX_DELAY_MS = 10000;
static const uint8_t MAX_REPEAT = 10;
static const uint32_t DEDUP_MS = 5UL * 60UL * 1000UL;

// If the broker is unreachable this long, reboot. The failure being guarded
// against is a wedged network stack, not a broker outage -- and a reboot fixes
// one of those. Cheaper than driving over to power-cycle it.
static const uint32_t REBOOT_AFTER_OFFLINE_MS = 10UL * 60UL * 1000UL;

// ---------------------------------------------------------------- state

WiFiClientSecure secureClient;
WiFiClient       plainClient;
PubSubClient     mqtt;

struct Step {
  bool     isDelay;
  uint32_t delayMs;
  bool     isPanasonic;   // false -> NEC raw
  uint16_t address;
  uint8_t  command;
  uint32_t raw;
  uint8_t  repeat;
};

static Step   pending[MAX_STEPS];
static size_t pendingCount = 0;
static char   pendingId[48] = {0};
static bool   hasPending = false;
static char recentIds[8][48] = {};
static uint32_t recentAt[8] = {};
static size_t recentNext = 0;

static bool alreadyAccepted(const char *id) {
  for (size_t i = 0; i < 8; i++) {
    if (recentIds[i][0] && millis() - recentAt[i] < DEDUP_MS &&
        strcmp(recentIds[i], id) == 0) return true;
  }
  return false;
}

static uint32_t lastConnectedAt = 0;

// ---------------------------------------------------------------- helpers

static void led(bool on) {
#if STATUS_LED_ACTIVE_LOW
  digitalWrite(STATUS_LED_PIN, on ? LOW : HIGH);
#else
  digitalWrite(STATUS_LED_PIN, on ? HIGH : LOW);
#endif
}

static void publishAck(const char *id, bool ok, const char *error) {
  JsonDocument doc;
  doc["id"] = id;
  doc["ok"] = ok;
  if (error) doc["error"] = error;

  char buf[192];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(TOPIC_ACK, (const uint8_t *)buf, n, false);

  Serial.printf("ack %s ok=%d%s%s\n", id, ok, error ? " error=" : "",
                error ? error : "");
}

// Validate the WHOLE sequence before touching the IR LED. Refusing is always
// safer than half-executing: firing three of five steps leaves the television
// in a state nobody asked for and she has no way to undo it.
static bool parseSteps(JsonArray steps, const char **errorOut) {
  pendingCount = 0;

  for (JsonVariant value : steps) {
    if (!value.is<JsonObject>()) { *errorOut = "invalid step"; return false; }
    JsonObject step = value.as<JsonObject>();
    if (pendingCount >= MAX_STEPS) { *errorOut = "too many steps"; return false; }

    const char *type = step["type"] | "";
    Step &s = pending[pendingCount];

    if (strcmp(type, "delay") == 0) {
      if (!step["ms"].is<uint32_t>() || step["ms"].as<uint32_t>() > MAX_DELAY_MS) {
        *errorOut = "invalid delay"; return false;
      }
      uint32_t ms = step["ms"].as<uint32_t>();
      s.isDelay = true;
      s.delayMs = ms;
      pendingCount++;
      continue;
    }

    if (strcmp(type, "ir") != 0) { *errorOut = "unknown step type"; return false; }

    const char *protocol = step["protocol"] | "";
    s.isDelay = false;
    if (!step["repeat"].isUnbound() &&
        (!step["repeat"].is<uint32_t>() || step["repeat"].as<uint32_t>() > MAX_REPEAT)) {
      *errorOut = "invalid repeat"; return false;
    }
    s.repeat = step["repeat"] | 0;

    if (strcmp(protocol, "panasonic") == 0) {
      if (!step["address"].is<uint32_t>() || step["address"].as<uint32_t>() > 0xFFF ||
          !step["command"].is<uint32_t>() || step["command"].as<uint32_t>() > 0xFF) {
        *errorOut = "invalid panasonic fields";
        return false;
      }
      s.isPanasonic = true;
      s.address = step["address"].as<uint16_t>();
      s.command = (uint8_t)step["command"].as<uint16_t>();
    } else if (strcmp(protocol, "nec_raw") == 0) {
      if (!step["raw"].is<uint32_t>()) { *errorOut = "invalid raw"; return false; }
      s.isPanasonic = false;
      s.raw = step["raw"].as<uint32_t>();
    } else {
      // Refuse rather than guess. The wrong protocol at her television is
      // worse than doing nothing at all.
      *errorOut = "unsupported protocol";
      return false;
    }

    pendingCount++;
  }

  if (pendingCount == 0) { *errorOut = "empty sequence"; return false; }
  return true;
}

static void executePending() {
  Serial.printf("executing %s (%u steps)\n", pendingId, (unsigned)pendingCount);
  led(true);

  for (size_t i = 0; i < pendingCount; i++) {
    const Step &s = pending[i];

    if (s.isDelay) {
      // Keep servicing MQTT while waiting. A 2.5s post-power gap would
      // otherwise starve the keepalive and the broker drops us mid-sequence.
      uint32_t until = millis() + s.delayMs;
      while ((int32_t)(until - millis()) > 0) {
        mqtt.loop();
        delay(10);
      }
      continue;
    }

    if (s.isPanasonic) {
      IrSender.sendPanasonic(s.address, s.command, s.repeat);
      Serial.printf("  panasonic addr=0x%X cmd=0x%X\n", s.address, s.command);
    } else {
      IrSender.sendNECRaw(s.raw, s.repeat);
      Serial.printf("  nec_raw 0x%08lX\n", (unsigned long)s.raw);
    }
    delay(60);   // inter-frame gap so the receiver sees separate presses
  }

  led(false);
  Serial.println("done");
}

// ---------------------------------------------------------------- mqtt

#include "learning.h"

static void onMessage(char *topic, byte *payload, unsigned int length) {
  if (strcmp(topic, TOPIC_LEARN_ACK) == 0) { learningAck(payload, length); return; }
  if (strcmp(topic, TOPIC_CMD) != 0) return;

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.printf("bad json: %s\n", err.c_str());
    return;
  }

  const char *id = doc["id"] | "";
  if (!id[0] || strlen(id) >= sizeof(pendingId) ||
      doc["id"].as<JsonString>().size() != strlen(id)) {
    Serial.println("invalid command id"); return;
  }
  // QoS1 may redeliver a command after its ACK was lost. Never repeat a
  // recently accepted power toggle merely because transport retried it.
  if (alreadyAccepted(id)) { publishAck(id, true, nullptr); return; }
  if (learningActive) { publishAck(id, false, "learning mode active"); return; }
  if (hasPending) { publishAck(id, false, "busy"); return; }
  strncpy(pendingId, id, sizeof(pendingId) - 1);
  pendingId[sizeof(pendingId) - 1] = '\0';

  JsonArray steps = doc["steps"].as<JsonArray>();
  if (steps.isNull()) { publishAck(pendingId, false, "no steps"); return; }

  const char *error = nullptr;
  if (!parseSteps(steps, &error)) {
    publishAck(pendingId, false, error);
    return;
  }

  /*
   * Ack now, execute afterwards.
   *
   * The ack means "received, understood, about to execute" -- not "the
   * television reacted". It cannot mean the latter: IR is open loop, so even
   * after firing we have no idea whether anything received it. Validating the
   * whole sequence first is what makes this honest rather than optimistic.
   *
   * It also keeps us inside the backend's 2.5s ack timeout. A sequence
   * containing a 2.5s post-power wait takes longer than that to run, and she
   * would otherwise be told it failed while it was still working.
   */
  hasPending = true;
  strcpy(recentIds[recentNext], pendingId);
  recentAt[recentNext] = millis();
  recentNext = (recentNext + 1) % 8;
  publishAck(pendingId, true, nullptr);
}

static void connectMqtt() {
  if (mqtt.connected()) return;

  Serial.printf("mqtt connecting to %s:%d ... ", MQTT_HOST, MQTT_PORT);

  char clientId[32];
  snprintf(clientId, sizeof(clientId), "revgen-emitter-%06lX",
           (unsigned long)(ESP.getEfuseMac() & 0xFFFFFF));

  // Last Will: if we drop off, the broker publishes "offline" on our behalf,
  // so the backend can tell her the box is unreachable instead of confirming a
  // command that went nowhere.
  bool ok = mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                         TOPIC_STATUS, 1, true, "offline");

  if (!ok) {
    Serial.printf("failed rc=%d\n", mqtt.state());
    return;
  }

  Serial.println("connected");
  if (!mqtt.subscribe(TOPIC_CMD, 1) || !mqtt.subscribe(TOPIC_LEARN_ACK, 1) ||
      !mqtt.publish(TOPIC_STATUS, "online", true)) {
    mqtt.disconnect();
    Serial.println("MQTT startup publish/subscribe failed");
    return;
  }
  lastConnectedAt = millis();

  for (int i = 0; i < 3; i++) { led(true); delay(80); led(false); delay(80); }
}

// ---------------------------------------------------------------- setup

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nRevGen emitter");
  Serial.printf("chip=%s flash=%u heap=%u IR GPIO=%d\n", ESP.getChipModel(),
                ESP.getFlashChipSize(), ESP.getFreeHeap(), IR_SEND_PIN);

  pinMode(STATUS_LED_PIN, OUTPUT);
  led(false);

  pinMode(IR_SEND_PIN, OUTPUT);
  digitalWrite(IR_SEND_PIN, LOW);
  IrSender.begin(IR_SEND_PIN);
  digitalWrite(IR_SEND_PIN, LOW);

  // Captive portal rather than hardcoded credentials. A hardcoded SSID means
  // one router change bricks the device and someone has to drive over.
  WiFiManager wm;
  wm.setConfigPortalTimeout(180);
  if (!wm.autoConnect("RevGen-Emitter")) {
    Serial.println("wifi portal timed out, restarting");
    ESP.restart();
  }
  Serial.printf("wifi ok, ip=%s\n", WiFi.localIP().toString().c_str());

  if (MQTT_TLS) {
    // Trust the broker's issuing root CA, not a short-lived leaf certificate.
    // Credentials must not be sent over an unauthenticated TLS connection.
    if (!MQTT_CA_CERT[0]) {
      Serial.println("Set MQTT_CA_CERT in secrets.h before using TLS");
      while (true) delay(1000);
    }
    configTime(0, 0, "pool.ntp.org", "time.google.com");
    secureClient.setCACert(MQTT_CA_CERT);
    mqtt.setClient(secureClient);
  } else {
    mqtt.setClient(plainClient);
  }

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  // PubSubClient defaults to a 256-byte buffer and SILENTLY DROPS anything
  // larger. Channel digits and multi-step volume exceed that easily. This one
  // line is the most common way this integration appears to work and does not.
  if (!mqtt.setBufferSize(2048)) {
    Serial.println("MQTT buffer allocation failed");
    ESP.restart();
  }
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(2);
  learningSetup();

  lastConnectedAt = millis();
}

void loop() {
  learningLoop();
  if (mqtt.connected() && WiFi.status() == WL_CONNECTED) lastConnectedAt = millis();
  if (!learningActive && millis() - lastConnectedAt > REBOOT_AFTER_OFFLINE_MS) {
    Serial.println("network offline too long, restarting");
    ESP.restart();
  }
  if (WiFi.status() != WL_CONNECTED) {
    if (!learningActive) led(millis() % 500 < 250);      // fast blink: no wifi
    delay(50);
    return;
  }

  if (!mqtt.connected()) {
    static uint32_t lastAttempt = 0;
    if (millis() - lastAttempt > 3000) {
      lastAttempt = millis();
      connectMqtt();
    }
    if (!learningActive && millis() - lastConnectedAt > REBOOT_AFTER_OFFLINE_MS) {
      Serial.println("offline too long, restarting");
      ESP.restart();
    }
    if (!learningActive) led(millis() % 1000 < 100);     // slow pulse: wifi ok, no broker
    delay(20);
    return;
  }

  mqtt.loop();

  if (hasPending) {
    executePending();
    hasPending = false;
  }

  delay(10);
}
