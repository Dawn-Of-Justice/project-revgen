# A2 fresh independent review — 2026-09-07

> Historical A2 findings. The amplifier orientation is corrected in A3;
> see A3_CORRECTIONS.md. The 24 kHz software finding remains open.

Read-only review of the released A2 design, with a fresh agent given limited context. No PCB, schematic, firmware or manufacturing archive was changed by this review.

## Disposition

Do not treat A2 as an unconditional drop-in production release. No additional confirmed electrical-routing defect was found, but amplifier mounting orientation and owned-module fit need resolution before ordering with confidence.

## Findings

### Amplifier requires component-side-down mounting

The A2 input row is LRC, BCLK, DIN, GAIN, SD, GND, VIN from left to right, with the speaker row below it. The original Adafruit module fits this arrangement with its components facing the carrier. The assembly instructions mention component clearance but do not explicitly state this orientation or establish a spacer height.

The manufacturer Eagle JP1 and X1 elements both have R180 rotation. Their transformed coordinates put VIN at +7.62 mm and speaker+ at (+1.7, +12.954) relative to the input-row center. Preserving these offsets in KiCad, whose vertical coordinate direction is opposite, reflects the mounting arrangement. For component-side-up mounting with the speaker row below the input row, the input order would instead be VIN, GND, SD, GAIN, DIN, BCLK, LRC, with speaker+ on the left.

The existing layout may work with deliberate flipped mounting and adequate clearance. It is not a verified fit for a module with conventional preinstalled headers. Either verify this arrangement against the owned module, or revise the footprint and routing for component-side-up mounting. Source: [Adafruit board files](https://github.com/adafruit/Adafruit-MAX98357-I2S-Amp-Breakout).

### Default TTS rate is outside the amplifier specification

`backend/app/config.py` requests 24000 Hz. The remote firmware reads the WAV rate and passes it directly to the amplifier I2S clock configuration. MAX98357A specifies 8, 16, 32, 44.1, 48, 88.2 and 96 kHz operation; 24 kHz is outside its specified bands.

Request a supported output rate or resample audio correctly. Merely changing the playback clock changes speed and pitch. Reported successful breadboard playback does not establish operation within specification. This is a software correction and does not itself require a PCB change. Source: [MAX98357A/B datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf).

## Remaining physical validation

- Compare the owned microphone against the 100% scale layout: its 2.54 mm pitch and 7.62 mm row separation were inferred from imagery.
- Verify XIAO rear battery-pad access; raised headers require separate insulated battery leads as documented.
- Verify battery protection, permitted charge current, speaker rating and actual charging behavior. Charging components have not been breadboard tested.
- Test USB-only operation explicitly: SW2 disconnects the battery, while amplifier VIN remains connected to the XIAO charger/battery node.

## Checks passed

Full DRC, unconnected-item check, schematic parity and ERC report zero issues. All PTH pads have solder-mask openings. GPIO mappings match the plain XIAO ESP32S3 and firmware. The microphone channel selection and amplifier shutdown network are consistent. All ten manufacturing ZIP entries match the export directory byte for byte; the source archive and release hashes also match. The outline is 120 × 45 mm with R8 corners.

These are CAD and source checks, not assembled hardware validation.
