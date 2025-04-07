# Voice-Controlled IR Remote System

A voice-controlled system designed to help elderly people interact with electronic devices through natural language commands in Malayalam. This system replaces traditional remote controls with voice commands, making technology more accessible.

## System Overview

This project consists of two physical ESP32 devices that communicate through a cloud service:

1. **Voice Input Device**: Captures voice commands, sends audio to the cloud for processing
2. **IR Output Device**: Receives commands from the cloud and transmits appropriate IR signals to devices

```
Voice Input → Cloud Processing → IR Output → Electronic Device
```

## Features

- **Multilingual Support**: Optimized for Malayalam language voice commands
- **Natural Language Understanding**: Process conversational commands rather than strict syntax
- **Long Battery Life**: Optimized for 7+ days on a single charge with regular use
- **Wireless Communication**: No physical connection between devices
- **Extendable**: Can be programmed to control any IR-compatible device

## Hardware Components

### Voice Input Device
- ESP32 microcontroller
- INMP441 I2S MEMS Microphone
- Speaker (MAX98357A amplifier)
- 5000mAh LiPo battery
- Charging circuit (TP4056)
- Pushbutton for activation

### IR Output Device
- ESP32 microcontroller
- IR LED (940nm)
- NPN transistor (2N2222A)
- 100Ω resistor

## Cloud Service

The system uses a backend service deployed on Render.com with these features:
- Speech-to-text conversion using Google Cloud Speech API
- Malayalam to English translation
- Natural language processing to extract commands
- Device control command formatting

## Setup Instructions

### Cloud Backend Setup
1. Clone this repository
2. Create a Google Cloud Platform account
3. Enable Speech-to-Text and Translation APIs
4. Create a service account and download credentials
5. Deploy the Flask application to Render.com
6. Set up environment variables on Render:
   - `GOOGLE_APPLICATION_CREDENTIALS` (upload the JSON file)

### Voice Input Device
1. Flash the ESP32 with the provided code
2. Update WiFi credentials and server endpoint
3. Connect components according to the wiring diagram
4. Test with voice commands

### IR Output Device
1. Flash the ESP32 with the provided code
2. Update WiFi credentials
3. Connect components according to the wiring diagram
4. Program IR codes for specific devices

## Usage

1. Press the button on the Voice Input Device
2. Speak a command in Malayalam
3. Wait for cloud processing (typically 2-3 seconds)
4. The IR Output Device will transmit the appropriate signal

### Example Commands

| Malayalam Command | English Equivalent | Action |
|-------------------|-------------------|--------|
| ടിവി ഓൺ ആക്കൂ | Turn on TV | Sends TV power signal |
| ശബ്ദം കൂട്ടുക | Increase volume | Sends volume up signal |
| ചാനൽ മാറ്റുക | Change channel | Sends channel change signal |

## Battery Life

The Voice Input Device uses a 5000mAh battery optimized for low power consumption:
- ~100mA average current during operation
- Deep sleep between commands (~20μA)
- Estimated 7-9 days of battery life with ~50 daily commands

## Future Enhancements

- Support for additional languages
- Local speech processing to reduce latency
- Bluetooth connectivity option
- Home automation integration
- Custom wake word instead of button press

## License

This project is released under the MIT License.
