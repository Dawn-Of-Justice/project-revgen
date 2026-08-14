/*
 * RevGen board self-test — bring-up steps 1 and 2
 * -----------------------------------------------
 * Flash this to any new board before wiring anything to it. Answers the three
 * questions that otherwise get debugged much later, in a much worse mood:
 *
 *   Does the board work at all, and is serial configured correctly?
 *   Does it really have PSRAM, and can it hold a recording?
 *   Is the WiFi radio good from where this device will actually live?
 *
 * WIRING: none. USB only.
 *
 * ARDUINO IDE SETTINGS THAT MATTER
 *
 *   XIAO ESP32S3        Tools > Board        "XIAO_ESP32S3"
 *                       Tools > PSRAM        "OPI PSRAM"      <-- MUST be set
 *                       Tools > USB CDC On Boot  "Enabled"    <-- or no serial
 *
 *   ESP32-C3 SuperMini  Tools > Board        "ESP32C3 Dev Module"
 *                       Tools > USB CDC On Boot  "Enabled"
 *
 * PSRAM is DISABLED BY DEFAULT in the IDE. With it off, a board that has 8MB
 * reports zero -- indistinguishable from a board that has none. If this prints
 * 0 bytes on a XIAO ESP32S3, fix the Tools menu before believing it.
 */

#include <WiFi.h>

// 6 seconds of 16kHz mono 16-bit audio -- the buffer the voice unit must hold,
// and the entire reason this project needs PSRAM. v1 died streaming audio over
// a WebSocket because the classic ESP32 could not keep a recording in memory.
static const size_t RECORDING_BYTES = 6 * 16000 * 2;   // 192,000

void setup() {
  Serial.begin(115200);
  delay(1500);                       // USB CDC needs a moment to enumerate

  Serial.println("\n=========== RevGen board self-test ===========\n");

  // --- identity ------------------------------------------------------
  Serial.printf("Chip      : %s rev %d, %d core(s) @ %d MHz\n",
                ESP.getChipModel(), ESP.getChipRevision(),
                ESP.getChipCores(), getCpuFrequencyMhz());
  Serial.printf("Flash     : %u MB\n", ESP.getFlashChipSize() / (1024 * 1024));
  Serial.printf("Heap free : %u bytes\n", ESP.getFreeHeap());

  // --- PSRAM ---------------------------------------------------------
  size_t psram = ESP.getPsramSize();
  Serial.printf("PSRAM     : %u bytes", psram);

  if (psram == 0) {
    Serial.println("   <-- NONE DETECTED");
    Serial.println("\n  If this is a XIAO ESP32S3, PSRAM is present but not");
    Serial.println("  enabled. Set Tools > PSRAM to \"OPI PSRAM\" and re-flash.");
    Serial.println("  If it stays 0, the board genuinely has none and cannot");
    Serial.println("  serve as the voice unit.");
  } else {
    Serial.printf("  (%u MB)\n", psram / (1024 * 1024));

    // Reporting a size is not the same as being able to use it.
    uint8_t *buf = (uint8_t *)ps_malloc(RECORDING_BYTES);
    if (!buf) {
      Serial.println("  !! ps_malloc failed -- PSRAM reported but unusable");
    } else {
      for (size_t i = 0; i < RECORDING_BYTES; i += 4096) buf[i] = (uint8_t)i;
      bool ok = true;
      for (size_t i = 0; i < RECORDING_BYTES; i += 4096)
        if (buf[i] != (uint8_t)i) { ok = false; break; }
      free(buf);
      Serial.printf("  allocated and verified %u bytes = 6s of 16kHz mono: %s\n",
                    RECORDING_BYTES, ok ? "OK" : "FAILED");
      Serial.printf("  PSRAM free after release: %u bytes\n", ESP.getFreePsram());
    }
  }

  // --- radio ---------------------------------------------------------
  Serial.println("\nScanning WiFi ...");
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  int n = WiFi.scanNetworks();
  if (n <= 0) {
    Serial.println("  no networks found");
    Serial.println("  On a XIAO, check the little IPEX antenna is plugged in --");
    Serial.println("  it ships loose in the box and range is poor without it.");
  } else {
    Serial.printf("  %d networks\n", n);
    for (int i = 0; i < n && i < 8; i++) {
      int rssi = WiFi.RSSI(i);
      const char *verdict = rssi > -70 ? "good"
                          : rssi > -80 ? "marginal"
                                       : "too weak";
      Serial.printf("    %-28s %4d dBm  %s\n", WiFi.SSID(i).c_str(), rssi, verdict);
    }
    Serial.println("\n  Run this again from where the device will actually sit.");
    Serial.println("  Below about -70 dBm you get intermittent MQTT drops that");
    Serial.println("  look like random failures months later.");
  }

  Serial.println("\n=============== self-test done ===============\n");
}

void loop() {
  delay(10000);
  Serial.printf("alive, heap %u, psram %u\n", ESP.getFreeHeap(), ESP.getFreePsram());
}
