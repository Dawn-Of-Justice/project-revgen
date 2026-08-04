"""Transcript -> Intent, via Sarvam chat completions.

Two decisions worth knowing about:

1. We use *forced tool calling* (`tool_choice` pinned to our function) rather
   than asking for JSON in the prompt. The model cannot reply with prose, and
   the arguments arrive already shaped. Anything that still fails validation is
   discarded rather than repaired -- a guessed command is worse than none.

2. `reasoning_effort` is disabled. Sarvam defaults it to "medium", which is
   latency we would be paying for on what is really a small classification over
   a fixed vocabulary. The 1.2s confirmation budget is tight and this is the
   cheapest place to buy time back.
"""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from .catalog import Catalog
from .config import settings
from .schemas import Intent

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
                "device": {
                    "type": "string",
                    "enum": ["tv", "stb"],
                    "description": (
                        "tv = the television. stb = the set-top box, which the "
                        "household may call the modem, the box, Asianet, or "
                        "ബോക്സ്. Omit only if truly unclear."
                    ),
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "power_on", "power_off", "volume_up", "volume_down",
                        "channel_up", "channel_down", "channel_set", "unknown",
                    ],
                    "description": (
                        "The goal, not a button. power_on means 'end up switched "
                        "on'. Use unknown for anything that is not a request to "
                        "control the TV or box."
                    ),
                },
                "channel": {
                    "type": "string",
                    "description": "Channel name, only with channel_set. Must be one of the known channels.",
                },
                "steps": {
                    "type": "integer",
                    "description": "How many volume presses. 1 normally; 3 for 'a lot louder'.",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "low"],
                    "description": (
                        "high only if you are sure. Use low for background "
                        "speech, half-sentences, or anything ambiguous."
                    ),
                },
    },
    "required": ["action", "confidence"],
}

TOOL = {
    "type": "function",
    "function": {
        "name": "control_devices",
        "description": (
            "Carry out a spoken remote-control request. One utterance may "
            "contain several actions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": ACTION_SCHEMA,
                    "description": "The actions requested, in the order she said them.",
                }
            },
            "required": ["actions"],
        },
    },
}


def build_system_prompt(catalog: Catalog) -> str:
    channels = ", ".join(catalog.channel_names()) or "(none configured yet)"
    return f"""You map a spoken utterance from an elderly Malayalam speaker onto one or more remote-control actions.

The speech has already been transcribed and may be code-mixed Malayalam and English, for example "TV ഓൺ ആക്കൂ" or "sound കൂട്ടൂ". Transcription is imperfect: channel and brand names are often garbled, so match them to the nearest known channel rather than rejecting them.

Known channels: {channels}

Rules:
- One utterance often contains more than one request. "TV ഓണാക്കുവോ... and sound-ഉം കൂടെ കൂട്ടണേ കുറച്ച്" is two actions: power_on for the tv, then volume_up with steps 2. Return them in the order she said them.
- Politeness, hesitation and filler are normal speech, not uncertainty. "ഓണാക്കുവോ?", "ഉം", "മോനേ" and similar are still clear requests -- keep confidence high.
- Softeners map to step counts: "കുറച്ച്" (a little) is 2, plain "കൂട്ടൂ" is 1, "ഒരുപാട്" (a lot) is 4.
- She names the device most of the time. If she says "modem", "box", "ബോക്സ്" or a channel name, that is the set-top box (stb).
- Volume without a named device is the TV.
- If the utterance is not a request to control the TV or box -- ordinary conversation, someone else talking, audio from the television itself -- return a single action "unknown" with confidence "low". This matters: the microphone sits in a room with a loud TV, so refusing is the common correct answer.
- Never invent a channel that is not listed.
- Prefer confidence "low" when unsure. A wrong command is worse than no command, because she has no way to undo one."""


class IntentError(Exception):
    pass


async def extract(transcript: str, catalog: Catalog) -> list[Intent]:
    if settings.offline:
        return _offline_intent(transcript)

    if not settings.sarvam_api_key:
        raise IntentError("SARVAM_API_KEY is not set")

    payload: dict = {
        "model": settings.chat_model,
        "temperature": 0.1,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": build_system_prompt(catalog)},
            {"role": "user", "content": transcript},
        ],
        "tools": [TOOL],
        "tool_choice": {"type": "function", "function": {"name": "control_devices"}},
    }
    if settings.chat_reasoning_effort:
        payload["reasoning_effort"] = settings.chat_reasoning_effort

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{settings.sarvam_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.sarvam_api_key}",
                    "api-subscription-key": settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.RequestError as exc:
            raise IntentError(f"network error talking to Sarvam: {exc}") from exc

    if response.status_code != 200:
        raise IntentError(f"Sarvam returned {response.status_code}: {response.text[:300]}")

    return _parse(response.json())


def _parse(body: dict) -> list[Intent]:
    """Tool arguments -> validated intents. Anything malformed is dropped.

    A guessed command is worse than none, so nothing here repairs bad output --
    an action that fails validation is discarded and the resolver refuses.
    """
    try:
        calls = body["choices"][0]["message"].get("tool_calls") or []
        if not calls:
            return [Intent()]  # unknown / low -- resolver will refuse
        args = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        return [Intent()]

    raw = args.get("actions")
    if isinstance(args, dict) and raw is None and "action" in args:
        raw = [args]          # tolerate a bare single action
    if not isinstance(raw, list):
        return [Intent()]

    intents: list[Intent] = []
    for item in raw:
        try:
            intents.append(Intent.model_validate(item))
        except ValidationError:
            continue

    return intents or [Intent()]


def _offline_intent(transcript: str) -> list[Intent]:
    """Keyword stub so the full chain runs with no API key.

    Only for wiring tests -- it is not a fallback and never ships.
    """
    from .schemas import Action, Device

    text = transcript.lower()
    found: list[Intent] = []
    if "off" in text:
        found.append(Intent(device=Device.TV, action=Action.POWER_OFF, confidence="high"))
    elif "on" in text:
        found.append(Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"))
    if "up" in text or "sound" in text:
        found.append(Intent(device=Device.TV, action=Action.VOLUME_UP, confidence="high"))
    return found or [Intent()]
