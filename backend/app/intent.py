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
import logging

import httpx
from pydantic import ValidationError

log = logging.getLogger(__name__)

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
                        "Always set this. tv = the television. stb = the "
                        "set-top box, which the household may call the modem, "
                        "the box, Asianet, or ബോക്സ്. If she did not name a "
                        "device: volume is tv, channel is stb."
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
    # `device` is required on purpose. Left optional, the model omits it even
    # when she plainly said "TV" -- and the resolver has no safe default for
    # power (she could mean either box), so it refuses and she hears "I didn't
    # understand" for a perfectly clear request. Forcing the field makes the
    # model commit, and the prompt tells it how to break ties.
    "required": ["device", "action", "confidence"],
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
- Always fill in `device`, on every action. If she says "TV" or "ടിവി" it is tv. If she says "modem", "box", "ബോക്സ്" or a channel name it is stb. When she names a device once and then asks for something else in the same breath, that device still applies -- "TV ഓണാക്കുവോ... and sound-ഉം കൂട്ടണേ" is tv for both actions.
- If she genuinely named no device: volume is tv, channel is stb.
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
        # Generous: reasoning tokens (if enabled) are drawn from this budget
        # too, and running out produces an empty response with no tool call
        # rather than an error.
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": build_system_prompt(catalog)},
            {"role": "user", "content": transcript},
        ],
        "tools": [TOOL],
        "tool_choice": {"type": "function", "function": {"name": "control_devices"}},
        # ALWAYS sent, including as an explicit null. Sarvam defaults this to
        # "medium", and the docs say it is disabled only by setting it to None
        # -- omitting the key leaves reasoning switched on. That cost us an
        # empty response with no tool call, which looked exactly like the model
        # failing to understand her.
        "reasoning_effort": settings.chat_reasoning_effort,
    }

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
        choice = body["choices"][0]
        message = choice["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            # No tool call despite tool_choice being forced. finish_reason and
            # usage are the two things that distinguish the causes:
            #   "length" + large completion_tokens -> ran out of budget, very
            #     likely reasoning tokens (see reasoning_effort above)
            #   "stop" + prose in content          -> model ignored tool_choice
            log.warning(
                "no tool_call: finish_reason=%s usage=%s reasoning=%r content=%r",
                choice.get("finish_reason"),
                body.get("usage"),
                (message.get("reasoning_content") or "")[:120],
                (message.get("content") or "")[:200],
            )
            return [Intent()]
        args = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        log.warning("unparseable tool_call (%s): %s", exc, str(body)[:300])
        return [Intent()]

    raw = args.get("actions")
    if isinstance(args, dict) and raw is None and "action" in args:
        raw = [args]          # tolerate a bare single action
    if not isinstance(raw, list):
        log.warning("tool_call had no actions array: %s", str(args)[:300])
        return [Intent()]

    intents: list[Intent] = []
    for item in raw:
        try:
            intents.append(Intent.model_validate(item))
        except ValidationError as exc:
            # Still discarded rather than repaired -- a guessed command is worse
            # than none -- but no longer silently. Without this line an
            # out-of-enum confidence value looks identical to a refusal.
            log.warning("dropped invalid action %s: %s", item, exc.errors()[:2])

    if not intents:
        return [Intent()]

    log.info("intents: %s", [(i.action.value, i.device, i.confidence) for i in intents])
    return intents


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
