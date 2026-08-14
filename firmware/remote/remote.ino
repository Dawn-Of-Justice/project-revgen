/*
 * RevGen handheld — the thing she actually holds
 * ----------------------------------------------
 * Press button, speak, hear a Malayalam confirmation. That is the entire user
 * interface. There is nothing else to press.
 *
 *   wake on button
 *     -> beep          "I'm listening"        (local, instant)
 *     -> record to PSRAM, stop on silence
 *     -> beep          "got it"               (local, instant)
 *     -> POST the WAV to the backend
 *     -> play the reply                       (Malayalam, from the backend)
 *     -> deep sleep
 *
 * WHY TWO LOCAL BEEPS
 *   Measured round trip is ~3s and upload dominates, so no amount of backend
 *   work gets the spoken reply under about a second. The question she actually
 *   has is "did it hear me?", and a beep answers that at zero latency. Without
 *   it she repeats herself, and a repeated "TV on" toggles the television back
 *   off. The beeps are not decoration -- they are the fix for the single worst
 *   failure mode in the system.
 *
 * WHY RECORD-THEN-UPLOAD RATHER THAN STREAM
 *   v1 streamed audio to a websocket because the classic ESP32 could not hold a
 *   recording in memory, and drowned in hand-rolled base64 and heap
 *   fragmentation. With 8MB of PSRAM the buffer is trivial and the whole design
 *   collapses to: fill an array, POST it.
 *
 * WIRING: docs/WIRING.md
 * LIBRARIES: WiFiManager (tzapu). Everything else ships with the ESP32 core.
 *
 * IDE (XIAO ESP32S3)
 *   Board             XIAO_ESP32S3
 *   PSRAM             OPI PSRAM
 *   USB CDC On Boot   Enabled
 *   Partition Scheme  8M with spiffs (3MB APP/1.5MB SPIFFS)   <- keeps OTA
 *
 * TARGETS the legacy driver/i2s.h API, which is present in ESP32 core 2.x and
 * still present (deprecated) in 3.x. If your core has removed it, the migration
 * is to <ESP_I2S.h> and the I2SClass wrapper; the logic below is unchanged.
 *
 * NOT YET COMPILED OR RUN ON HARDWARE.
 */

#include <WiFi.h>
#include <WiFiManager.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoOTA.h>
#include <driver/i2s.h>
#include <esp_sleep.h>

#include "secrets.h"

// ---------------------------------------------------------------- pins

#define MIC_SCK      7
#define MIC_WS       8
#define MIC_SD       9

#define AMP_BCLK     1
#define AMP_LRC      2
#define AMP_DIN      3

#define BUTTON_PIN   4     // to GND, INPUT_PULLUP. RTC-capable, so it can wake us.
#define LED_PIN      21    // onboard, active low

#define I2S_MIC      I2S_NUM_0
#define I2S_AMP      I2S_NUM_1

// ---------------------------------------------------------------- tuning

static const int      SAMPLE_RATE      = 16000;   // Saaras works best here
static const uint32_t MAX_RECORD_MS    = 8000;    // hard cap; STT is billed per second
static const uint32_t MIN_RECORD_MS    = 700;     // ignore an accidental brush
static const uint32_t SILENCE_MS       = 1200;    // quiet for this long -> she has finished
static const int      SILENCE_LEVEL    = 900;     // mean |sample| below this counts as quiet

/*
 * INMP441 gives 24-bit data left-justified in a 32-bit frame, so the raw word
 * shifted right by 8 is the true sample and >>8 again would be plain 16-bit.
 * MIC_GAIN_BITS adds gain on top of that, with saturation.
 *
 * v1 used a bare `>> 8` and produced a 24-bit value crammed into an int16,
 * which wrapped around on anything above a whisper. That is why its audio was
 * unusable. Start at 2; raise if she records quiet, lower if loud speech
 * clips.
 */
static const int MIC_GAIN_BITS = 2;

