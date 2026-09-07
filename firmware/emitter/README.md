# IR emitter

Stationary box on the TV cabinet. Subscribes to MQTT, fires IR, acknowledges.
Holds no IR codes — the backend sends complete descriptors, so new devices are
a server-side JSON edit rather than a trip to reflash hardware.

## Current development target (2026-09-08)

**Hardware correction:** the newly connected board was read over USB as
ESP32-D0WD-V3 revision 3.1, 4 MB flash, via CP2104 on COM8. This classic ESP32
is the current emitter. Select **ESP32 Dev Module**, 4 MB flash, PSRAM disabled;
IR is GPIO4 and status LED GPIO2 if fitted. The C3 below is the earlier recorded
choice and remains a supported alternative. Its GPIO8/USB-CDC settings do not
apply to the classic board.

Build the current board with `./firmware/emitter/check_build.ps1 -Target classic`.
Add `-UseSecrets` to compile the ignored real credentials for uploading. The
default build uses placeholders only. `backend/tools/check_emitter.py --probe`
tests broker status and a zero-delay ACK without emitting any IR.

The recorded owned board is **ESP32-C3 Super Mini**, per `docs/BOM.md` and
`docs/WIRING.md`; the ESP32-WROOM-32 is a spare. The historical lack-of-PSRAM
issue concerns audio recording on the handheld. The emitter processes a 2 KB
MQTT packet and a fixed 24-step sequence, so it does not require PSRAM. The
recorded −39 dBm WiFi result establishes signal reception at that test location,
not sustained MQTT/TLS operation. No logged C3-specific hardware failure was
found in the project notes inspected during this pass.

Select **ESP32C3 Dev Module**, **USB CDC On Boot: Enabled**, GPIO4 for IR and
GPIO8 for the active-low onboard LED. GPIO4 controls the transistor; it must
not directly supply the LED bank. The driver and real appliance response still
need bench testing. Keep the transistor pinout check in `docs/WIRING.md`.

The emitter now rejects malformed numeric fields, reports `busy` for a new
command during execution, and remembers the last eight accepted IDs for five
minutes to prevent duplicate QoS1 delivery from firing twice. This memory is
lost on reboot. Never publish retained commands; a command ID must be unique
and its payload immutable. ACK still means accepted, not appliance confirmed.
The backend does not automatically retry a timeout, because execution may
already have happened.

TLS now requires the broker's issuing root CA in `MQTT_CA_CERT` in `secrets.h`.
It verifies the server and synchronizes time using NTP. An empty CA is a
configuration error; no insecure TLS fallback is used. Existing secrets files
need the new field from `secrets.example.h`.

For a compile check with placeholder credentials (no flashing), run
`./firmware/emitter/check_build.ps1` from the repository root.

## Test the backend connection without speech

From `backend`, use the virtual environment with requirements-dev.txt installed:

```powershell
.venv/Scripts/python.exe tools/test_emitter.py tv volume_up
.venv/Scripts/python.exe tools/test_emitter.py tv volume_up --execute
```

The first prints the command only. The second uses the same MQTT client as the
backend, waits up to 15 seconds for online status, sends one catalog button and
waits for its acceptance ACK. Configure matching broker credentials/topics in
`backend/.env` and firmware `secrets.h` first. No STT/TTS API calls are made.
Do not run the fake emitter alongside real hardware on the same topics: either
could ACK and mask the other's failure.

After direct IR works, use the existing `/command` voice endpoint. Catalog
limitations still apply: STB digit 1 is flagged broken, and channel numbers
are placeholders. Recapture/configure these before testing channel selection.

## Libraries

Arduino Library Manager, board **ESP32C3 Dev Module** for the recorded emitter:

| Library | Min version |
|---|---|
| IRremote | 4.3 |
| PubSubClient | 2.8 |
| ArduinoJson | 7.0 |
| WiFiManager | 2.0 |

## Wiring

```
GPIO4 ──[1k]── base (2N2222A)
                collector ──┬─[100R]─ IR LED ─┐
                            ├─[100R]─ IR LED ─┤
                            ├─[100R]─ IR LED ─┼── 5V
                            └─[100R]─ IR LED ─┘
                emitter ── GND
```

One resistor **per LED**. LEDs don't current-share, so a single shared resistor
leaves one doing all the work while the others barely light.

Fan them across ~90°. Aiming is designed out of the system — she holds a
microphone, not a pointer, and this box never moves.

Mains USB, no battery. A stationary device with a battery is just a device that
eventually dies without warning.

## Broker

HiveMQ Cloud free tier, TLS on 8883.

**This repo is public**, so the cluster hostname and credentials live in
`secrets.h`, which is gitignored:

```bash
cp secrets.example.h secrets.h    # then fill it in
```

Create a credential under **Access Management → Credentials** with publish and
subscribe rights — the cluster URL alone will not authenticate. Use *separate*
credentials for the firmware and the backend, so revoking one does not take the
other down.

The backend's historical test recorded roughly 160 ms for the broker round
trip. Measure again on the real emitter connection; acceptance is acknowledged
before running the sequence so post-power delays do not consume the ACK timeout.

## First run

1. `cp secrets.example.h secrets.h` and fill in the cluster hostname, username,
   password and issuing root CA. Never commit it.
2. Flash. On first boot it opens a WiFi access point called **RevGen-Emitter** —
   join it and pick her network. Credentials persist; a router change means
   redoing this, not reflashing.
3. Watch the serial monitor at **115200**.

Status LED — GPIO2 on a classic ESP32, GPIO8 (active low) on a C3. Selected
automatically by `#if CONFIG_IDF_TARGET_ESP32C3`.

| Pattern | Meaning |
|---|---|
| Fast blink (2Hz) | No WiFi |
| Short pulse every second | WiFi up, no broker |
| Three quick flashes | Connected |
| Solid while firing | Executing a sequence |

On a C3, enable **USB CDC On Boot** in the IDE or there is no serial output.

## Testing

The simplest check is to send a real command from the deployed backend and
watch the board react:

```bash
cd ../../backend
python tools/send_wav.py recordings/01_tv_on__power_on.m4a https://project-revgen.fly.dev/command
```

To publish a command by hand without the backend, use the Python stand-in
rather than installing Mosquitto — `backend/tools/fake_emitter.py` shows the
message format, and it reads credentials from `backend/.env`. It is also how
the wire protocol was verified before any hardware existed: it enforces the
same step count, delay ceiling and protocol whitelist as `parseSteps()` here,
so if it accepts a command this firmware will too.

Topics worth watching: `revgen/emitter/ack` for acknowledgements,
`revgen/emitter/status` for online/offline.

## Two things worth knowing

**`setBufferSize(2048)`.** PubSubClient defaults to 256 bytes and *silently
drops* anything larger. Channel digits and multi-step volume exceed that. This
is the most common way the integration appears to work and doesn't — the
backend publishes happily, the emitter simply never sees the message.

**The ack means "received and understood", not "the TV reacted".** It can't
mean the latter: IR is open-loop, so even after firing nothing tells us the
television saw it. The whole sequence is validated *before* acknowledging,
which is what makes that honest rather than optimistic — an unsupported
protocol or an over-long delay rejects the entire command instead of
half-executing it and leaving the TV somewhere nobody asked for.

Acking before execution also keeps inside the backend's 2.5s timeout. A
sequence with a 2.5s post-power wait takes longer than that to run, and she'd
otherwise be told it failed while it was still working.
