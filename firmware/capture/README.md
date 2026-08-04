# Capture rig — Phase 0

Reads codes off her existing remotes and prints them as paste-ready
`config/commands.json` entries.

Needs **three wires**: TSOP1838 OUT → GPIO, VCC → 3V3, GND → GND. No
transistor, no IR LED, no breadboard strictly required.

`IR_RECV_PIN` is GPIO15 on a classic ESP32, GPIO3 on a C3 — selected
automatically.

## Why this exists

Two problems in the inherited catalogue:

**`stb.digit_1` is byte-identical to `stb.channel_down`** (`0x798600DF`). A
copy-paste error from v1. The backend refuses to fire it rather than changing
the channel she did not ask for, so any channel containing a 1 is unavailable
until this is recaptured.

**`tv.apps` is malformed** — address `0x98` where every other TV button is
`0x8`, and a raw value with 11 hex digits where the others have 12.

## Capturing

```
name tv.power
```

then press that button on the remote. It prints the decoded code and the JSON
line to paste. Repeat for every button on both remotes.

```
  tv.power       Panasonic  addr=0x08 cmd=0x3D raw=0xBD3D00802002
  "tv.power": { "command": 61 },
```

**It warns on duplicates.** If a capture matches something already recorded
this session, it says so loudly — that is the exact bug that produced
`stb.digit_1`, caught while the remote is still in your hand rather than months
later when she asks for channel 21.

Other commands: `list` dumps everything as JSON, `clear` forgets the session,
`help` lists them.

The backend understands `panasonic` and `nec_raw` only. Anything else decodes
fine but gets flagged as unsupported.

## Sweeping for discrete power codes

This one needs the IR LED wired, same driver as the emitter.

```
sweep
```

Fires Panasonic address `0x8`, commands `0x00`–`0xFF`, one every 900ms, printing
each as it goes. **Film the television.** You will not remember which of 256
commands did what otherwise — match the video timestamps against the printed
list afterwards.

Manufacturers usually ship discrete power-on and power-off commands that are not
on the physical remote. If hers has them, put them in the `discrete` block for
the `tv` device in `config/commands.json`:

```json
"discrete": { "power_on": { "command": 62 }, "power_off": { "command": 63 } }
```

The resolver checks for them on its own. The moment they are present it stops
sending toggles, and the entire "she repeated herself and switched the TV back
off" problem disappears — along with the 8-second debounce that currently works
around it.

`sweep 0x30 0x50` narrows the range. Anything typed stops it early.

Worth also sweeping for discrete input-select codes while you are there, though
the current design never changes input.
