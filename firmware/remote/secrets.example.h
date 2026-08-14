/*
 * Copy to secrets.h and fill in. secrets.h is gitignored — this repo is public.
 *
 *     cp secrets.example.h secrets.h
 *
 * The device token also ends up readable from flash by anyone with physical
 * access and a USB cable. Accepted: someone standing in her living room can
 * press the television's power button anyway.
 */

#pragma once

// Deployed backend. Must be https.
#define BACKEND_URL   "https://project-revgen.fly.dev/command"

// Must match DEVICE_TOKEN in `fly secrets`. Sent as X-RevGen-Token.
#define DEVICE_TOKEN  ""

// Password for over-the-air updates. Not the WiFi password.
#define OTA_PASSWORD  ""
