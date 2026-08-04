# IR emitter

Stationary box on the TV cabinet. Subscribes to MQTT, fires IR, acknowledges.
Holds no IR codes — the backend sends complete descriptors, so new devices are
a server-side JSON edit rather than a trip to reflash hardware.

## Libraries

Arduino Library Manager, board **ESP32 Dev Module**:

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

## First run

1. Set `MQTT_HOST` / `MQTT_USER` / `MQTT_PASS` at the top of `emitter.ino`.
   Use `MQTT_TLS = true` with port 8883 for a hosted broker, `false` / 1883
   for a local Mosquitto.
2. Flash. On first boot it opens a WiFi access point called **RevGen-Setup** —
   join it and pick her network. Credentials persist; a router change means
   redoing this, not reflashing.
3. Watch the serial monitor at **115200**.

Status LED (GPIO2):

| Pattern | Meaning |
|---|---|
| Fast blink (2Hz) | No WiFi |
| Short pulse every second | WiFi up, no broker |
| Three quick flashes | Connected |
| Solid while firing | Executing a sequence |

## Test without the backend

```bash
mosquitto_pub -h <broker> -p 8883 --capath /etc/ssl/certs -u revgen -P '<pass>' \
  -t revgen/emitter/cmd \
  -m '{"id":"test-1","steps":[{"type":"ir","protocol":"panasonic","address":8,"command":61,"repeat":0}]}'
```

That's TV power. Subscribe to `revgen/emitter/ack` in another terminal to see
the acknowledgement, and `revgen/emitter/status` for online/offline.

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
