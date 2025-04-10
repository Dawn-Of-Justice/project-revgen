#include <driver/i2s.h>
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include "esp_sleep.h"
#include "driver/rtc_io.h"

#define I2S_SD 32
#define I2S_WS 25
#define I2S_SCK 33
#define I2S_PORT I2S_NUM_0

// Define button pin - must be RTC GPIO for wake-up functionality
#define BUTTON_PIN GPIO_NUM_26  // Make sure this is an RTC-capable GPIO

// Define external LED pin
#define LED_PIN 27

#define bufferCnt 10
#define bufferLen 1024
int16_t sBuffer[bufferLen];

const char* ssid = "This Is Note Free Either!";
const char* password = "godISlove";

const char* websocket_server_host = "192.168.0.196";
const uint16_t websocket_server_port = 8888;

// Maximum stream time in milliseconds before going back to sleep
#define MAX_STREAM_TIME 30000  // 30 seconds

// WebSocket reconnection parameters
#define MAX_RECONNECT_ATTEMPTS 5
#define RECONNECT_DELAY 1000  // 1 second between reconnection attempts

// For extended light sleep vs regular light sleep
#define REGULAR_SLEEP 0
#define EXTENDED_SLEEP 1

using namespace websockets;
WebsocketsClient client;
volatile bool isWebSocketConnected = false;
volatile bool isStreaming = false;
volatile bool streamStarted = false;
volatile unsigned long lastConnectionAttempt = 0;
volatile int reconnectAttempts = 0;

// Add RTC data to persist across sleep cycles
RTC_DATA_ATTR bool firstBoot = true;
RTC_DATA_ATTR int bootCount = 0;
RTC_DATA_ATTR int sleepMode = REGULAR_SLEEP;  // 0 = regular light sleep, 1 = extended light sleep

void onEventsCallback(WebsocketsEvent event, String data) {
  if (event == WebsocketsEvent::ConnectionOpened) {
    Serial.println("Connection Opened");
    isWebSocketConnected = true;
    reconnectAttempts = 0;  // Reset reconnect counter on successful connection
  } else if (event == WebsocketsEvent::ConnectionClosed) {
    Serial.println("Connection Closed");
    isWebSocketConnected = false;
    // Don't immediately stop streaming - reconnection will be attempted in loop()
    digitalWrite(LED_PIN, LOW);
  } else if (event == WebsocketsEvent::GotPing) {
    Serial.println("Got a Ping!");
  } else if (event == WebsocketsEvent::GotPong) {
    Serial.println("Got a Pong!");
  }
}

void i2s_install() {
  // Set up I2S Processor configuration
  const i2s_config_t i2s_config = {
    .mode = i2s_mode_t(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 44100,
    .bits_per_sample = i2s_bits_per_sample_t(16),
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = i2s_comm_format_t(I2S_COMM_FORMAT_STAND_I2S),
    .intr_alloc_flags = 0,
    .dma_buf_count = bufferCnt,
    .dma_buf_len = bufferLen,
    .use_apll = false
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
}

void i2s_setpin() {
  // Set I2S pin configuration
  const i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = -1,
    .data_in_num = I2S_SD
  };

  i2s_set_pin(I2S_PORT, &pin_config);
}

bool connectToWebSocket() {
  if (client.available()) {
    client.close();
  }
  
  // Increment the reconnect attempts counter
  reconnectAttempts++;
  lastConnectionAttempt = millis();
  
  Serial.print("WebSocket connection attempt ");
  Serial.print(reconnectAttempts);
  Serial.print(" of ");
  Serial.println(MAX_RECONNECT_ATTEMPTS);
  
  // Attempt to connect
  bool connected = client.connect(websocket_server_host, websocket_server_port, "/");
  
  if (connected) {
    Serial.println("WebSocket Connected!");
    isWebSocketConnected = true;
    return true;
  } else {
    Serial.println("WebSocket connection failed.");
    isWebSocketConnected = false;
    return false;
  }
}

bool setupWiFiAndWebSocket() {
  // Connect to WiFi
  WiFi.disconnect();
  delay(100);
  WiFi.begin(ssid, password);

  int attempts = 0;
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("");
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    
    // Set up WebSocket events callback
    client.onEvent(onEventsCallback);
    
    // Initialize reconnection counter
    reconnectAttempts = 0;
    
    // Connect to WebSocket server
    return connectToWebSocket();
  } else {
    Serial.println("");
    Serial.println("WiFi connection failed.");
    return false;
  }
}

