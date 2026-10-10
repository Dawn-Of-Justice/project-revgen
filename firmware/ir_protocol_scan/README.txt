RevGen IR protocol scanner

Target: classic ESP32 emitter B3, receiver OUT on GPIO15.
Library: IRremoteESP8266 2.9.0 (installed).
Serial: 115200 baud.

The scanner uses the library-default enabled decoders, including AC protocols.
It reports protocol, bit length, decoded values/state, supported AC descriptions,
and raw timing arrays. UNKNOWN does not necessarily mean faulty hardware.
A demodulating IR receiver cannot measure the original carrier frequency.
A 50ms capture gap accommodates many multi-part AC messages, but some protocols
need a different gap. Long held buttons can merge repeats; use brief presses.

Open ir_protocol_scan.ino in Arduino IDE, select ESP32 Dev Module and COM12.
Uploading this replaces the normal emitter application during diagnosis:
there is no Wi-Fi, MQTT, learning page or transmission in this sketch.
Saved settings are not intentionally erased. Restore the normal emitter
firmware after recording the diagnostic captures.

For each test, note the remote model, button pressed and AC display settings.
Press once, wait two seconds, and save the full serial output. Capture several
buttons and temperatures to confirm repeatable identification.