static const uint32_t OTA_HOLD_MS     = 3000;              // hold button at boot
static const uint32_t OTA_WINDOW_MS   = 5UL * 60UL * 1000UL;

static const size_t RECORD_CAPACITY =
    (size_t)SAMPLE_RATE * 2 * (MAX_RECORD_MS / 1000);      // 16-bit mono

// ---------------------------------------------------------------- state

static int16_t  *recording   = nullptr;   // PSRAM
static size_t    recordedLen = 0;         // bytes

// ---------------------------------------------------------------- audio out

// Track install state: sleepNow() tears both down defensively, and the legacy
// driver logs a scary error if you uninstall a port that is already gone.
static bool micUp = false;
static bool ampUp = false;

static void ampStart() {
  if (ampUp) return;
  i2s_config_t cfg = {};
  cfg.mode                = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate         = SAMPLE_RATE;
  cfg.bits_per_sample     = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format      = I2S_CHANNEL_FMT_ONLY_LEFT;
  cfg.communication_format= I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags    = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count       = 8;
  cfg.dma_buf_len         = 256;
  cfg.use_apll            = false;

  i2s_pin_config_t pins = {};
  pins.bck_io_num   = AMP_BCLK;
  pins.ws_io_num    = AMP_LRC;
  pins.data_out_num = AMP_DIN;
  pins.data_in_num  = I2S_PIN_NO_CHANGE;

  i2s_driver_install(I2S_AMP, &cfg, 0, NULL);
  i2s_set_pin(I2S_AMP, &pins);
  ampUp = true;
}

static void ampStop() { if (ampUp) { i2s_driver_uninstall(I2S_AMP); ampUp = false; } }

static void ampRate(int rate) { i2s_set_sample_rates(I2S_AMP, rate); }

// A plain sine. Short, distinct, and impossible to mistake for speech.
static void beep(int freq, int ms, float volume = 0.35f) {
  const int  total = SAMPLE_RATE * ms / 1000;
  const int  chunk = 256;
  int16_t    buf[chunk];
  size_t     written;

  for (int done = 0; done < total; done += chunk) {
    int n = min(chunk, total - done);
    for (int i = 0; i < n; i++) {
      float t = (float)(done + i) / SAMPLE_RATE;
      // Fade the last 8ms so it stops without a click.
      float env = 1.0f;
      int remaining = total - (done + i);
      if (remaining < SAMPLE_RATE / 125) env = (float)remaining / (SAMPLE_RATE / 125);
      buf[i] = (int16_t)(sinf(2.0f * PI * freq * t) * 32767.0f * volume * env);
    }
    i2s_write(I2S_AMP, buf, n * sizeof(int16_t), &written, portMAX_DELAY);
  }
}

static void beepListening() { beep(880, 90); }
static void beepHeard()     { beep(1320, 70); }
static void beepFailed()    { beep(400, 140); delay(60); beep(300, 200); }
// Distinct from the others: two rising notes, heard only on a cold boot.
static void beepArmed()     { beep(660, 70); delay(50); beep(990, 110); }

// ---------------------------------------------------------------- audio in

static void micStart() {
  if (micUp) return;
  i2s_config_t cfg = {};
  cfg.mode                = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate         = SAMPLE_RATE;
  cfg.bits_per_sample     = I2S_BITS_PER_SAMPLE_32BIT;   // INMP441 is 32-bit frames
  cfg.channel_format      = I2S_CHANNEL_FMT_ONLY_LEFT;   // L/R pin tied to GND
  cfg.communication_format= I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags    = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count       = 8;
  cfg.dma_buf_len         = 256;
  cfg.use_apll            = false;

  i2s_pin_config_t pins = {};
  pins.bck_io_num   = MIC_SCK;
  pins.ws_io_num    = MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num  = MIC_SD;

  i2s_driver_install(I2S_MIC, &cfg, 0, NULL);
  i2s_set_pin(I2S_MIC, &pins);
  i2s_zero_dma_buffer(I2S_MIC);
  micUp = true;
}

