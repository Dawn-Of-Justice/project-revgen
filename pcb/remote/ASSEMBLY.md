# RevGen A3 assembly

> **A3 supersedes A2 and rejected A1.** A3 corrects the amplifier for component-side-up mounting. Physical module fit and charging/sleep measurements still require prototype verification. The separate 24 kHz playback issue remains open.

Carrier for the existing plain Seeed XIAO ESP32S3, round Robu INMP441 and
Adafruit MAX98357A mono breakout. Speaker connects to J2.

## Fabrication and fit

120 × 45 mm contour, R8 corners, two layers, 1.6 mm FR4, standard 1 oz copper.
Four M2.5 mounting holes. The Gerber job size includes the 0.05 mm outline stroke.
Print `artifacts/assembly-1to1.svg` at **100%, no fit-to-page**, check the 120 mm
length with a ruler, and compare the owned modules and button.

The mic's nominal 2.54 mm pin pitch / 7.62 mm row separation is inferred from
its product image, not a supplier mechanical drawing. The chosen button is
Omron B3F-40xx; an arbitrary 12 mm button is not guaranteed to fit.

The mic center is 22.5 mm from either side, 31 mm below the top edge, above
the talk button. Nearby passives have been moved to preserve clearance.

## Install modules

1. Fit passives first. Leave **R1 empty**, fit **R5 = 0 ohms**.
2. XIAO USB points toward the top. J3/J4/J6 together represent one module,
   not three connectors to purchase. J3/J4 support castellated soldering or
   pins. J6 offers rear solder access to underside battery pads: 1 is B+,
   2 is B−. These require solder joints. If existing headers raise the XIAO,
   use two short insulated battery leads; lands cannot bridge an air gap.
   Rear-access soldering has not been physically tested on this prototype.
3. Mic **CHIP UP, acoustic port DOWN**, over the 3.2 mm hole. With USB at top,
   upper row left-to-right is **L/R, WS, SCK**; lower row **GND, VDD, SD**.
   Keep the acoustic opening clear.
4. Amplifier **CHIP / COMPONENTS UP**, with its speaker row toward the bottom
   of the remote. Input row left-to-right is **VIN, GND, SD, GAIN, DIN, BCLK, LRC**.
   Use soldered header pins with clearance for underside solder joints. J5 is its speaker
   pair, 12.954 mm below the input row, 3.5 mm pitch. Connect the module speaker
   holes using soldered pins or lead stubs; omit its screw terminal block.
   At J5, **speaker + is left and − is right**, viewed from the component side
   with the remote USB at the top. Do not use the superseded A2 mounting order.
5. Connect a speaker rated at least 4 ohms at J2 +/−. Neither speaker terminal is ground. Connect a
   protected single-cell 3.7 V LiPo at J1, checking polarity against the + mark.
   SW2 isolates the battery from the switched rail.

The XIAO uses an **external IPEX antenna**. Preserve cable access and position
it near the copper-free side area, away from battery and metal. Keep USB,
reset and boot accessible. Enclosure and speaker mounting are not defined here.

## Additional parts

| References | Value / footprint |
|---|---|
| C1, C3 | 10 µF 16 V radial electrolytic, D6.3 mm, P2.5 mm |
| C5 | 220 µF 16 V radial electrolytic, D6.3 mm, P2.5 mm |
| C2, C4, C6, C7 | 100 nF ceramic disc, P5 mm; C7 optional debounce |
| R2, R3 | 1 MΩ 1%, axial 1/4 W, P10.16 mm |
| R4 | 100 kΩ axial, P10.16 mm, button pull-up |
| R5 | 0 Ω axial link, P10.16 mm, fitted |
| R6 | 2.2 kΩ, 1%, axial 1/4 W, P10.16 mm; SD series protection |
| R7 | 10 kΩ, 1%, axial 1/4 W, P10.16 mm; SD default-off pull-down |
| R1 | 100 kΩ gain option, **do not fit** with R5 |
| SW1 | Omron B3F-40xx 12 mm tactile |
| SW2 | C&K **1101M2S3CQE2**, 6 A at 28 VDC; common pin 2, 4.70 mm pitch, 1.85 mm drills |
| J1 | JST S2B-PH-K right-angle, 2 mm pitch, 2 pins |
| J2 | JST B2B-PH-K vertical, 2 mm pitch, 2 pins |
| TP1–TP11 | Test pads, no fitted part required |

Respect electrolytic polarity. These parts are additional to the owned modules.

## First power and charging

Charging is automatic in the XIAO hardware; separate charging firmware is not
needed simply to charge the cell. Battery alerts and validation remain pending.

The XIAO onboard charger connects through its underside battery pads; no
separate charger IC is added. SW2 must connect the battery for charging.
With SW2 off, USB may still power the XIAO.

Before battery installation, check shorts and J6 polarity/continuity. On first
power verify 3V3, VBAT_SW and the divider: TP9 should read half TP8. Verify
button wake, recording and playback. Test USB charging current and cell voltage
initially with the remote idle, then validate termination and behavior with the
amplifier active. Charging on the assembled carrier has not yet been verified. CAD checks are not functional charging tests.

## Sources

- [Seeed XIAO documentation](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/), official [footprints](https://files.seeedstudio.com/wiki/XIAO-KiCad-Library/New_XIAO_Series_Footprints.zip) and [symbols](https://files.seeedstudio.com/wiki/XIAO-KiCad-Library/XIAO_Series_SCH_Symbols.zip). Battery pad 23 is VBAT, 24 is GND.
- [Adafruit original mono board files](https://github.com/adafruit/Adafruit-MAX98357-I2S-Amp-Breakout), copied with license into `sources/`.
- User's [Robu mic](https://robu.in/product/inmp441-mems-high-precision-omnidirectional-microphone-module-i2s/) and [Robu amplifier](https://robu.in/product/adafruit-max98357a-i2s-3w-class-d-amplifier-breakout-board/). Mic orientation was checked against pictured labels; pitch needs physical comparison.

## A2 electrical corrections

Use the exact new switch; the old OS102011MS2Q cannot substitute. R6 limits
current into amplifier SD when its supply falls below the ESP32 logic supply.
R7 holds SD low when the GPIO floats. Including the breakout 1 MΩ pull-up and
100 kΩ internal pull-down, nominal SD is about 38 mV with GPIO floating at a
4.2 V cell, and 2.66 V when driven high from 3.3 V. Verify these states on the
prototype. Updated firmware holds GPIO5 low through deep sleep and mutes the
amplifier before stopping clocks. Firmware compilation is separate from
charging and sleep-current measurements.

Switch footprint is based on [C&K 1000 series datasheet](https://www.littelfuse.com/assetdocs/littelfuse-ck-slide-1000-series-datasheet?assetguid=68a2b41e-19a4-4cf4-821b-aca78a430f00), pages 2 and 4; SD protection follows [MAX98357A datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf), page 17.
