/*
 * RevGen IR capture rig — Phase 0
 * -------------------------------
 * Reads codes off her existing remotes and prints them as paste-ready
 * config/commands.json entries.
 *
 * Two jobs:
 *
 *   1. RECAPTURE both remotes. The v1 catalogue has stb.digit_1 byte-identical
 *      to channel_down -- a copy-paste error that makes any channel containing
 *      a 1 unusable. This sketch WARNS on duplicates as you capture, so that
 *      class of bug cannot survive the session.
 *
 *   2. SWEEP the Panasonic command space for discrete codes that are not on the
 *      physical remote. Manufacturers usually ship separate power-on and
 *      power-off commands. If hers has them, the backend stops using toggles
 *      entirely and the whole "she repeated herself and turned the TV back off"
 *      problem disappears. Sweeping needs the IR LED wired; capture does not.
 *
 * WIRING (capture)
 *   TSOP1838:  OUT -> IR_RECV_PIN,  VCC -> 3V3,  GND -> GND
 *   Nothing else. Three wires.
 *
 * WIRING (sweep, optional)
 *   Same IR driver as the emitter: GPIO -> 1k -> base of 2N2222A, IR LED with
 *   its own 100R from 5V to the collector, emitter to GND.
 *
 * LIBRARIES:  IRremote >= 4.3
 * SERIAL:     115200
 *
 * COMMANDS (type into the serial monitor)
 *   help              this list
 *   name <button>     label the next capture, e.g.  name stb.digit_1
 *   list              everything captured this session, as JSON
 *   clear             forget the session
 *   sweep             Panasonic address 0x8, commands 0x00-0xFF  (needs the LED)
 *   sweep <a> <b>     narrower range, e.g.  sweep 0x30 0x50
 */

#include <Arduino.h>

#define DECODE_NEC
#define DECODE_PANASONIC
#define DECODE_SONY
#define DECODE_SAMSUNG
#define DECODE_RC5
#define DECODE_RC6
#define DECODE_JVC
#define DECODE_LG

#include <IRremote.hpp>

#if CONFIG_IDF_TARGET_ESP32C3
  #define IR_RECV_PIN  3
  #define IR_SEND_PIN  4
#else
  #define IR_RECV_PIN  15
  #define IR_SEND_PIN  4
#endif

// Sweep pacing. A television needs time to react visibly, and you are watching
// (or filming) it to see which command did what.
static const uint16_t SWEEP_GAP_MS   = 900;
static const uint8_t  SWEEP_ADDRESS  = 0x08;

static const size_t MAX_CAPTURES = 60;

struct Capture {
  char     name[24];
  uint16_t protocol;
  uint16_t address;
  uint16_t command;
  uint32_t raw;
};

static Capture captures[MAX_CAPTURES];
static size_t  captureCount = 0;
static char    pendingName[24] = "";

// ---------------------------------------------------------------- helpers

static const char *protocolKey(decode_type_t p) {
  switch (p) {
    case PANASONIC: return "panasonic";
    case NEC:
    case NEC2:      return "nec_raw";
    default:        return nullptr;   // backend only knows these two
  }
}

static void printEntry(const Capture &c) {
  const char *key = protocolKey((decode_type_t)c.protocol);

  Serial.print("  \"");
  Serial.print(c.name[0] ? c.name : "UNNAMED");
  Serial.print("\": { ");

  if (key && strcmp(key, "nec_raw") == 0) {
    Serial.printf("\"raw\": \"0x%08lX\"", (unsigned long)c.raw);
  } else if (key) {
    Serial.printf("\"command\": %u", c.command);          // decimal: commands.json uses ints
    if (c.address != SWEEP_ADDRESS) Serial.printf(", \"address\": %u", c.address);
  } else {
    Serial.printf("\"UNSUPPORTED_PROTOCOL\": \"%s\"", getProtocolString((decode_type_t)c.protocol));
  }
  Serial.println(" },");
}

/*
 * The point of the whole sketch. Two buttons that decode identically means one
 * of them was mislabelled during capture -- exactly how v1 ended up with "1"
 * changing the channel. Catch it while the remote is still in your hand.
 */
static int findDuplicate(const Capture &fresh) {
  for (size_t i = 0; i < captureCount; i++) {
    const Capture &c = captures[i];
    if (c.protocol != fresh.protocol) continue;
    bool same = (c.raw && c.raw == fresh.raw) ||
                (!c.raw && c.address == fresh.address && c.command == fresh.command);
    if (same) return (int)i;
  }
  return -1;
}

static void dumpAll() {
  Serial.println("\n---------- paste into config/commands.json ----------");
  for (size_t i = 0; i < captureCount; i++) printEntry(captures[i]);
  Serial.printf("---------- %u captured ----------\n\n", (unsigned)captureCount);
}

// ---------------------------------------------------------------- sweep

