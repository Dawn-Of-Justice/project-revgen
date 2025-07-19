#include <IRremote.h>

// Define the IR transmitter pin
#define IR_SEND_PIN 5

// Button structure
struct Button {
  String name;
  uint16_t address;
  uint16_t command;
  uint32_t rawData;
};

// TV Remote buttons (Panasonic) - using protocol method
Button tvButtons[] = {
  {"power", 0x8, 0x3D, 0},
  {"vol+", 0x8, 0x20, 0},
  {"vol-", 0x8, 0x21, 0},
  {"up", 0x8, 0x4A, 0},
  {"down", 0x8, 0x4B, 0},
  {"left", 0x8, 0x4E, 0},
  {"right", 0x8, 0x4F, 0},
  {"ok", 0x8, 0x49, 0},
  {"exit", 0x8, 0xD3, 0},
  {"apps", 0x98, 0x8F, 0}
};

// Set Top Box buttons (NEC) - using raw data method
Button stbButtons[] = {
  {"power", 0xDF, 0x59, 0xA65900DF},
  {"mute", 0xDF, 0x95, 0x6A9500DF},
  {"vol+", 0xDF, 0x80, 0x7F8000DF},
  {"vol-", 0xDF, 0x81, 0x7E8100DF},
  {"ch+", 0xDF, 0x85, 0x7A8500DF},
  {"ch-", 0xDF, 0x86, 0x798600DF},
  {"1", 0xDF, 0x86, 0x798600DF},
  {"2", 0xDF, 0x93, 0x6C9300DF},
  {"3", 0xDF, 0xCC, 0x33CC00DF},
  {"4", 0xDF, 0x8E, 0x718E00DF},
  {"5", 0xDF, 0x8F, 0x708F00DF},
  {"6", 0xDF, 0xC8, 0x37C800DF},
  {"7", 0xDF, 0x8A, 0x758A00DF},
  {"8", 0xDF, 0x8B, 0x748B00DF},
  {"9", 0xDF, 0xC4, 0x3BC400DF},
  {"0", 0xDF, 0x87, 0x788700DF}
};

const int tvButtonCount = sizeof(tvButtons) / sizeof(tvButtons[0]);
const int stbButtonCount = sizeof(stbButtons) / sizeof(stbButtons[0]);

void setup() {
  Serial.begin(9600);
  
  // Turn off onboard LED
  pinMode(2, OUTPUT);
  digitalWrite(2, LOW);
  
  // Initialize IR transmitter and ensure LED is OFF
  pinMode(IR_SEND_PIN, OUTPUT);
  digitalWrite(IR_SEND_PIN, LOW);
  IrSender.begin(IR_SEND_PIN);
  digitalWrite(IR_SEND_PIN, LOW);
  
  Serial.println("========== IR REMOTE CONTROLLER ==========");
  Serial.println("📺 TV Commands: tv.power, tv.vol+, tv.vol-, tv.up, tv.down, tv.left, tv.right, tv.ok, tv.exit, tv.apps");
  Serial.println("📡 STB Commands: stb.power, stb.mute, stb.vol+, stb.vol-, stb.ch+, stb.ch-, stb.0-9");
  Serial.println("");
  Serial.println("💡 Examples:");
  Serial.println("  tv.power");
  Serial.println("  stb.power, stb.1, stb.2, stb.3");
  Serial.println("  tv.power, delay 2000, stb.power");
  Serial.println("==========================================");
}

void loop() {
  if (Serial.available()) {
    String input = Serial.readString();
    input.trim();
    input.toLowerCase();
    
    processCommands(input);
  }
  
  delay(50);
}

void processCommands(String commandString) {
  Serial.println("🚀 EXECUTING: " + commandString);
  
  // Split commands by comma
  int startIndex = 0;
  
  while (startIndex < commandString.length()) {
    int commaIndex = commandString.indexOf(',', startIndex);
    if (commaIndex == -1) commaIndex = commandString.length();
    
    String command = commandString.substring(startIndex, commaIndex);
    command.trim();
    
    if (command.length() > 0) {
      executeCommand(command);
      delay(200); // Small delay between commands
    }
    
    startIndex = commaIndex + 1;
  }
  
  Serial.println("✅ Complete!\n");
}

void executeCommand(String command) {
  // Handle special commands
  if (command.startsWith("delay ")) {
    int delayTime = command.substring(6).toInt();
    Serial.print("⏳ Wait ");
    Serial.print(delayTime);
    Serial.println("ms");
    delay(delayTime);
    return;
  }
  
  // Handle remote commands
  if (command.startsWith("tv.")) {
    String buttonName = command.substring(3);
    sendTVCommand(buttonName);
  } else if (command.startsWith("stb.")) {
    String buttonName = command.substring(4);
    sendSTBCommand(buttonName);
  } else {
    Serial.println("❌ Unknown: " + command);
  }
}

void sendTVCommand(String buttonName) {
  for (int i = 0; i < tvButtonCount; i++) {
    if (tvButtons[i].name == buttonName) {
      Serial.print("📺 TV " + buttonName + " → ");
      
      IrSender.sendPanasonic(tvButtons[i].address, (uint8_t)tvButtons[i].command, 0);
      
      Serial.println("✅");
      return;
    }
  }
  Serial.println("❌ TV button not found: " + buttonName);
}

void sendSTBCommand(String buttonName) {
  for (int i = 0; i < stbButtonCount; i++) {
    if (stbButtons[i].name == buttonName) {
      Serial.print("📡 STB " + buttonName + " → ");
      
      // Use NEC Raw method (Method 3 that works)
      IrSender.sendNECRaw(stbButtons[i].rawData, 0);
      
      Serial.println("✅");
      return;
    }
  }
  Serial.println("❌ STB button not found: " + buttonName);
}