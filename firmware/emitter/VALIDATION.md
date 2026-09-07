# Emitter development validation — 2026-09-08

Target: documented ESP32-C3 Super Mini, `esp32:esp32:esp32c3:CDCOnBoot=cdc`.
The BOM records −39 dBm WiFi reception. Its missing PSRAM is a limitation for
the handheld audio design, not a requirement of the small-command IR emitter.
No C3-specific hardware failure was found in the inspected project notes.

- Final firmware compile/link: PASS, ESP32 Arduino core 3.3.11, IRremote 4.7.1,
  PubSubClient 2.8, ArduinoJson 7.4.3, WiFiManager 2.0.17.
- Program: 1,191,701 / 1,310,720 bytes (90% of selected app partition).
- Static globals: 39,224 bytes; runtime TLS/WiFi heap use must be measured on
  hardware. The linker's remaining-memory figure is not a runtime measurement.
- Backend suite: 78 passed. Targeted emitter suite: 21 passed. Tests cover
  cross-thread ACK delivery, late ACKs, cancellation cleanup, failed publish,
  disconnect handling, numeric limits and MQTT packet overhead.
- Direct test tool dry-runs: TV volume_up and STB channel_up produce valid
  catalog commands through the same serializer as the backend.
- Compiled staged sketch matches current emitter.ino. Placeholder credentials
  were used; no board was flashed. Reproduce with check_build.ps1.

Live MQTT and IR were not tested. This checkout has no backend/.env or emitter
secrets.h. Provision matching broker credentials and the broker issuing root
CA, then run the documented test_emitter.py --execute test. COM3 was detected
only as a generic ESP32 USB device and was not assumed to be the emitter.

Remaining catalog tasks: recapture STB digit 1 and configure channel numbers.
Recent-command deduplication is RAM-only (last eight IDs, five minutes) and
does not provide exactly-once delivery across resets. An ACK confirms command
acceptance, not appliance response. Fake-emitter testing does not establish IR
timing, driver current or coverage. Do not run a fake and physical emitter on
the same production topics.