static void micStop() { if (micUp) { i2s_driver_uninstall(I2S_MIC); micUp = false; } }

static inline int16_t convert(int32_t raw) {
  int32_t s = (raw >> 8) >> (8 - MIC_GAIN_BITS);   // 24-bit, then to 16 with gain
  if (s >  32767) s =  32767;                       // saturate rather than wrap
  if (s < -32768) s = -32768;
  return (int16_t)s;
}

/*
 * Records until she stops talking, the button is released, or the cap is hit --
 * whichever is latest for the first two. Holding the button longer works, and
 * so does tapping and speaking; both mental models are valid and she will use
 * whichever feels natural without being told.
 */
static void record() {
  const int  CHUNK = 256;
  int32_t    raw[CHUNK];
  size_t     bytesRead;

  recordedLen = 0;
  uint32_t started      = millis();
  uint32_t lastLoudAt   = millis();
  bool     heardAnything = false;

  while (true) {
    uint32_t elapsed = millis() - started;
    if (elapsed > MAX_RECORD_MS) break;

    if (i2s_read(I2S_MIC, raw, sizeof(raw), &bytesRead, pdMS_TO_TICKS(100)) != ESP_OK)
      continue;

    int samples = bytesRead / sizeof(int32_t);
    int64_t sum = 0;

    for (int i = 0; i < samples; i++) {
      if (recordedLen + sizeof(int16_t) > RECORD_CAPACITY) break;
      int16_t s = convert(raw[i]);
      recording[recordedLen / sizeof(int16_t)] = s;
      recordedLen += sizeof(int16_t);
      sum += abs(s);
    }

    int level = samples ? (int)(sum / samples) : 0;
    if (level > SILENCE_LEVEL) { lastLoudAt = millis(); heardAnything = true; }

    bool buttonUp = digitalRead(BUTTON_PIN) == HIGH;
    bool wentQuiet = heardAnything && (millis() - lastLoudAt > SILENCE_MS);

    if (elapsed > MIN_RECORD_MS && buttonUp && wentQuiet) break;

    // Nothing at all after a couple of seconds: she pressed it by accident.
    if (!heardAnything && elapsed > 2500 && buttonUp) break;
  }

  Serial.printf("recorded %u bytes (%.1fs), speech=%s\n",
                (unsigned)recordedLen, recordedLen / 32000.0f,
                heardAnything ? "yes" : "no");
}

// ---------------------------------------------------------------- wav

static void writeWavHeader(uint8_t *h, size_t dataLen, int rate) {
  const uint32_t byteRate = rate * 2;
  memcpy(h, "RIFF", 4);
  *(uint32_t *)(h + 4)  = 36 + dataLen;
  memcpy(h + 8, "WAVEfmt ", 8);
  *(uint32_t *)(h + 16) = 16;          // PCM chunk size
  *(uint16_t *)(h + 20) = 1;           // PCM
  *(uint16_t *)(h + 22) = 1;           // mono
  *(uint32_t *)(h + 24) = rate;
  *(uint32_t *)(h + 28) = byteRate;
  *(uint16_t *)(h + 32) = 2;           // block align
  *(uint16_t *)(h + 34) = 16;          // bits
  memcpy(h + 36, "data", 4);
  *(uint32_t *)(h + 40) = dataLen;
}

// ---------------------------------------------------------------- network

/*
 * Uploads the recording as multipart/form-data and plays whatever comes back.
 *
 * The body is assembled in PSRAM in one piece rather than streamed, because a
 * single contiguous buffer means HTTPClient can send it with a known
 * Content-Length and there is nothing to get wrong. Memory is the one thing
 * this board is not short of.
 */
