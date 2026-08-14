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
#include <driver/rtc_io.h>
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
/*
 * 6s cap, matching what the architecture assumed all along (192KB).
 *
 * This is the upload size lever, and upload dominates the round trip. It also
 * bounds the Saaras bill, which is charged per second of audio. She is issuing
 * one short command, not dictating -- anything longer than this is a stuck
 * button or a conversation the device should not be sending anyway.
 */
static const uint32_t MAX_RECORD_MS    = 6000;
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

/*
 * Playback loudness.
 *
 * BEEP_VOLUME is a fraction of full scale for the local tones.
 *
 * The spoken reply is normalised instead of scaled by a fixed amount: the
 * buffer is scanned for its loudest sample and the whole clip lifted so that
 * peak lands at PLAYBACK_PEAK. Bulbul does not guarantee a consistent level
 * between phrases, and a fixed multiplier would either clip the loud ones or
 * leave the quiet ones inaudible. This way every confirmation comes out at the
 * same volume, which is what she actually needs.
 *
 * MAX_NORMALISE_GAIN stops a near-silent clip being amplified into a wall of
 * hiss -- past about 8x you are boosting the noise floor, not the voice.
 */
static const float BEEP_VOLUME        = 0.85f;
/*
 * 27000 rather than something closer to 32767, deliberately.
 *
 * Normalising to the very top means any sample that rounds up clips, and a
 * handful of clipped peaks per second is heard as a blurred, harsh voice rather
 * than as obvious distortion. A little headroom sounds noticeably cleaner and
 * costs about 1.5dB of loudness, which the amplifier's GAIN pin gives back for
 * free.
 */
static const int   PLAYBACK_PEAK      = 27000;   // out of 32767
static const float MAX_NORMALISE_GAIN = 8.0f;

static const uint32_t OTA_HOLD_MS     = 3000;              // hold button at boot
static const uint32_t OTA_WINDOW_MS   = 5UL * 60UL * 1000UL;

static const size_t RECORD_CAPACITY =
    (size_t)SAMPLE_RATE * 2 * (MAX_RECORD_MS / 1000);      // 16-bit mono

// ---------------------------------------------------------------- state

static int16_t  *recording   = nullptr;   // PSRAM
static size_t    recordedLen = 0;         // bytes

/*
 * Survives deep sleep. Ordinary RAM does not.
 *
 * A cold WiFi connect scans every channel for the SSID and then runs DHCP --
 * about 1.3s, every single press. Remembering the exact channel, the access
 * point's BSSID and the IP we were given last time turns that into a directed
 * association with no scan and no DHCP, which is typically under 400ms.
 *
 * All of it is a cache, never a source of truth: anything stale just fails and
 * falls back to the slow path, which then refreshes it.
 */
RTC_DATA_ATTR static char     rtcSsid[33]  = {0};
RTC_DATA_ATTR static char     rtcPsk[65]   = {0};
RTC_DATA_ATTR static uint8_t  rtcBssid[6]  = {0};
RTC_DATA_ATTR static int32_t  rtcChannel   = 0;
RTC_DATA_ATTR static uint32_t rtcIp        = 0;
RTC_DATA_ATTR static uint32_t rtcGw        = 0;
RTC_DATA_ATTR static uint32_t rtcMask      = 0;
RTC_DATA_ATTR static uint32_t rtcDns       = 0;
RTC_DATA_ATTR static bool     rtcValid     = false;
RTC_DATA_ATTR static uint8_t  rtcFailures  = 0;

/*
 * Set by the button interrupt when she presses during an upload, then read on
 * the next boot. See the interrupt handler for why a reboot is the mechanism.
 */
RTC_DATA_ATTR static bool     rtcRestartToRecord = false;

// ---------------------------------------------------------------- cancel