bool reconnectWebSocket() {
  // Check if we've exceeded the maximum reconnection attempts
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    Serial.println("Maximum reconnection attempts reached. Going to deep sleep.");
    return false;
  }
  
  // Check if we need to wait between reconnection attempts
  unsigned long currentTime = millis();
  if (currentTime - lastConnectionAttempt < RECONNECT_DELAY) {
    delay(100);  // Small delay to prevent CPU hogging
    return false;  // Not connected yet but still trying
  }
  
  // Ensure WiFi is still connected before attempting to reconnect
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected. Attempting to reconnect WiFi first.");
    WiFi.disconnect();
    delay(100);
    WiFi.begin(ssid, password);
    
    int wifiAttempts = 0;
    Serial.print("Reconnecting to WiFi");
    while (WiFi.status() != WL_CONNECTED && wifiAttempts < 10) {
      delay(500);
      Serial.print(".");
      wifiAttempts++;
    }
    
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi reconnection failed.");
      return false;
    }
    
    Serial.println("WiFi reconnected!");
  }
  
  // Attempt to reconnect to WebSocket
  return connectToWebSocket();
}

void setupI2S() {
  // Initialize I2S
  i2s_install();
  i2s_setpin();
  i2s_start(I2S_PORT);
  Serial.println("I2S initialized");
}

void goToLightSleep() {
  Serial.println("Going to light sleep - press button for instant streaming");
  
  // Configure button pin as wake-up source for light sleep
  gpio_wakeup_enable(BUTTON_PIN, GPIO_INTR_LOW_LEVEL); // Wake on button press (LOW)
  esp_sleep_enable_gpio_wakeup();
  
  // Turn off LED
  digitalWrite(LED_PIN, LOW);
  
  // Make sure serial messages finish
  Serial.flush();
  delay(50);
  
  // Enter light sleep
  Serial.println("Entering light sleep now");
  sleepMode = REGULAR_SLEEP;
  esp_light_sleep_start();
  
  // Execution continues here after waking up (unlike deep sleep)
  Serial.println("Woke up from light sleep!");
  
  // IMPORTANT: Check if button is still pressed after waking up
  // If it is, start streaming immediately
  if (digitalRead(BUTTON_PIN) == LOW) {
    Serial.println("Button is pressed - starting streaming immediately");
    digitalWrite(LED_PIN, HIGH);
    isStreaming = true;
    
    // Reset stream start time for timeout tracking
    // We'll do this in loop() but setting a flag here
    streamStarted = true;
  } else {
    Serial.println("Button was released too quickly - going back to sleep");
    goToLightSleep(); // Go back to sleep if button was released
  }
}

void prepareForLongSleep() {
  Serial.println("Preparing for extended light sleep");
  
  // Shut down WiFi to save power
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  btStop();
  
  // Clean up I2S
  i2s_stop(I2S_PORT);
  i2s_driver_uninstall(I2S_PORT);
  isStreaming = false;
  
  // Turn off LED
  digitalWrite(LED_PIN, LOW);
  
  // Configure button pin as wake-up source for light sleep
  gpio_wakeup_enable(BUTTON_PIN, GPIO_INTR_LOW_LEVEL); // Wake on button press (LOW)
  esp_sleep_enable_gpio_wakeup();
  
  // Make sure serial messages finish
  Serial.flush();
  delay(100);
  
  // Set flag to indicate we need full initialization on wake
  sleepMode = EXTENDED_SLEEP;
  
  // Triple blink to indicate extended sleep
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }
  
  // Go to light sleep - will wake up when button is pressed
  Serial.println("Entering extended light sleep now");
  esp_light_sleep_start();
  
  // Code will continue here when device wakes up
  Serial.println("Woke up from extended light sleep!");
}

