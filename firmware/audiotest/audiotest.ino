/*
 * Speaker bring-up — deliberately identical to the code that already works
 * -----------------------------------------------------------------------
 * The rising three-note chirp you hear when the handheld enters maintenance
 * mode proves the amp, wiring and speaker are fine. This sketch plays that
 * exact sequence, using the exact same I2S setup and the exact same amplitude,
 * and nothing else.
 *
 * Nothing touches the SD pin. Nothing touches GPIO4 (the button). No WiFi, no
 * recording, no sleep.
 *
 * If STAGE 1 is silent here but the maintenance chirp is audible from
 * remote.ino, the difference is not in the audio path and we look elsewhere.
 * If STAGE 1 plays, we add volume and duration back one step at a time and
 * find where it stops.
 *
 * WIRING (XIAO ESP32S3)
 *   MAX98357A  BCLK -> GPIO1 (D0)
 *              LRC  -> GPIO2 (D1)
 *              DIN  -> GPIO3 (D2)
 *              VIN  -> 5V        (not 3V3, not BAT+)
 *              GND  -> GND
 *              +/-  -> speaker   (both to the amp, neither to GND)
 *
 * Board: XIAO_ESP32S3, USB CDC On Boot enabled. Serial 115200.
 */

#include <driver/i2s.h>

#define AMP_BCLK  1
#define AMP_LRC   2
#define AMP_DIN   3

#define I2S_AMP   I2S_NUM_1

static const int SAMPLE_RATE = 16000;

// Byte-for-byte the same as remote.ino::ampStart()
static void ampStart() {
  i2s_config_t cfg = {};
  cfg.mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate          = SAMPLE_RATE;
  cfg.bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count        = 8;
  cfg.dma_buf_len          = 256;
  cfg.use_apll             = false;

  i2s_pin_config_t pins = {};
  pins.bck_io_num   = AMP_BCLK;
  pins.ws_io_num    = AMP_LRC;
  pins.data_out_num = AMP_DIN;
  pins.data_in_num  = I2S_PIN_NO_CHANGE;

  esp_err_t a = i2s_driver_install(I2S_AMP, &cfg, 0, NULL);
  esp_err_t b = i2s_set_pin(I2S_AMP, &pins);
  Serial.printf("i2s install=%s  set_pin=%s\n", esp_err_to_name(a), esp_err_to_name(b));
}

// Byte-for-byte the same as remote.ino::beep(), including the default volume.
static void playTone(int freq, int ms, float volume = 0.35f) {
  const int  total = SAMPLE_RATE * ms / 1000;
  const int  chunk = 256;
  int16_t    buf[chunk];
  size_t     written;

  for (int done = 0; done < total; done += chunk) {
    int n = min(chunk, total - done);
    for (int i = 0; i < n; i++) {
      float t = (float)(done + i) / SAMPLE_RATE;
      float env = 1.0f;
      int remaining = total - (done + i);
      if (remaining < SAMPLE_RATE / 125) env = (float)remaining / (SAMPLE_RATE / 125);
      buf[i] = (int16_t)(sinf(2.0f * PI * freq * t) * 32767.0f * volume * env);
    }
    i2s_write(I2S_AMP, buf, n * sizeof(int16_t), &written, portMAX_DELAY);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("\n===== speaker bring-up =====");
  ampStart();
  Serial.println();
}

void loop() {
  // STAGE 1 -- the maintenance chirp, exactly as remote.ino plays it.
  Serial.println("STAGE 1: maintenance chirp (660/880/1100Hz @ 0.35) <- known to work");
  playTone(660, 80);  delay(80);
  playTone(880, 80);  delay(80);
  playTone(1100, 120);
  delay(1200);

  // STAGE 2 -- same volume, but held long enough to be unmistakable.
  Serial.println("STAGE 2: 880Hz for 1s @ 0.35");
  playTone(880, 1000);
  delay(1200);

  // STAGE 3 -- near full scale. If 1 and 2 were inaudible and this is not,
  // the amp works and the earlier levels were simply too quiet for the speaker.
  Serial.println("STAGE 3: 880Hz for 1s @ 0.95  <- loud");
  playTone(880, 1000, 0.95f);

  Serial.println();
  Serial.println("  which stages did you hear?");
  Serial.println("    all three      -> audio path is fine");
  Serial.println("    only stage 3   -> works, but everything else is too quiet");
  Serial.println("    none           -> wiring differs from when the chirp played");
  Serial.println();
  delay(2500);
}