/*
 * "She changed her mind" detection.
 *
 * Everything after the recording -- upload, download, playback -- can take ten
 * seconds, and making her sit through all of it after a misspoken command is
 * the kind of thing that makes a device feel broken. A second press abandons
 * the current attempt and starts a new recording.
 *
 * It cannot un-fire IR: if the backend already published, the television has
 * already reacted. This skips the *wait*, not the action. The backend's power
 * debounce is what stops the resulting second command undoing the first.
 *
 * Edge-triggered, because the press that ENDS the recording is still physically
 * down when the upload starts and would otherwise instantly cancel itself.
 */
static bool cancelArmed = false;

static void armCancel() {
  cancelArmed = false;                       // must see the button go up first
}

static bool cancelRequested() {
  if (digitalRead(BUTTON_PIN) == HIGH) { cancelArmed = true; return false; }
  if (!cancelArmed) return false;            // still held from last time
  delay(25);                                 // cheap debounce
  return digitalRead(BUTTON_PIN) == LOW;
}

/*
 * Plain ints rather than an enum, deliberately.
 *
 * The Arduino IDE auto-generates prototypes for every function in the .ino and
 * inserts them near the top of the file -- above anything declared later. A
 * function returning `SendResult` therefore gets a prototype that mentions a
 * type the compiler has not seen yet: "'SendResult' does not name a type".
 * Builtin types have no such problem.
 */
static const int SEND_OK        = 0;
static const int SEND_FAILED    = 1;
static const int SEND_CANCELLED = 2;

/*
 * The upload itself cannot be interrupted from this task.
 *
 * HTTPClient::POST blocks for the whole request -- about seven seconds for a
 * four second recording -- and there is no callback to poll the button from.
 * Splitting the network onto its own FreeRTOS task would work, but it means
 * shared state, careful teardown and a half-open TLS session to clean up.
 *
 * Rebooting is simpler and, for this device, free. Nothing is worth preserving
 * mid-upload: the recording is being abandoned by definition, and the WiFi
 * cache lives in RTC memory which survives a restart. Boot to recording is
 * ~300ms, faster than the wait it replaces.
 *
 * The interrupt is only attached around the blocking call, so playback keeps
 * the graceful chunked cancel instead of restarting.
 */
static void IRAM_ATTR onButtonDuringUpload() {
  rtcRestartToRecord = true;
  esp_restart();
}

static void watchButtonDuringUpload(bool on) {
  if (on) attachInterrupt(digitalPinToInterrupt(BUTTON_PIN),
                          onButtonDuringUpload, FALLING);
  else    detachInterrupt(digitalPinToInterrupt(BUTTON_PIN));
}

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
static void beep(int freq, int ms, float volume = BEEP_VOLUME) {
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

  /*
   * Silence the DMA buffer, or the tone never actually stops.
   *
   * Once i2s_write stops feeding it, the peripheral underruns and keeps
   * clocking out whatever samples are still in the buffer -- looping the tail
   * of the beep indefinitely. It is audible right through the recording, and
   * worse, the microphone picks it up: a steady tone laid over every utterance
   * sent to Saaras.
   */
  i2s_zero_dma_buffer(I2S_AMP);
}

static void beepListening() { beep(880, 90); }

/*
 * Deliberately quieter and shorter than the others: a tick, not an
 * announcement.
 *
 * Its only job is to mark the boundary between "listening" and "working on it",
 * so the ten-second wait that follows does not feel like nothing happened. She
 * already knows she let go of the button, so it does not need to be loud enough
 * to compete with the confirmation that follows.
 */
static void beepHeard()     { beep(1320, 40, 0.30f); }
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
 * Push-to-talk, with a fallback.
 *
 * If she is holding the button, record until she lets go -- that is the
 * walkie-talkie model, it is unambiguous, and she is in control of the end.
 * A short tail after release catches the last syllable, which people routinely
 * clip by letting go as they finish the word.
 *
 * If the button is already up when we get here -- a quick tap, which is what a
 * short press looks like after ~300ms of boot -- fall back to stopping on
 * silence so a tap-and-speak still works.
 *
 * Either way MAX_RECORD_MS is the ceiling, because a stuck button should not
 * upload six seconds of an empty room every time it is nudged.
 */
