# Emitter development validation — 2026-09-08

## Production voice request to physical emitter: PASS

A Windows-generated English recording, "Increase the TV volume", was uploaded
to `https://project-revgen.fly.dev/command` with the configured device token.
Production returned HTTP 200, `X-RevGen-Outcome: tv.volume_up`, server processing
2531 ms and total request time 3812 ms. COM8 captured:

```text
ack 3bb1ba80-0ff7-4142-878b-40d631191bf8 ok=1
executing 3bb1ba80-0ff7-4142-878b-40d631191bf8 (1 steps)
  panasonic addr=0x8 cmd=0x20
done
```

The spoken reply was a valid mono PCM16 WAV, 24000 Hz, 33536 frames. This
establishes production speech processing, command delivery, device execution,
and returned audio. It does not establish Malayalam recognition accuracy,
handheld playback or physical appliance response. The input was synthetic;
no external IR components were connected during this run.

The local backend now requests 32000 Hz because MAX98357A does not support
24000 Hz LRCLK. Cache keys include synthesis settings and offline mode;
generated and cached WAVs are checked for mono PCM16 at the configured rate.
Offline tests now produce valid silence WAVs. Backend suite: 92 passed.
This audio fix is NOT deployed: no Fly CLI/login is available on this PC.

## Backend-to-emitter execution confirmed on serial

A TV volume-up command sent through the backend MQTT client received a matching
positive ACK. COM8 simultaneously logged the same command ID, execution of one
Panasonic step (`addr=0x8 cmd=0x20`), and `done`. This establishes actual device
receipt and completion of its IR-send routine, beyond the MQTT ACK alone.
Command ID: `a4a1a1aa-497b-48f1-adf9-4dcb4956526c`.

Backend-to-emitter command delivery/execution is PASS. The board had no external
IR circuit connected during this run; physical IR output and current appliance
response were not measured. The published command came from the local backend
MQTT client using the configured broker, not a new request to production's
voice `/command` endpoint.

## Prior hardware test confirmed by user

The user reports previously controlling the TV through this IR driver circuit
using serial-monitor triggers. Treat that tested circuit/TV combination as
user-verified; do not require repeating basic driver bring-up as a prerequisite
for software integration. Exact coverage, every catalog button and STB codes
are not established by that report.

The backend MQTT client subsequently sent one Panasonic TV volume-up command
(address 8, command 32) and received a positive acceptance ACK from the flashed
emitter. The current board has no external components connected, so this run
verified network delivery and firmware acceptance, not a new physical TV
response. Full voice-to-appliance testing awaits reconnecting the circuit.

## WiFi setup completed: live integration verified

After the user configured WiFi, `backend/tools/check_emitter.py --probe`
confirmed broker connection, emitter online status, and an ACK for a zero-delay
command. This exercises the real firmware command parser and MQTT return path
without firing IR. The deployed backend `/health` also returned `ok: true`,
`emitter_online: true`, `offline_mode: false`. Physical appliance response and
IR coverage are still untested. Production reported zero configured channels.
This completes the WiFi/ACK checks marked pending in the initial upload notes
below. The locally modified backend code has not been redeployed.

## Current physical board and upload

The user corrected the connected hardware after the earlier C3 build. USB
identification reads **ESP32-D0WD-V3, revision 3.1**, 40 MHz crystal, 4 MB
flash, CP2104 bridge, COM8. The signed Silicon Labs driver was installed to
resolve Windows device error 28. This classic ESP32 is the current emitter.

Configured build: ESP32 Arduino core 3.3.11, `esp32:esp32:esp32`, 4 MB flash,
PSRAM disabled. Program is 1,142,081 / 1,310,720 bytes (87%); static globals
50,116 bytes. The staged credentials match ignored secrets.h. Upload of
bootloader, partitions and application completed with esptool hash verification.
Serial boot confirmed the correct chip and GPIO4 IR output, with 276,880 bytes
free heap before network setup.

A complete 4 MB pre-upload flash backup is retained locally at
`build/board-backup/com8-before-emitter-20260908.bin`. It is ignored by Git and
may contain the board's old configuration; do not distribute it.

The supplied MQTT credentials authenticate from the backend client. Broker TLS
hostname/chain validation passed; the firmware trusts ISRG Root X1. No IR was
emitted during testing. The physical board could not connect to its previously
saved WiFi and opened **RevGen-Emitter**, so the live acknowledgement probe
remains pending WiFi setup. Connect to that AP and open `http://192.168.4.1`.
The portal times out after 180 seconds and restarts; use reset if necessary.

The supplied remote credentials are saved in firmware/remote/secrets.h; MQTT
credentials and the device token are also in backend/.env. All three real
configuration files are confirmed ignored by Git. The earlier statements below
about missing credentials/no flashing describe the initial C3 validation only.

## Earlier C3 compilation and backend tests

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

## Learning implementation — 2026-09-08

This section records the new local build, separately from historical checks above.
Classic ESP32 compilation passes: 1,168,059 / 1,310,720 bytes of application flash
(89%); static RAM 51,956 / 327,680 bytes (15%). The source includes parity-error
rejection. Backend suite: 115 passed; one dependency deprecation warning.
The headless browser test passes for capture gating, test/save capture versions,
channel mapping, upload-state presentation, session-token use and safe name rendering.

This learning build has not been flashed. Its backend changes have not been
deployed. Live receiver capture, physical replay, MQTT learning-topic ACLs and
restart persistence across actual devices remain to be tested. See
`docs/EMITTER_LEARNING.md` for the setup and rollout checklist.