static bool sendAndPlay() {
  if (recordedLen == 0) return false;

  static const char *BOUNDARY = "----revgenboundary";

  char head[256];
  int headLen = snprintf(head, sizeof(head),
      "--%s\r\n"
      "Content-Disposition: form-data; name=\"file\"; filename=\"command.wav\"\r\n"
      "Content-Type: audio/wav\r\n\r\n", BOUNDARY);

  char tail[64];
  int tailLen = snprintf(tail, sizeof(tail), "\r\n--%s--\r\n", BOUNDARY);

  const size_t wavLen  = 44 + recordedLen;
  const size_t bodyLen = headLen + wavLen + tailLen;

  uint8_t *body = (uint8_t *)ps_malloc(bodyLen);
  if (!body) { Serial.println("ps_malloc failed for request body"); return false; }

  memcpy(body, head, headLen);
  writeWavHeader(body + headLen, recordedLen, SAMPLE_RATE);
  memcpy(body + headLen + 44, recording, recordedLen);
  memcpy(body + headLen + wavLen, tail, tailLen);

  WiFiClientSecure net;
  // Not certificate-pinned: a pinned cert that expires means a dead device in
  // someone else's house. The token in the header is what actually authorises.
  net.setInsecure();

  HTTPClient http;
  http.setTimeout(20000);
  if (!http.begin(net, BACKEND_URL)) { free(body); return false; }

  http.addHeader("Content-Type", String("multipart/form-data; boundary=") + BOUNDARY);
  if (strlen(DEVICE_TOKEN)) http.addHeader("X-RevGen-Token", DEVICE_TOKEN);

  uint32_t t0 = millis();
  int code = http.POST(body, bodyLen);
  free(body);

  Serial.printf("POST -> %d in %lums\n", code, millis() - t0);

  Serial.printf("  outcome=%s\n", http.header("X-RevGen-Outcome").c_str());

  if (code != 200) { http.end(); return false; }

  // getSize() is -1 when the server uses chunked transfer encoding, which is
  // not an error -- it just means the length is unknown up front. Allocate a
  // generous buffer and read until the stream ends.
  int len = http.getSize();
  size_t capacity = (len > 0) ? (size_t)len : 512 * 1024;
  Serial.printf("  content-length=%d, reading into %uKB\n", len, (unsigned)(capacity / 1024));

  uint8_t *reply = (uint8_t *)ps_malloc(capacity);
  if (!reply) { Serial.println("  ps_malloc failed for reply"); http.end(); return false; }

  WiFiClient *stream = http.getStreamPtr();
  size_t got = 0;
  uint32_t lastData = millis();
  while (got < capacity) {
    size_t avail = stream->available();
    if (avail) {
      int n = stream->readBytes(reply + got, min(avail, capacity - got));
      if (n <= 0) break;
      got += n;
      lastData = millis();
    } else {
      if (!http.connected() && !stream->available()) break;
      if (millis() - lastData > 3000) break;      // stalled
      delay(5);
    }
    if (len > 0 && got >= (size_t)len) break;
  }
  http.end();

  Serial.printf("  received %u bytes of audio\n", (unsigned)got);

  if (got < 44) {
    Serial.println("  reply too short to be a WAV");
    free(reply);
    return false;
  }

  // Trust the reply's own header rather than assuming: the backend serves
  // cached Bulbul audio, and its rate is a server-side setting we do not
  // control from here.
  uint32_t rate = *(uint32_t *)(reply + 24);
  if (rate < 8000 || rate > 48000) rate = SAMPLE_RATE;

  ampRate(rate);
  size_t written;
  i2s_write(I2S_AMP, reply + 44, got - 44, &written, portMAX_DELAY);
  // Let the DMA drain before the driver is torn down or she hears a clipped word.
  delay(120);
  ampRate(SAMPLE_RATE);

  free(reply);
  return true;
}

// ---------------------------------------------------------------- ota

/*
 * Hold the button while the device wakes to stay awake for five minutes with
 * OTA listening. This exists because the device lives hours away: every other
 * part of the system was built so problems can be fixed without a car journey,
 * and firmware is no exception.
 */