static const uint32_t RELEASE_TAIL_MS = 300;

static void record() {
  const int  CHUNK = 256;
  int32_t    raw[CHUNK];
  size_t     bytesRead;

  recordedLen = 0;
  uint32_t started       = millis();
  uint32_t lastLoudAt    = millis();
  uint32_t releasedAt    = 0;
  bool     heardAnything = false;
  bool     wasHeld       = digitalRead(BUTTON_PIN) == LOW;

  // Belt and braces: make sure the amplifier is silent before we start
  // listening, so nothing of ours ends up in her recording.
  i2s_zero_dma_buffer(I2S_AMP);

  Serial.printf("recording... (%s)\n",
                wasHeld ? "hold to talk, release to send"
                        : "tap detected, will stop on silence");

  while (true) {
    uint32_t elapsed = millis() - started;
    if (elapsed > MAX_RECORD_MS) { Serial.println("  hit the time cap"); break; }

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

    if (wasHeld) {
      // Held: she decides when it ends.
      if (buttonUp) {
        if (!releasedAt) releasedAt = millis();
        if (millis() - releasedAt > RELEASE_TAIL_MS) {
          Serial.println("  button released");
          break;
        }
      } else {
        releasedAt = 0;             // re-pressed; ignore the blip
      }
    } else {
      // Tapped: stop when she stops talking.
      if (elapsed > MIN_RECORD_MS && heardAnything &&
          millis() - lastLoudAt > SILENCE_MS) {
        Serial.println("  went quiet");
        break;
      }
      if (!heardAnything && elapsed > 2500) {
        Serial.println("  nothing said");
        break;
      }
    }
  }

  Serial.printf("recorded %u bytes (%.1fs), speech=%s\n",
                (unsigned)recordedLen, recordedLen / 32000.0f,
                heardAnything ? "yes" : "no");
}

// ---------------------------------------------------------------- wav

/*
 * Find the actual audio inside a WAV.
 *
 * A minimal WAV puts samples at byte 44, and assuming that is a very easy bug
 * to write. Real encoders insert LIST/INFO/fact chunks between `fmt ` and
 * `data`, so a hardcoded 44 lands mid-header: the amplifier is then fed header
 * bytes and the real samples are never played. Silence, with everything else
 * apparently correct.
 *
 * Walks the chunk list instead. Returns false if this is not a WAV at all.
 */
