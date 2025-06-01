#include <IRremote.h>

#define IR_SEND_PIN 5

void setup() {
  Serial.begin(9600);
  delay(1000);
  
  Serial.println("Basic IR Send Test");
  IrSender.begin(IR_SEND_PIN);
}

void loop() {
  Serial.println("Sending NEC code...");
  
  // Most basic NEC code sending
  IrSender.sendNEC(0x00, 0x01, 0);
  
  Serial.println("Sent!");
  delay(3000);  // Wait 3 seconds between sends
}