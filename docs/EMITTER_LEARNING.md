# Emitter learning mode

Implemented locally on 2026-09-08. This firmware and backend change has not
been flashed or deployed. Capture and appliance response still need hardware
testing; earlier backend-to-emitter tests do not validate learning.

## Wiring and use

The recovered classic ESP32 carrier uses GPIO4 for the IR driver, GPIO15 for
receiver OUT, and GPIO27 for the learning button. Connect the button to ground;
the revised schematic includes a 10k pull-up to 3.3V. The IR receiver and button
are required for learning. Use a receiver explicitly rated for 3.3V operation
and verify its actual pin order. Receiver power is 3.3V, with 100nF across its
supply and ground. The schematic's J1 pins are 1=3V3, 2=GND, 3=OUT.

1. Connect the emitter and phone/computer to the same Wi-Fi.
2. Hold the learning button for five seconds. The status LED blinks rapidly.
3. Open `http://revgen-emitter.local/`. If mDNS does not resolve, use the local
   IP address printed on the serial monitor. The firmware cannot automatically
   launch a browser on another device.
4. Enter a device ID/name and action ID/name. Use `tv` and `stb` for the primary
   devices, or IDs such as `bedroom_tv` for additional remotes.
5. Start capture. Press and release the original remote button twice, leaving
   a short pause between presses. Two matching valid frames are required.
6. Test the captured command and observe the appliance. A decoded signal or
   successful transmission alone cannot confirm that the appliance responded.
7. Save. The page distinguishes locally saved, upload pending, rejected and
   uploaded states. Repeat for other buttons/remotes. Saving the same device,
   action and kind replaces that mapping; changing its ID creates a new one.
8. Close learning mode from the page or hold the button again for five seconds.
   It also closes after five minutes without interaction or thirty minutes total.

Normal backend commands are rejected during learning to avoid interfering
with capture. Learning mode begins only after any pending sequence finishes.
The page is available only during a physically enabled session and requires a
session token and matching host. Anyone on that LAN who opens the enabled page
can configure it; this is not a separate account login. Wi-Fi is required.

## Names, channels and power

Learn primary STB keys as `digit_0` through `digit_9`. Then map a channel display
name to its channel number in the channel section. The backend sends the digit
sequence using its existing channel resolver. Channel aliases currently target
the primary `stb`, not arbitrary additional devices.

The backend gives the LLM the registered command keys and display names. It
accepts only a registered key and looks up the validated IR payload itself.
The LLM does not generate IR codes. Existing TV/STB actions use learned button
overrides; additional named actions use exact learned-command dispatch.

An ordinary power button must be marked `power_toggle`. Only use `power_on`
or `power_off` behavior for a genuinely discrete signal. Toggle transmissions
are debounced. IR remains open-loop: this cannot establish the appliance's
current power state. Additional-device toggle mappings are offered to the LLM
for explicit toggle requests, not as reliable on/off commands.

## Supported scope and persistence

- NEC/NEC2 32-bit and Panasonic 48-bit decoded commands matching the existing
  send protocol are supported. Unknown protocols and AC state frames are rejected.
- Up to 32 local command/channel records; actual NVS space can fill earlier.
  Storage failures are reported instead of pretending a save succeeded.
- Names allow 64 UTF-8 bytes on the emitter; IDs are lowercase letters, digits
  and underscores, start with a letter, and have at most 32 characters.
- Local NVS retains mappings and pending uploads across reset. Uploads retry
  every five seconds when connected, oldest first, until acknowledged.
- Backend storage is `DATA_DIR/learned_commands.json`, written atomically before
  acknowledgement, with up to 128 mappings and eight producer identities.
- Duplicate deliveries are acknowledged without reverting newer mappings.
  Stale sequences are rejected. Disk failures leave uploads pending for retry.
- Rejected records can be retried from the page; stale records need an edit and
  new save. There is no deletion or cross-emitter catalog download UI yet.

## Backend rollout

Deploy the matching backend before flashing the learning firmware. Preserve its
persistent data directory. MQTT ACLs must allow the emitter to publish
`revgen/emitter/learn` and subscribe to `revgen/emitter/learn_ack`; the backend
needs the reverse permissions. Both topics are non-retained. Existing command,
acknowledgement and status permissions are unchanged.

After deployment and flashing, verify two captures, physical test transmission,
local persistence after reboot, upload acknowledgement, backend persistence
after restart, and a voice request resolving the newly named action. These live
checks remain pending. Do not erase NVS during routine updates.

Local verification: backend regression suite, mocked browser UI tests and a
classic ESP32 compilation. Browser mocks test interface behavior, not electrical
capture or live MQTT permissions.