static bool findWavData(const uint8_t *buf, size_t len,
                        size_t *dataOffset, size_t *dataLen,
                        uint32_t *rate, uint16_t *channels, uint16_t *bits) {
  if (len < 12 || memcmp(buf, "RIFF", 4) || memcmp(buf + 8, "WAVE", 4)) return false;

  *rate = 16000; *channels = 1; *bits = 16;   // sane defaults if fmt is missing
  size_t pos = 12;

  while (pos + 8 <= len) {
    char id[5] = {0};
    memcpy(id, buf + pos, 4);
    uint32_t size;
    memcpy(&size, buf + pos + 4, 4);
    size_t body = pos + 8;

    if (!memcmp(id, "fmt ", 4) && body + 16 <= len) {
      memcpy(channels, buf + body + 2,  2);
      memcpy(rate,     buf + body + 4,  4);
      memcpy(bits,     buf + body + 14, 2);
    } else if (!memcmp(id, "data", 4)) {
      *dataOffset = body;
      // Trust the smaller of the declared size and what actually arrived: a
      // truncated download should play what we have, not read past the buffer.
      *dataLen = min((size_t)size, len - body);
      return true;
    }

    pos = body + size + (size & 1);          // chunks are word-aligned
  }
  return false;
}

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
static int sendAndPlay() {
  if (recordedLen == 0) return SEND_FAILED;

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
  if (!body) { Serial.println("ps_malloc failed for request body"); return SEND_FAILED; }

  memcpy(body, head, headLen);
  writeWavHeader(body + headLen, recordedLen, SAMPLE_RATE);
  memcpy(body + headLen + 44, recording, recordedLen);
  memcpy(body + headLen + wavLen, tail, tailLen);

  Serial.printf("uploading %u bytes (%.1fs audio), heap %u\n",
                (unsigned)bodyLen, recordedLen / 32000.0f, ESP.getFreeHeap());

  WiFiClientSecure net;
  // Not certificate-pinned: a pinned cert that expires means a dead device in
  // someone else's house. The token in the header is what actually authorises.
  net.setInsecure();
  // No setBufferSizes() here -- that is an ESP8266/BearSSL API. ESP32 uses
  // mbedTLS with fixed buffers, so the way to reduce pressure during a large
  // upload is to send less: see MAX_RECORD_MS.
  net.setTimeout(30);                 // seconds, socket level

  HTTPClient http;
  http.setTimeout(30000);             // ms
  http.setConnectTimeout(10000);
  http.setReuse(false);
  if (!http.begin(net, BACKEND_URL)) {
    Serial.println("http.begin failed");
    free(body);
    return SEND_FAILED;
  }

  http.addHeader("Content-Type", String("multipart/form-data; boundary=") + BOUNDARY);
  if (strlen(DEVICE_TOKEN)) http.addHeader("X-RevGen-Token", DEVICE_TOKEN);

  // HTTPClient discards response headers unless asked for them by name, so
  // header() would otherwise always come back empty.
  static const char *WANTED[] = { "X-RevGen-Outcome", "X-RevGen-Elapsed-Ms" };
  http.collectHeaders(WANTED, 2);

  /*
   * Only arm the interrupt once the button has actually been released --
   * otherwise the press that ended the recording is still down and reboots us
   * instantly, forever.
   */
  uint32_t waited = millis();
  while (digitalRead(BUTTON_PIN) == LOW && millis() - waited < 2000) delay(10);
  bool guarded = digitalRead(BUTTON_PIN) == HIGH;
  if (guarded) watchButtonDuringUpload(true);

  uint32_t t0 = millis();
  int code = http.POST(body, bodyLen);
  uint32_t took = millis() - t0;

  if (guarded) watchButtonDuringUpload(false);
  free(body);

  // Negative codes are client-side failures, not HTTP statuses:
  //   -1 connection refused   -2 send header failed   -3 send payload failed
  //   -4 not connected        -5 connection lost      -11 read timeout
  Serial.printf("POST -> %d in %lums (%s)\n", code, took,
                code > 0 ? "server responded"
                         : "client-side failure, request never completed");
  if (code < 0) Serial.printf("  %s\n", HTTPClient::errorToString(code).c_str());

  Serial.printf("  outcome=%s (server %sms)\n",
                http.header("X-RevGen-Outcome").c_str(),
                http.header("X-RevGen-Elapsed-Ms").c_str());

  if (code != 200) { http.end(); return SEND_FAILED; }

  // getSize() is -1 when the server uses chunked transfer encoding, which is
  // not an error -- it just means the length is unknown up front. Allocate a
  // generous buffer and read until the stream ends.
  int len = http.getSize();
  size_t capacity = (len > 0) ? (size_t)len : 512 * 1024;
  Serial.printf("  content-length=%d, reading into %uKB\n", len, (unsigned)(capacity / 1024));

  uint8_t *reply = (uint8_t *)ps_malloc(capacity);
  if (!reply) { Serial.println("  ps_malloc failed for reply"); http.end(); return SEND_FAILED; }

  // `auto` because this is WiFiClient* on core 2.x and NetworkClient* on 3.x.
  auto *stream = http.getStreamPtr();
  size_t got = 0;
  uint32_t lastData = millis();
  while (got < capacity) {
    // Interruptible: she should not have to sit through a download she has
    // already decided against.
    if (cancelRequested()) {
      Serial.println("  cancelled during download");
      http.end();
      free(reply);
      return SEND_CANCELLED;
    }

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
    return SEND_FAILED;
  }

  size_t   dataOffset = 0, dataLen = 0;
  uint32_t rate = SAMPLE_RATE;
  uint16_t channels = 1, bits = 16;

  if (!findWavData(reply, got, &dataOffset, &dataLen, &rate, &channels, &bits)) {
    Serial.println("  reply is not a WAV I can parse");
    free(reply);
    return SEND_FAILED;
  }

  Serial.printf("  wav: %luHz %uch %ubit, %u bytes of audio at offset %u (%.1fs)\n",
                (unsigned long)rate, channels, bits,
                (unsigned)dataLen, (unsigned)dataOffset,
                dataLen / (float)(rate * channels * (bits / 8)));

  if (bits != 16 || channels != 1) {
    // The I2S output is configured for 16-bit mono. Anything else would play
    // as noise, which is worse than saying nothing.
    Serial.println("  unexpected format, refusing to play noise");
    free(reply);
    return SEND_FAILED;
  }

  if (rate < 8000 || rate > 48000) rate = SAMPLE_RATE;

  /*
   * Normalise to a consistent, loud level before playing.
   *
   * Done in place in PSRAM -- the buffer is discarded straight afterwards, so
   * there is nothing to preserve, and a second copy of 100KB would be wasteful
   * for no benefit.
   */
  {
    int16_t *samples = (int16_t *)(reply + dataOffset);
    size_t   count   = dataLen / sizeof(int16_t);
    int      peak    = 1;

    for (size_t i = 0; i < count; i++) {
      int a = abs(samples[i]);
      if (a > peak) peak = a;
    }

    float gain = (float)PLAYBACK_PEAK / peak;
    if (gain > MAX_NORMALISE_GAIN) gain = MAX_NORMALISE_GAIN;   // do not amplify hiss
    if (gain < 1.0f)               gain = 1.0f;                 // never quieten

    if (gain > 1.01f) {
      for (size_t i = 0; i < count; i++) {
        int v = (int)(samples[i] * gain);
        samples[i] = v > 32767 ? 32767 : (v < -32768 ? -32768 : v);
      }
    }
    Serial.printf("  peak %d -> gain %.2fx\n", peak, gain);
  }

  ampRate(rate);

  /*
   * Played in chunks rather than one blocking write, so a second press can stop
   * it. A single i2s_write of three seconds of audio cannot be interrupted, and
   * three seconds of a confirmation she no longer wants is exactly the wait
   * that makes a device feel unresponsive.
   */
  const size_t CHUNK = 2048;
  size_t sent = 0, written = 0;
  bool cancelled = false;

  while (sent < dataLen) {
    if (cancelRequested()) { cancelled = true; break; }
    size_t n = min(CHUNK, dataLen - sent);
    i2s_write(I2S_AMP, reply + dataOffset + sent, n, &written, portMAX_DELAY);
    sent += written;
  }

  if (cancelled) {
    i2s_zero_dma_buffer(I2S_AMP);      // stop mid-word rather than trailing off
    Serial.printf("  cancelled during playback (%u of %u bytes)\n",
                  (unsigned)sent, (unsigned)dataLen);
  } else {
    Serial.printf("  played %u of %u bytes\n", (unsigned)sent, (unsigned)dataLen);
    delay(150);                        // let the DMA drain or the last word clips
  }

  ampRate(SAMPLE_RATE);
  free(reply);
  return cancelled ? SEND_CANCELLED : SEND_OK;
}

