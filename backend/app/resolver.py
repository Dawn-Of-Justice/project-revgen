"""Intents + state -> button sequence. No model, no I/O, no clock of its own.

This is the layer that decides whether IR actually fires, so it is deliberately
pure: `resolve()` takes everything it needs as arguments and returns a Plan.
That makes every safety rule below a two-line unit test.

The rules exist because IR is open-loop. Nothing here can observe the room, so
the job is not to be clever -- it is to refuse to make things worse.

It takes a *list* of intents because real speech is compound. "TV ഓണാക്കുവോ...
and sound-ഉം കൂടെ കൂട്ടണേ കുറച്ച്" is one utterance and two actions, and that
is how she actually talks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .catalog import BrokenCode, Catalog
from .schemas import Action, DelayStep, Device, Intent, Phrase, Plan, Step


@dataclass
class State:
    """Everything we are allowed to believe. Deliberately tiny.

    We do NOT track whether the TV is on, because we cannot know it. We track
    only what we ourselves did and when -- which we do know for certain.
    """

    last_power_sent: dict[str, float] = field(default_factory=dict)

    def note_power(self, device: Device, now: float) -> None:
        self.last_power_sent[device.value] = now

    def seconds_since_power(self, device: Device, now: float) -> float:
        last = self.last_power_sent.get(device.value)
        return float("inf") if last is None else now - last


def resolve(
    intents: list[Intent],
    catalog: Catalog,
    state: State,
    now: float,
    *,
    debounce_s: float,
    max_volume_steps: int,
    digit_gap_ms: int,
    max_actions: int = 3,
    post_power_delay_ms: int = 2500,
    inter_action_delay_ms: int = 250,
) -> Plan:
    plan_id = str(uuid.uuid4())

    if not intents:
        return Plan(id=plan_id, phrases=[Phrase(key="err.not_understood")])

    steps: list[Step] = []
    phrases: list[Phrase] = []
    refusals: list[Phrase] = []

    for index, intent in enumerate(intents[:max_actions]):
        part = _resolve_one(
            intent, catalog, state, now, debounce_s, max_volume_steps, digit_gap_ms
        )

        if not part.steps:
            refusals.extend(part.phrases)
            continue

        if steps:
            # A device that was just told to power on is not listening yet.
            # Firing the next command into a booting TV is how "turn it on and
            # turn it up" ends with the volume never changing.
            gap = (
                post_power_delay_ms
                if _is_power_on(intents[index - 1])
                else inter_action_delay_ms
            )
            steps.append(DelayStep(ms=gap))

        steps.extend(part.steps)
        phrases.extend(part.phrases)

    # Partial success is still success: if the TV power was debounced but the
    # volume change went through, say what happened rather than apologising.
    if not phrases:
        phrases = refusals[:1] or [Phrase(key="err.not_understood")]

    return Plan(id=plan_id, steps=steps, phrases=phrases)


def _is_power_on(intent: Intent) -> bool:
    return intent.action is Action.POWER_ON


# --- single action ------------------------------------------------------


def _resolve_one(
    intent: Intent,
    catalog: Catalog,
    state: State,
    now: float,
    debounce_s: float,
    max_volume_steps: int,
    digit_gap_ms: int,
) -> Plan:
    plan_id = ""  # sub-plans are merged; only the parent id matters

    def refuse(key: str, **args: str) -> Plan:
        return Plan(id=plan_id, steps=[], phrases=[Phrase(key=key, args=args)])

    if intent.action is Action.UNKNOWN or intent.confidence != "high":
        return refuse("err.not_understood")

    if intent.action is Action.LEARNED:
        entry = catalog.raw.get("learned", {}).get(intent.command_key)
        if entry is None:
            return refuse("err.not_understood")
        from .schemas import IRStep
        key = entry["device"]
        if entry["behavior"] == "power_toggle":
            if now - state.last_power_sent.get(key, float("-inf")) < debounce_s:
                return refuse("err.too_soon")
            state.last_power_sent[key] = now
        return Plan(id=plan_id, steps=[IRStep.model_validate(entry["code"])],
                    phrases=[Phrase(key="learned.sent")])

    device = intent.device or _default_device(intent.action)
    if device is None:
        return refuse("err.not_understood")

    try:
        if intent.action in (Action.POWER_ON, Action.POWER_OFF):
            return _power(intent, device, catalog, state, now, debounce_s, plan_id)

        if intent.action in (Action.VOLUME_UP, Action.VOLUME_DOWN):
            return _volume(intent, device, catalog, max_volume_steps, plan_id)

        if intent.action in (Action.CHANNEL_UP, Action.CHANNEL_DOWN):
            button = "channel_up" if intent.action is Action.CHANNEL_UP else "channel_down"
            return Plan(
                id=plan_id,
                steps=[catalog.step(device, button)],
                phrases=[Phrase(key=f"{device.value}.{button}")],
            )

        if intent.action is Action.CHANNEL_SET:
            return _channel_set(intent, device, catalog, digit_gap_ms, plan_id)

    except BrokenCode:
        # A code we know is wrong. Saying nothing happened is honest; firing it
        # would change the channel when she asked for something else entirely.
        return refuse("err.broken_code")
    except KeyError:
        return refuse("err.not_understood")

    return refuse("err.not_understood")


def _power(
    intent: Intent,
    device: Device,
    catalog: Catalog,
    state: State,
    now: float,
    debounce_s: float,
    plan_id: str,
) -> Plan:
    want_on = intent.action is Action.POWER_ON
    discrete_name = "power_on" if want_on else "power_off"
    phrase = Phrase(key=f"{device.value}.{discrete_name}")

    # Best case: a discrete code exists, so the command is idempotent. Firing
    # it twice is harmless, which means no debounce and no state at all.
    if catalog.has_discrete(device, discrete_name):
        return Plan(id=plan_id, steps=[catalog.step(device, discrete_name)],
                    phrases=[phrase])

    # Otherwise we only have a toggle, and the dominant real-world failure is
    # her repeating herself while the TV is still waking up. The second toggle
    # would undo the first, so suppress it and tell her to wait.
    if state.seconds_since_power(device, now) < debounce_s:
        return Plan(id=plan_id, steps=[], phrases=[Phrase(key="err.too_soon")])

    state.note_power(device, now)
    return Plan(id=plan_id, steps=[catalog.step(device, "power")], phrases=[phrase])


def _volume(
    intent: Intent, device: Device, catalog: Catalog, max_steps: int, plan_id: str
) -> Plan:
    button = "volume_up" if intent.action is Action.VOLUME_UP else "volume_down"
    steps_n = max(1, min(intent.steps, max_steps))

    steps: list[Step] = []

    # If a discrete unmute exists, lead with it: a muted TV looks broken, and
    # "louder" is exactly what she would say to fix it. We never send a *toggle*
    # mute here -- that would mute an unmuted TV, which is strictly worse.
    if catalog.has_discrete(device, "mute_off"):
        steps.append(catalog.step(device, "mute_off"))
        steps.append(DelayStep(ms=120))

    for i in range(steps_n):
        if i:
            steps.append(DelayStep(ms=120))
        steps.append(catalog.step(device, button))

    return Plan(id=plan_id, steps=steps,
                phrases=[Phrase(key=f"{device.value}.{button}")])


def _channel_set(
    intent: Intent, device: Device, catalog: Catalog, digit_gap_ms: int, plan_id: str
) -> Plan:
    if not intent.channel:
        return Plan(id=plan_id, steps=[], phrases=[Phrase(key="err.not_understood")])

    number = catalog.channel_number(intent.channel)
    if number is None:
        return Plan(id=plan_id, steps=[], phrases=[Phrase(key="err.unknown_channel")])

    # Absolute entry, never relative. Digits do not require knowing the current
    # channel, which is the whole reason we prefer them over channel_up.
    steps: list[Step] = []
    for i, digit in enumerate(number):
        if i:
            steps.append(DelayStep(ms=digit_gap_ms))
        steps.append(catalog.step(device, f"digit_{digit}"))

    return Plan(
        id=plan_id,
        steps=steps,
        phrases=[Phrase(key="stb.channel_set", args={"channel": intent.channel})],
    )


def _default_device(action: Action) -> Device | None:
    """If she did not name a device, pick the one she meant.

    Volume goes to the TV on purpose: with the STB feeding it over HDMI, the TV
    is the master gain. Two volume controls fighting each other is a classic
    source of "the sound doesn't work".
    """
    if action in (Action.VOLUME_UP, Action.VOLUME_DOWN):
        return Device.TV
    if action in (Action.CHANNEL_UP, Action.CHANNEL_DOWN, Action.CHANNEL_SET):
        return Device.STB
    return None
