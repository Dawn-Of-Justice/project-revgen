/*
 * Copy to secrets.h and fill in. secrets.h is gitignored.
 *
 * This repo is public. A Groq key was committed in .env in April 2025 and had
 * to be revoked -- that is the reason this file exists rather than putting
 * credentials directly in emitter.ino.
 *
 *     cp secrets.example.h secrets.h
 *
 * Note the credentials still end up in the ESP32's flash, readable by anyone
 * with physical access and a USB cable. That is an accepted risk here: someone
 * standing in her living room can press the television's power button anyway.
 */

#pragma once

// HiveMQ Cloud cluster, TLS on 8883.
#define MQTT_HOST_STR "xxxxxxxx.s1.eu.hivemq.cloud"
#define MQTT_PORT_NUM 8883
#define MQTT_TLS_ON   true

// Access Management -> Credentials, needs publish + subscribe.
#define MQTT_USER_STR "revgen-emitter"
#define MQTT_PASS_STR ""

// Paste the broker's issuing root CA PEM here, obtained from the provider.
// TLS refuses to start with an empty CA. Do not paste the broker leaf cert.
static const char MQTT_CA_CERT[] = R"PEM()PEM";
