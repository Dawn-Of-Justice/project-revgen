// RevGen emitter B3: receive-only protocol identification, ESP32 GPIO15.
// Library: IRremoteESP8266 2.9.0. Serial monitor: 115200 baud.
// All library-default decoders enabled, including AC protocols.
#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRac.h>
#include <IRutils.h>

constexpr uint16_t kReceiverPin = 15;
constexpr uint16_t kEmitterPin = 4;
constexpr uint16_t kBufferSize = 2048;
constexpr uint8_t kFrameTimeoutMs = 50;
IRrecv receiver(kReceiverPin, kBufferSize, kFrameTimeoutMs, true);
decode_results result;

void setup() {
  pinMode(kEmitterPin, OUTPUT);
  digitalWrite(kEmitterPin, LOW);
  Serial.begin(115200);
  delay(300);
  receiver.setUnknownThreshold(12);
  receiver.enableIRIn();
  Serial.println("RevGen IR protocol scanner; receiver GPIO15; library "
                 _IRREMOTEESP8266_VERSION_STR);
  Serial.println("Briefly press a remote button, then wait 2 seconds.");
  Serial.println("AC capture timeout: 50ms. UNKNOWN still includes raw timings.");
  Serial.println("Receive only: no Wi-Fi, learning webpage, MQTT, or IR transmission.");
}

void loop() {
  if (receiver.decode(&result)) {
    Serial.printf("\n--- Capture at %lu ms ---\n", (unsigned long)millis());
    if (result.overflow)
      Serial.println("WARNING: capture buffer overflow; frame is incomplete.");
    Serial.print(resultToHumanReadableBasic(&result));
    String description = IRAcUtils::resultAcToString(&result);
    if (description.length()) Serial.println("AC state: " + description);
    if (result.decode_type == UNKNOWN)
      Serial.println("Unknown protocol or noise; compare multiple captures.");
    yield();
    Serial.println(resultToSourceCode(&result));
    Serial.println("--- End capture ---");
    yield();
  }
  delay(1);
}