// ---------------------------------------------------------------- wifi

// Remember everything needed to skip the scan and DHCP next time.
static void cacheConnection() {
  strncpy(rtcSsid, WiFi.SSID().c_str(), sizeof(rtcSsid) - 1);
  strncpy(rtcPsk,  WiFi.psk().c_str(),  sizeof(rtcPsk) - 1);
  memcpy(rtcBssid, WiFi.BSSID(), 6);
  rtcChannel = WiFi.channel();
  rtcIp   = (uint32_t)WiFi.localIP();
  rtcGw   = (uint32_t)WiFi.gatewayIP();
  rtcMask = (uint32_t)WiFi.subnetMask();
  rtcDns  = (uint32_t)WiFi.dnsIP();
  rtcValid = rtcSsid[0] && rtcChannel > 0;
  rtcFailures = 0;
}

/*
 * Directed reconnect: exact channel, exact access point, static IP taken from
 * the address the router already leased us. No scan, no DHCP.
 *
 * Returns false on anything unexpected so the caller can fall back to the full
 * WiFiManager path -- a moved router, a new channel after a reboot, or a lease
 * that expired all land here, and all of them fix themselves on the next
 * successful slow connect.
 */
static uint32_t wifiStartedAt = 0;

/*
 * Non-blocking. Kicked off BEFORE recording so the radio associates while she
 * is still talking -- roughly 400ms of connect time hidden entirely underneath
 * two seconds of speech, for free.
 */
