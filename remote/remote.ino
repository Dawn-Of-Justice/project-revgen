#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <driver/i2s.h>

// WiFi credentials
const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";

// OpenAI API configuration
const char* openai_api_key = "API_KEY";
const char* websocket_host = "api.openai.com";
const int websocket_port = 443;
const char* websocket_path = "/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01";


// I2S pins for INMP441
#define I2S_SD 34
#define I2S_WS 25
#define I2S_SCK 26
#define I2S_PORT I2S_NUM_0

// Audio configuration
#define SAMPLE_RATE 16000  // OpenAI Realtime expects 16kHz
#define DMA_BUF_COUNT 4
#define DMA_BUF_LEN 512
#define AUDIO_BUFFER_SIZE 1024

// WebSocket client
WebSocketsClient webSocket;

// Audio buffers
int32_t i2sBuffer[DMA_BUF_LEN];
int16_t pcmBuffer[DMA_BUF_LEN];

// Connection state
bool wsConnected = false;
bool sessionCreated = false;
bool audioStreamActive = false;

// Timing variables
unsigned long lastAudioSend = 0;
const unsigned long AUDIO_SEND_INTERVAL = 100; // Send audio every 100ms

// Function prototypes
void setupI2S();
void setupWebSocket();
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length);
void captureAndSendAudio();
void sendSessionUpdate();
void sendInputAudioBufferAppend(const String& base64Audio);
void sendInputAudioBufferCommit();
String base64Encode(const uint8_t* data, size_t length);

void setClock() {
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");

    Serial.print(F("Waiting for NTP time sync: "));
    time_t nowSecs = time(nullptr);
    while (nowSecs < 8 * 3600 * 2) {
        delay(500);
        Serial.print(F("."));
        yield();
        nowSecs = time(nullptr);
    }

    Serial.println();
    struct tm timeinfo;
    gmtime_r(&nowSecs, &timeinfo);
    Serial.print(F("Current time: "));
    Serial.print(asctime(&timeinfo));
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    delay(10);
  }
  delay(1000);
  
  Serial.println("\n\nESP32 OpenAI Realtime API Client");
  Serial.println("=================================");
  
  // Connect to WiFi first
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
      delay(500);
      Serial.print(".");
  }
  Serial.println("\nWiFi connected!");

  // Set the clock!
  setClock();
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nFailed to connect to WiFi. Restarting...");
    ESP.restart();
  }
  
  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  
  // Add delay before I2S setup
  delay(500);
  
  // Setup I2S for microphone
  setupI2S();
  
  // Setup WebSocket connection
  setupWebSocket();
  
  Serial.println("Setup complete!");
}

void loop() {
  webSocket.loop();
  
  // Capture and send audio periodically if connected
  if (wsConnected && sessionCreated && audioStreamActive) {
    unsigned long currentTime = millis();
    if (currentTime - lastAudioSend >= AUDIO_SEND_INTERVAL) {
      captureAndSendAudio();
      lastAudioSend = currentTime;
    }
  }
  
  // Small delay to prevent watchdog issues
  delay(1);
}

void setupI2S() {
  Serial.println("Setting up I2S for INMP441...");
  
  // Uninstall driver if it exists
  // i2s_driver_uninstall(I2S_PORT);
  
  // I2S configuration for INMP441
  const i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,  // INMP441 outputs 32-bit samples
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,   // INMP441 outputs on left channel
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = 0,
    .dma_buf_count = DMA_BUF_COUNT,
    .dma_buf_len = DMA_BUF_LEN,
    .use_apll = false
  };
  
  // I2S pin configuration
  const i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };
  
  // Install I2S driver
  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("Failed to install I2S driver: %s\n", esp_err_to_name(err));
    return;
  }
  
  // Set I2S pins
  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("Failed to set I2S pins: %s\n", esp_err_to_name(err));
    return;
  }
  
  // Clear DMA buffer
  i2s_zero_dma_buffer(I2S_PORT);
  
  Serial.println("I2S setup complete!");
}

void setupWebSocket() {
    Serial.println("Setting up WebSocket connection...");

    // Build the custom headers string
    String headers = "Authorization: Bearer ";
    headers += openai_api_key;
    headers += "\r\nOpenAI-Beta: realtime=v1";

    // 1. Set the custom headers FIRST using the correct function
    webSocket.setExtraHeaders(headers.c_str());

    // 2. Begin the connection. The library will automatically use the headers
    //    you just set.
    webSocket.beginSslWithBundle(websocket_host, websocket_port, websocket_path, NULL, 0);

    // --- The rest of the function is the same ---
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
    webSocket.enableHeartbeat(15000, 3000, 2);

    Serial.println("WebSocket setup complete!");
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("WebSocket disconnected!");
      wsConnected = false;
      sessionCreated = false;
      audioStreamActive = false;
      break;
      
    case WStype_CONNECTED:
      Serial.println("WebSocket connected!");
      wsConnected = true;
      break;
      
    case WStype_TEXT: {
      // Parse JSON response
      DynamicJsonDocument doc(2048);
      DeserializationError error = deserializeJson(doc, payload, length);
      
      if (!error) {
        const char* msgType = doc["type"];
        
        if (strcmp(msgType, "session.created") == 0) {
          Serial.println("Session created successfully!");
          sessionCreated = true;
          
          // Send session update to configure audio
          delay(100);
          sendSessionUpdate();
          
          // Start audio streaming after a short delay
          delay(500);
          audioStreamActive = true;
          Serial.println("Ready to capture audio!");
        }
        else if (strcmp(msgType, "session.updated") == 0) {
          Serial.println("Session updated!");
        }
        else if (strcmp(msgType, "input_audio_buffer.speech_started") == 0) {
          Serial.println("Speech detected!");
        }
        else if (strcmp(msgType, "input_audio_buffer.speech_stopped") == 0) {
          Serial.println("Speech stopped!");
        }
        else if (strcmp(msgType, "response.text.delta") == 0) {
            const char* transcript = doc["delta"];
            if (transcript) {
                Serial.print(transcript);
            }
        }
        else if (strcmp(msgType, "response.text.done") == 0) {
            Serial.println(); // Move to the next line for the next response
        }
        else if (strcmp(msgType, "error") == 0) {
          Serial.print("Error: ");
          JsonObject error = doc["error"];
          Serial.println(error["message"].as<const char*>());
        }
        else {
          Serial.print("Received event: ");
          Serial.println(msgType);
        }
      } else {
        Serial.print("JSON parse error: ");
        Serial.println(error.c_str());
      }
      break;
    }
    
    case WStype_ERROR:
      Serial.printf("WebSocket error!\n");
      break;
      
    case WStype_PING:
      Serial.println("Ping");
      break;
      
    case WStype_PONG:
      Serial.println("Pong");
      break;
      
    default:
      break;
  }
}