static void maintenanceMode() {
  Serial.println("maintenance mode: OTA open for 5 minutes");

  ArduinoOTA.setHostname("revgen-remote");
  if (strlen(OTA_PASSWORD)) ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([]() { Serial.println("OTA start"); });
  ArduinoOTA.onEnd([]()   { Serial.println("OTA done"); });
  ArduinoOTA.onProgress([](unsigned p, unsigned t) {
    digitalWrite(LED_PIN, (p / (t / 100 + 1)) % 2);
  });
  ArduinoOTA.begin();

  Serial.printf("ready at %s\n", WiFi.localIP().toString().c_str());
  beep(660, 80); delay(80); beep(880, 80); delay(80); beep(1100, 120);

  uint32_t until = millis() + OTA_WINDOW_MS;
  while (millis() < until) {
    ArduinoOTA.handle();
    digitalWrite(LED_PIN, (millis() / 500) % 2);   // slow blink = maintenance
    delay(10);
  }
}

// ---------------------------------------------------------------- sleep

static void sleepNow() {
  Serial.println("sleeping\n");
  Serial.flush();

  digitalWrite(LED_PIN, HIGH);        // off (active low)
  micStop();
  ampStop();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);

  esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);   // wake on press
  esp_deep_sleep_start();
}

// ---------------------------------------------------------------- main

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  recording = (int16_t *)ps_malloc(RECORD_CAPACITY);
  if (!recording) {
    // Without PSRAM there is no point continuing -- this is the whole reason
    // the board was chosen. Fail visibly rather than behaving oddly.
    Serial.println("FATAL: no PSRAM. Check Tools > PSRAM = OPI PSRAM.");
    while (true) { digitalWrite(LED_PIN, !digitalRead(LED_PIN)); delay(120); }
  }

  ampStart();

  /*
   * Only record if the BUTTON woke us.
   *
   * setup() also runs on power-on, on reset, and after every flash. Recording
   * unconditionally means a power glitch or a reconnected battery uploads
   * whatever the room happens to be saying -- and once the emitter exists,
   * that could switch her television on or off with nobody in the room.
   *
   * On a cold boot: chirp to say "ready", then sleep armed. She gets useful
   * confirmation after charging, and the device does nothing until asked.
   */
  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  bool wokenByButton = (cause == ESP_SLEEP_WAKEUP_EXT0);

  Serial.printf("wake cause: %d (%s)\n", (int)cause,
                wokenByButton ? "button" : "power-on / reset");

  if (!wokenByButton) {
    // Except when you are standing here holding it down, which means you want
    // to configure or update it.
    if (digitalRead(BUTTON_PIN) == HIGH) {
      beepArmed();
      Serial.println("cold boot, nothing to do -- arming and sleeping");
      sleepNow();
    }
    Serial.println("cold boot with button held -- continuing");
  }

  beepListening();                    // instant: she knows it woke up
  digitalWrite(LED_PIN, LOW);         // on

  // Captive portal rather than hardcoded credentials: a router change should
  // not mean a drive over with a laptop.
  WiFiManager wm;
  wm.setConfigPortalTimeout(180);
  wm.setConnectTimeout(15);
  if (!wm.autoConnect("RevGen-Setup")) {
    Serial.println("no wifi");
    beepFailed();
    sleepNow();
  }

  // Still holding the button after connecting? She isn't; you are.
  uint32_t held = millis();
  while (digitalRead(BUTTON_PIN) == LOW && millis() - held < OTA_HOLD_MS) delay(10);
  if (digitalRead(BUTTON_PIN) == LOW) {
    maintenanceMode();
    sleepNow();
  }

  micStart();
  record();
  micStop();

  beepHeard();                        // instant: "got it, working on it"

  if (recordedLen < (size_t)(SAMPLE_RATE * 2 * 0.4f)) {
    Serial.println("too short, ignoring");
    sleepNow();
  }

  // Every failure path makes a sound. Silence is indistinguishable from a dead
  // device, and that is the moment she stops using it.
  if (!sendAndPlay()) beepFailed();

  sleepNow();
}

void loop() { }   // never runs; setup() always ends in deep sleep