static void wifiKickoff() {
  wifiStartedAt = millis();

  if (!rtcValid) return;                 // nothing cached; the slow path runs later

  // Three consecutive failures means the cache is wrong, not unlucky.
  if (rtcFailures >= 3) {
    Serial.println("wifi cache failed repeatedly, discarding");
    rtcValid = false;
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  if (rtcIp) WiFi.config(IPAddress(rtcIp), IPAddress(rtcGw),
                         IPAddress(rtcMask), IPAddress(rtcDns));
  WiFi.begin(rtcSsid, rtcPsk, rtcChannel, rtcBssid);
  Serial.printf("wifi: associating on ch %d (cached)\n", (int)rtcChannel);
}

// Called after recording, by which time it has usually already connected.
static bool wifiReady(uint32_t timeoutMs) {
  if (rtcValid) {
    while (WiFi.status() != WL_CONNECTED && millis() - wifiStartedAt < timeoutMs) delay(10);
    if (WiFi.status() == WL_CONNECTED) {
      rtcFailures = 0;
      Serial.printf("wifi %s in %lums (cached)\n",
                    WiFi.localIP().toString().c_str(), millis() - wifiStartedAt);
      return true;
    }
    rtcFailures++;
    Serial.printf("cached connect failed (%u), falling back\n", rtcFailures);
    WiFi.disconnect(true);
  }

  // Slow path: full scan, DHCP, and the captive portal if there are no
  // credentials at all. Also refreshes the cache for next time.
  WiFiManager wm;
  wm.setConfigPortalTimeout(180);
  wm.setConnectTimeout(15);
  if (!wm.autoConnect("RevGen-Setup")) return false;

  cacheConnection();
  Serial.printf("wifi %s (full connect, cached for next time)\n",
                WiFi.localIP().toString().c_str());
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
  micStop();
  ampStop();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  digitalWrite(LED_PIN, HIGH);        // off (active low)

  // Wait for the button to come up, or we arm on a press that is still
  // happening and wake again the instant we sleep.
  uint32_t waited = millis();
  while (digitalRead(BUTTON_PIN) == LOW && millis() - waited < 5000) delay(20);
  delay(80);                          // contact bounce

  /*
   * THE PULLUP MUST BE RE-ARMED IN THE RTC DOMAIN.
   *
   * pinMode(INPUT_PULLUP) configures the ordinary GPIO peripheral, and that is
   * powered down during deep sleep. The pin then floats, drifts low, ext0
   * fires, and the device wakes itself over and over -- recording and
   * uploading every few seconds. On a metered STT API that spends real money,
   * and on battery it would be flat by morning.
   *
   * Only the RTC pullup survives deep sleep.
   */
  rtc_gpio_pullup_en((gpio_num_t)BUTTON_PIN);
  rtc_gpio_pulldown_dis((gpio_num_t)BUTTON_PIN);
  esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);   // wake on LOW

  Serial.println("sleeping\n");
  Serial.flush();
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

  /*
   * A reboot triggered by pressing the button mid-upload. Treat it exactly like
   * a button wake: she wants to say something new, and the fastest route back
   * to a microphone is to pretend the last cycle never happened.
   */
  if (rtcRestartToRecord) {
    rtcRestartToRecord = false;
    wokenByButton = true;
    Serial.println("restarted mid-upload -- she pressed again, listening now");
  } else {
    Serial.printf("wake cause: %d (%s)\n", (int)cause,
                  wokenByButton ? "button" : "power-on / reset");
  }

  if (!wokenByButton) {
    /*
     * Cold boot. Chirp and sleep armed -- unless you are standing here holding
     * the button down, which is how you reach the WiFi portal and OTA.
     */
    if (digitalRead(BUTTON_PIN) == HIGH) {
      beepArmed();

      /*
       * If a host has the USB serial port open, someone is at a laptop -- stay
       * awake long enough to be re-flashed.
       *
       * Without this, a cold boot sleeps within a second and the USB device
       * disappears with it, so the only way back in is the BOOT+RESET dance.
       * That is fine once; it is miserable while iterating. On battery in her
       * living room nothing has the port open, so this costs her nothing.
       */
      if (Serial) {
        Serial.println("cold boot with USB attached -- staying awake 15s for flashing");
        uint32_t until = millis() + 15000;
        while (millis() < until) {
          digitalWrite(LED_PIN, (millis() / 250) % 2);   // fast blink = flashable
          if (digitalRead(BUTTON_PIN) == LOW) break;     // impatient: carry on
          delay(10);
        }
        digitalWrite(LED_PIN, HIGH);
      }

      Serial.println("cold boot, nothing to do -- arming and sleeping");
      sleepNow();
    }
    Serial.println("cold boot with button held -- maintenance");

    wifiKickoff();
    if (!wifiReady(30000)) { beepFailed(); sleepNow(); }
    maintenanceMode();
    sleepNow();
  }

  /*
   * Woken by the button, so record immediately -- no second press, and no
   * waiting for the network first.
   *
   * There is no "is the button still down?" check here. Boot takes ~300ms and
   * a normal press is shorter than that, so requiring it to still be held
   * meant every quick press was dismissed as spurious and she had to press
   * twice. The floating-pin problem that check was guarding against is fixed
   * properly at the source, by the RTC pullup in sleepNow().
   */
  // Non-blocking: the radio associates while she is talking, so ~400ms of
  // connect time disappears underneath the recording instead of preceding it.
  wifiKickoff();

  /*
   * One session per press, but a second press restarts it rather than being
   * ignored. Without this she is locked out for the ten seconds it takes to
   * upload, download and play -- and if she misspoke, that wait is the whole
   * experience of the device being wrong.
   */
  while (true) {
    beepListening();                  // instant: she knows it is listening
    digitalWrite(LED_PIN, LOW);       // on

    micStart();
    record();
    micStop();

    beepHeard();                      // instant: "got it, working on it"
    armCancel();                      // the press that just ended recording
                                      // must not count as a cancel

    if (recordedLen < (size_t)(SAMPLE_RATE * 2 * 0.4f)) {
      Serial.println("too short, ignoring");
      break;
    }

    // By now this has almost always already finished in the background.
    if (!wifiReady(15000)) {
      Serial.println("no wifi");
      beepFailed();
      break;
    }

    int r = sendAndPlay();

    if (r == SEND_CANCELLED) {
      Serial.println("cancelled -- listening again\n");
      continue;                       // straight back to recording
    }

    // Every failure path makes a sound. Silence is indistinguishable from a
    // dead device, and that is the moment she stops using it.
    if (r == SEND_FAILED) beepFailed();
    break;
  }

  sleepNow();
}

void loop() { }   // never runs; setup() always ends in deep sleep