void setup() {
  Serial.begin(115200);
  delay(100);
  
  bootCount++;
  Serial.println("Boot number: " + String(bootCount));
  
  // Set up pins
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  digitalWrite(LED_PIN, LOW);
  
  // Check if this is first boot or wake from extended light sleep where we need reinitialization
  if (firstBoot || sleepMode == EXTENDED_SLEEP) {
    firstBoot = false;
    
    // First boot or wake needing full initialization
    Serial.println("First boot or wake needing full initialization");
    
    // Initialize all required components
    setupI2S();
    setupWiFiAndWebSocket();
    
    // Blink LED twice to indicate ready state
    for (int i = 0; i < 2; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(100);
      digitalWrite(LED_PIN, LOW);
      delay(100);
    }
    
    // Go to light sleep to wait for button press with low power
    goToLightSleep();
  }
}

void loop() {
  static unsigned long streamStartTime = 0;
  static size_t bytesIn = 0;
  
  // Check if streaming just started
  if (isStreaming && streamStarted) {
    streamStartTime = millis();
    streamStarted = false;
    Serial.println("Stream started at: " + String(streamStartTime));
  }
  
  // Check button state - stop streaming immediately when released
  if (isStreaming && digitalRead(BUTTON_PIN) == HIGH) {
    Serial.println("Button released - stopping streaming instantly");
    isStreaming = false;
    streamStartTime = 0;
    
    // Turn off LED
    digitalWrite(LED_PIN, LOW);
    
    // Go back to light sleep
    goToLightSleep();
    return;
  }
  
  // Check streaming time limit
  if (isStreaming && streamStartTime > 0 && (millis() - streamStartTime) > MAX_STREAM_TIME) {
    Serial.println("Max streaming time reached");
    isStreaming = false;
    streamStartTime = 0;
    
    // Go back to light sleep
    digitalWrite(LED_PIN, LOW);
    goToLightSleep();
    return;
  }
  
  // Check if WiFi is still connected
  if (isStreaming && WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi connection lost - attempting to reconnect");
    
    // If WiFi reconnection fails, go to extended light sleep
    if (!reconnectWebSocket()) {
      prepareForLongSleep();
      // After waking up, we need to reinitialize
      setup();
      return;
    }
  }
  
  // Check if WebSocket is connected while streaming
  if (isStreaming && !isWebSocketConnected) {
    Serial.println("WebSocket disconnected - attempting to reconnect");
    
    // Blink LED to indicate reconnection attempt
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    
    // Attempt to reconnect
    if (!reconnectWebSocket()) {
      // If we've hit max attempts, go to extended light sleep
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        Serial.println("Maximum reconnection attempts reached");
        digitalWrite(LED_PIN, LOW);  // Turn off LED
        prepareForLongSleep();
        // After waking up, we need to reinitialize
        setup();
        return;
      }
      // Otherwise, continue trying
    } else {
      // Reconnected successfully
      digitalWrite(LED_PIN, HIGH);  // Turn LED back on
    }
  }
  
  // Stream audio when button is pressed and connection is active
  if (isStreaming && isWebSocketConnected && digitalRead(BUTTON_PIN) == LOW) {
    esp_err_t result = i2s_read(I2S_PORT, &sBuffer, bufferLen, &bytesIn, 0);
    
    if (result == ESP_OK && bytesIn > 0) {
      // Send audio data
      bool sendSuccess = client.sendBinary((const char*)sBuffer, bytesIn);
      
      if (!sendSuccess) {
        Serial.println("Failed to send audio data - WebSocket might be disconnected");
        isWebSocketConnected = false;
        // We'll attempt to reconnect in the next loop iteration
      }
    }
  }
  
  // Poll WebSocket events
  if (isWebSocketConnected) {
    client.poll();
  }
  
  // Very small delay to prevent watchdog reset
  delay(1);
  
  // If sending audio data failed and we're not trying to reconnect
  if (isStreaming && !isWebSocketConnected && reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    Serial.println("Failed to reconnect WebSocket after maximum attempts");
    isStreaming = false;
    
    // Don't go to deep sleep, reinitialize and go to light sleep
    prepareForLongSleep();
    // After waking up, we need to reinitialize
    setup();
    return;
  }
}