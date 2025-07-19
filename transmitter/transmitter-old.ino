#include <IRremote.h>

#define IR_RECEIVE_PIN 22
#define IR_SEND_PIN 4
#define BUTTON_PIN 26
#define ENABLE_LED_FEEDBACK  true
#define USE_DEFAULT_FEEDBACK_LED_PIN true
#define SENDING_REPEATS 0

const int user_input_size = 100;
char user_input[user_input_size];
int char_changing = 0;

/*Sets up the program*/
void setup() {
  Serial.begin(115200);
  SerialBT.begin("ESP32 Remote");
  
  IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK, USE_DEFAULT_FEEDBACK_LED_PIN);
  IrSender.begin(IR_SEND_PIN, ENABLE_LED_FEEDBACK); // Specify send pin and enable feedback LED at default feedback LED pin
  
  Serial.println("The device started, now you can pair it with bluetooth!");
  Serial.print("Ready to send IR signals at pin ");
  Serial.println(IR_SEND_PIN);

  //used internal pullup resistors to prevent noise
  pinMode(BUTTON_PIN, INPUT_PULLUP);
}

/*sends an IR code*/
void send_message(const char message[]){
  //unsigned longs are 32 bits so max number is 4294967295 = FFFFFFFF
  unsigned long code = strtoul(message, NULL, 16);
  Serial.print("Sending code:");
  Serial.println(message);

  //the receiver has to be disabled to send messages
  IrReceiver.stop();
   
  IrSender.sendNECRaw(code, SENDING_REPEATS);

  //restarts the reciever
  IrReceiver.start();
}

/*checks for serial messages*/
void check_serial(){
  if(Serial.available()){
    delay(100);
    //clears the previous user input
    for(int i = 0;i<user_input_size;i++){
      user_input[i] = 0;
    }
    char_changing = 0;
    while(Serial.available()){
      char character = Serial.read();
      if(character != '\n'){
        if(char_changing < (user_input_size-1)){//-1 due to null teminating character. Usable size of an array is 1 less than its stated length
          //saves all recieved characters into buffer
          user_input[char_changing] = character;
          char_changing++;
        }else{
          //input larger than buffer
          Serial.println("User input too long to store");
        }
      }else{
        //reached the end of the line so sends the recieved message
        send_message(user_input);
      }
    }
  }
}

/*checks for IR codes picked up by the reciever*/
void check_recieved(){
  if(IrReceiver.decode()){
    if(IrReceiver.decodedIRData.decodedRawData != 0){
      IrReceiver.printIRResultShort(&Serial);
      if(IrReceiver.decodedIRData.decodedRawData == 0xFFFFFFFF){
        //Repeat command(used by some IR remotes
        //to indicate that a button has been held
        Serial.println("...");
      }else{
        //transmits the recieved IR code back to the Android device for storage
        Serial.print("command:");
        Serial.println(IrReceiver.decodedIRData.decodedRawData, HEX);
      }
    }
    //Enable receiving of the next value
    IrReceiver.resume(); 
  }
}

/*the main loop*/
void loop() {
  check_serial();
  //checks if the recieve button has been held
  if(digitalRead(BUTTON_PIN) == LOW){
    //and if so it checks if any IR codes have been picked up
    check_recieved();
  }
}