static void sweep(uint16_t from, uint16_t to) {
  Serial.printf("\nSweeping Panasonic addr=0x%02X, commands 0x%02X-0x%02X\n",
                SWEEP_ADDRESS, from, to);
  Serial.println("Point the LED at the TV and FILM the screen -- you will not");
  Serial.println("remember which of 256 commands did what otherwise.");
  Serial.println("Anything typed stops the sweep.\n");
  delay(2500);

  IrReceiver.stop();                     // avoid hearing ourselves

  for (uint16_t cmd = from; cmd <= to; cmd++) {
    if (Serial.available()) { while (Serial.available()) Serial.read();
                              Serial.println("stopped"); break; }
    Serial.printf("0x%02X\n", cmd);      // timestamped by the serial monitor
    IrSender.sendPanasonic(SWEEP_ADDRESS, (uint8_t)cmd, 0);
    delay(SWEEP_GAP_MS);
  }

  IrReceiver.start();
  Serial.println("\nSweep done. Match the timestamps in your video against the");
  Serial.println("printed commands, then fill in the \"discrete\" block for the tv");
  Serial.println("device in config/commands.json. The resolver picks them up on");
  Serial.println("its own and stops sending toggles.\n");
}

// ---------------------------------------------------------------- serial

static void handleLine(String line) {
  line.trim();
  if (!line.length()) return;

  if (line == "help") {
    Serial.println("  name <button>   label the next capture, e.g. name stb.digit_1");
    Serial.println("  list            dump everything captured, as JSON");
    Serial.println("  clear           forget the session");
    Serial.println("  sweep [a] [b]   Panasonic command sweep (needs the IR LED)");
    return;
  }
  if (line == "list")  { dumpAll(); return; }
  if (line == "clear") { captureCount = 0; pendingName[0] = '\0';
                         Serial.println("cleared"); return; }

  if (line.startsWith("name ")) {
    String n = line.substring(5); n.trim();
    strncpy(pendingName, n.c_str(), sizeof(pendingName) - 1);
    pendingName[sizeof(pendingName) - 1] = '\0';
    Serial.printf("next press will be recorded as: %s\n", pendingName);
    return;
  }

  if (line.startsWith("sweep")) {
    uint16_t a = 0x00, b = 0xFF;
    int sp = line.indexOf(' ');
    if (sp > 0) {
      String rest = line.substring(sp + 1); rest.trim();
      int sp2 = rest.indexOf(' ');
      if (sp2 > 0) { a = strtol(rest.substring(0, sp2).c_str(), nullptr, 0);
                     b = strtol(rest.substring(sp2 + 1).c_str(), nullptr, 0); }
    }
    sweep(a, b);
    return;
  }

  Serial.println("unknown command -- type help");
}

// ---------------------------------------------------------------- arduino

void setup() {
  Serial.begin(115200);
  delay(300);

  IrReceiver.begin(IR_RECV_PIN, ENABLE_LED_FEEDBACK);
  IrSender.begin(IR_SEND_PIN);

  Serial.println("\nRevGen capture rig");
  Serial.printf("receiver on GPIO%d, sender on GPIO%d\n\n", IR_RECV_PIN, IR_SEND_PIN);
  Serial.println("Label a button, then press it on the remote:");
  Serial.println("    name tv.power");
  Serial.println("Type help for everything else.\n");
}

void loop() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { if (line.length()) { handleLine(line); line = ""; } }
    else line += ch;
  }

  if (!IrReceiver.decode()) return;

  auto &d = IrReceiver.decodedIRData;

  if (d.protocol == UNKNOWN) {
    Serial.println("  (undecoded -- press again, or move closer to the receiver)");
    IrReceiver.resume();
    return;
  }
  if (d.flags & IRDATA_FLAGS_IS_REPEAT) { IrReceiver.resume(); return; }

  Capture fresh = {};
  strncpy(fresh.name, pendingName, sizeof(fresh.name) - 1);
  fresh.protocol = d.protocol;
  fresh.address  = d.address;
  fresh.command  = d.command;
  fresh.raw      = (protocolKey(d.protocol) &&
                    strcmp(protocolKey(d.protocol), "nec_raw") == 0)
                   ? d.decodedRawData : 0;

  Serial.printf("%-14s %-10s addr=0x%02X cmd=0x%02X raw=0x%08lX\n",
                fresh.name[0] ? fresh.name : "(unnamed)",
                getProtocolString(d.protocol),
                d.address, d.command, (unsigned long)d.decodedRawData);

  int dup = findDuplicate(fresh);
  if (dup >= 0) {
    Serial.printf("  !! IDENTICAL to \"%s\" already captured.\n",
                  captures[dup].name[0] ? captures[dup].name : "(unnamed)");
    Serial.println("  !! Either you pressed the same button twice, or the remote");
    Serial.println("  !! sends one code for both. Do NOT record both -- this is");
    Serial.println("  !! precisely the bug that made stb.digit_1 change channels.");
  }

  if (!protocolKey(d.protocol)) {
    Serial.printf("  note: backend supports panasonic and nec_raw only; this is %s\n",
                  getProtocolString(d.protocol));
  }

  if (fresh.name[0] && captureCount < MAX_CAPTURES) {
    captures[captureCount++] = fresh;
    printEntry(fresh);
    pendingName[0] = '\0';
  } else if (!fresh.name[0]) {
    Serial.println("  (not saved -- run `name <button>` first)");
  } else {
    Serial.println("  (buffer full -- run `list`, then `clear`)");
  }

  IrReceiver.resume();
}