void sendSessionUpdate() {
  Serial.println("Sending session update...");
 
  DynamicJsonDocument doc(1024);
  doc["type"] = "session.update";
 
  JsonObject session = doc.createNestedObject("session");
 
  // Set modalities
  JsonArray modalities = session.createNestedArray("modalities");
  modalities.add("text");
  // modalities.add("audio");
 
  // Instructions
  session["instructions"] = "You are a helpful assistant. Please respond concisely.";
  // session["voice"] = "alloy";
 
  // Simplified Audio Format Section
  session["input_audio_format"] = "pcm16";
  session["output_audio_format"] = "pcm16";
 
  // Turn detection (VAD)
  JsonObject turnDetection = session.createNestedObject("turn_detection");
  turnDetection["type"] = "server_vad";
  turnDetection["threshold"] = 0.1;
  turnDetection["prefix_padding_ms"] = 300;
  turnDetection["silence_duration_ms"] = 500;
 
  String jsonString;
  serializeJson(doc, jsonString);
 
  if (webSocket.sendTXT(jsonString)) {
    Serial.println("Session update sent successfully!");
  } else {
    Serial.println("Failed to send session update!");
  }
}

void captureAndSendAudio() {
  size_t bytesRead = 0;
 
  // Read from I2S
  esp_err_t result = i2s_read(I2S_PORT, i2sBuffer, sizeof(i2sBuffer), &bytesRead, 10);
 
  if (result == ESP_OK && bytesRead > 0) {
    // Calculate number of samples
    int samples = bytesRead / sizeof(int32_t);
   
    // Convert 32-bit samples to 16-bit PCM
    for (int i = 0; i < samples; i++) {
      // Shift right by 8 to convert 24-bit audio to 16-bit
      pcmBuffer[i] = (int16_t)(i2sBuffer[i] >> 8);
    }

    // --- START OF DEBUGGING CODE ---
    // Calculate the average audio level for this chunk of audio
    long totalMagnitude = 0;
    for (int i = 0; i < samples; i++) {
      totalMagnitude += abs(pcmBuffer[i]);
    }
    int averageMagnitude = samples > 0 ? totalMagnitude / samples : 0;
    // Serial.printf("Read %d bytes | Avg. Audio Level: %d\n", bytesRead, averageMagnitude);
    // --- END OF DEBUGGING CODE ---
   
    // Base64 encode the PCM data
    String base64Audio = base64Encode((uint8_t*)pcmBuffer, samples * sizeof(int16_t));
   
    // Send to OpenAI
    if (base64Audio.length() > 0) {
      sendInputAudioBufferAppend(base64Audio);
    }
  } else if (bytesRead == 0) {
      // Also good to know if we are reading 0 bytes
      Serial.println("Read 0 bytes from I2S.");
  }
}

void sendInputAudioBufferAppend(const String& base64Audio) {
  DynamicJsonDocument doc(8192);
  doc["type"] = "input_audio_buffer.append";
  doc["audio"] = base64Audio;
  
  String jsonString;
  serializeJson(doc, jsonString);
  
  webSocket.sendTXT(jsonString);
}

void sendInputAudioBufferCommit() {
  StaticJsonDocument<64> doc;
  doc["type"] = "input_audio_buffer.commit";
  
  String jsonString;
  serializeJson(doc, jsonString);
  webSocket.sendTXT(jsonString);
}

// Simple base64 encoding function
String base64Encode(const uint8_t* data, size_t length) {
  const char* base64_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  String encoded;
  encoded.reserve(((length + 2) / 3) * 4);
  
  for (size_t i = 0; i < length; i += 3) {
    uint32_t b = (data[i] << 16) | 
                 ((i + 1 < length) ? (data[i + 1] << 8) : 0) | 
                 ((i + 2 < length) ? data[i + 2] : 0);
    
    encoded += base64_chars[(b >> 18) & 0x3F];
    encoded += base64_chars[(b >> 12) & 0x3F];
    encoded += (i + 1 < length) ? base64_chars[(b >> 6) & 0x3F] : '=';
    encoded += (i + 2 < length) ? base64_chars[b & 0x3F] : '=';
  }
  
  return encoded;
}