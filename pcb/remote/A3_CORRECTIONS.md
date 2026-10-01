# A3 amplifier orientation correction

A2's amplifier footprint required component-side-down assembly. A3 mirrors the
physical X positions of U3 and J5 pads so the original Adafruit MAX98357A mono
breakout mounts with its components facing up and its speaker row toward the
bottom of the remote. Net identities are unchanged; affected copper is rerouted.

Input order from left to right is VIN, GND, SD, GAIN, DIN, BCLK, LRC. Speaker+
is 1.7 mm left of the module center and speaker− is 1.8 mm right. The speaker
row remains 12.954 mm below the input row. These positions account for both
R180 element rotations in the manufacturer Eagle file and the opposite Y axes
of Eagle and KiCad. The footprint generator is corrected too.

Source: [Adafruit original board files](https://github.com/adafruit/Adafruit-MAX98357-I2S-Amp-Breakout).

A3 supersedes A2 manufacturing files. Earlier files are retained as history.
The microphone fit and charging hardware remain unverified physically. The
24 kHz playback finding in A2_FRESH_REVIEW.md is a separate, open software issue.

Validation: full DRC, unrouted connections, schematic parity and ERC all report
zero issues. All 79 logical pad assignments match the schematic. A separate
geometry check compares all nine amplifier pads with transformed manufacturer
Eagle coordinates; all match. Battery traces remain at least 1 mm and speaker
traces at least 0.8 mm. PTH solder-mask openings are present. The top render was
visually inspected, including the corrected labels and AMP CHIP UP marking.
