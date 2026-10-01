# A3 fresh independent review — 2026-09-07

Requested final review by a new agent with limited context. Design and firmware
were inspected read-only; neither was changed. No demonstrated A3 PCB order
blocker or new confirmed electrical defect was found. This is a CAD/source
assessment, not assembled hardware validation.

## Open software finding

The backend defaults to 24000 Hz (`backend/app/config.py:40`), requests that
rate in `backend/app/tts.py:112`, and the remote passes the returned WAV rate
directly to I2S (`firmware/remote/remote.ino:752`). MAX98357A excludes 24 kHz
from its specified rates. Correct generation or resample audio, including
existing cached WAVs, before functional release. Changing WAV metadata alone
changes speed and pitch. No PCB change is required for this finding.

Source: [MAX98357A/B datasheet, page 19](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf).

## Physical and charging limits

- The microphone's nominal 2.54 mm pitch, 7.62 mm row spacing and centered
  acoustic opening still need comparison with the owned module. No actual
  mismatch was demonstrated. Check the exact button and switch too.
- XIAO rear solder access needs assembly validation. Raised headers require
  separate insulated battery leads as described in ASSEMBLY.md.
- Connectivity is J1+ through SW2 to XIAO B+ and amplifier VIN, with B− at
  ground and XIAO 5V isolated. Charging requires SW2 on. With SW2 off, USB can
  power the MCU while the battery is disconnected.
- The amplifier loads the battery/charger node. Idle charging, termination,
  USB-only behavior and active playback require prototype measurements.
  No charging defect was demonstrated. Cell protection, allowable charging
  current and polarity remain assembly requirements.

Source: [Seeed XIAO ESP32S3 instructions](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/).

## Independent checks

- Actual PCB pad/net membership matches docs/netlist.json with zero differences.
- An independent transform of the original Adafruit Eagle JP1/X1 geometry
  matches all nine A3 amplifier connections for component-up assembly.
  With the input row above the speaker row, input order is VIN, GND, SD,
  GAIN, DIN, BCLK, LRC. Speaker+ is left at (120.8, 153.954) mm and speaker−
  right at (124.3, 153.954) mm in board coordinates.
- Board contour is 120 × 45 mm with rounded corners. Microphone and amplifier
  signal groups, battery divider, differential speaker connections and gain
  selection were checked.
- The SD resistor network supports default shutdown and driven left-channel
  selection. Firmware mutes before removing I2S clocks and holds SD low through
  deep sleep.

Source: [Adafruit original board files](https://github.com/adafruit/Adafruit-MAX98357-I2S-Amp-Breakout), also retained in sources/adafruit-max98357.brd.

## Parent verification alongside the independent agent

A fresh KiCad DRC with zone refill reports zero violations, zero unconnected
items and zero schematic parity mismatches (artifacts/a3-independent-drc.json).
All 79 logical pads match the schematic. PTH mask openings are present. Battery
and speaker trace widths meet the intended 1 mm and 0.8 mm minimums.
All release manifest hashes, source ZIP entries and fabrication ZIP entries
match current files. The board SHA-256 is
`ccacc02e2b2d3712b67a74642d75926f3c7b05e21c09729e8ec59687a4304513`.

This review did not perform physical measurements, enclosure checks, firmware
compilation or live audio/charging tests. Existing A3 archives are unchanged.
