"""Every safety rule, one test each.

The resolver is pure, so none of this needs a network, a broker, or hardware.
This is the component where correctness is cheapest to guarantee, which is
exactly why it holds all the rules that can hurt her.
"""

from __future__ import annotations

import pytest

from app.catalog import Catalog
from app.config import settings
from app.resolver import State, resolve
from app.schemas import Action, Device, Intent

DEBOUNCE = 8.0


@pytest.fixture
def catalog() -> Catalog:
    return Catalog.load(settings.catalog_path)


def run(intent: Intent, catalog: Catalog, state: State, now: float = 1000.0):
    return run_many([intent], catalog, state, now)


def run_many(intents: list[Intent], catalog: Catalog, state: State, now: float = 1000.0):
    return resolve(
        intents,
        catalog,
        state,
        now=now,
        debounce_s=DEBOUNCE,
        max_volume_steps=5,
        digit_gap_ms=300,
    )


def ir_count(plan) -> int:
    return sum(1 for s in plan.steps if s.type == "ir")


# --- refusing to act ----------------------------------------------------


def test_low_confidence_fires_nothing(catalog):
    plan = run(Intent(device=Device.TV, action=Action.POWER_ON, confidence="low"),
               catalog, State())
    assert not plan.fires_ir
    assert plan.phrase_key == "err.not_understood"


def test_unknown_action_fires_nothing(catalog):
    plan = run(Intent(action=Action.UNKNOWN, confidence="high"), catalog, State())
    assert not plan.fires_ir


def test_background_speech_pattern_is_refused(catalog):
    """The mic sits in a room with a loud TV. Refusing is the common correct answer."""
    plan = run(Intent(action=Action.UNKNOWN, confidence="low"), catalog, State())
    assert plan.steps == []


# --- the debounce, i.e. the reason this project works -------------------


def test_first_power_command_fires(catalog):
    plan = run(Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"),
               catalog, State())
    assert plan.fires_ir


def test_repeat_within_window_is_suppressed(catalog):
    state = State()
    intent = Intent(device=Device.TV, action=Action.POWER_ON, confidence="high")

    first = run(intent, catalog, state, now=1000.0)
    second = run(intent, catalog, state, now=1003.0)

    assert first.fires_ir
    assert not second.fires_ir, "second toggle would turn the TV back off"
    assert second.phrase_key == "err.too_soon"


def test_repeat_after_window_fires_again(catalog):
    state = State()
    intent = Intent(device=Device.TV, action=Action.POWER_ON, confidence="high")

    run(intent, catalog, state, now=1000.0)
    later = run(intent, catalog, state, now=1000.0 + DEBOUNCE + 0.1)

    assert later.fires_ir


def test_debounce_is_per_device(catalog):
    state = State()
    run(Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"),
        catalog, state, now=1000.0)
    stb = run(Intent(device=Device.STB, action=Action.POWER_ON, confidence="high"),
              catalog, state, now=1001.0)
    assert stb.fires_ir, "the box is a separate device and should not be blocked"


# --- volume -------------------------------------------------------------


def test_volume_defaults_to_tv(catalog):
    """The TV is the master gain with the box feeding it over HDMI."""
    plan = run(Intent(action=Action.VOLUME_UP, confidence="high"), catalog, State())
    assert plan.fires_ir
    assert plan.phrase_key == "tv.volume_up"


def test_volume_steps_are_capped(catalog):
    plan = run(Intent(device=Device.TV, action=Action.VOLUME_UP, steps=10,
                      confidence="high"), catalog, State())
    assert ir_count(plan) == 5


def test_volume_is_never_debounced(catalog):
    """Volume is relative and harmless to repeat -- only toggles need guarding."""
    state = State()
    intent = Intent(device=Device.TV, action=Action.VOLUME_UP, confidence="high")
    assert run(intent, catalog, state, now=1000.0).fires_ir
    assert run(intent, catalog, state, now=1000.5).fires_ir


# --- channels -----------------------------------------------------------


def test_unconfigured_channel_is_refused(catalog):
    plan = run(Intent(action=Action.CHANNEL_SET, channel="ഏഷ്യാനെറ്റ്",
                      confidence="high"), catalog, State())
    assert not plan.fires_ir
    assert plan.phrase_key == "err.unknown_channel"


def test_unknown_channel_name_is_refused(catalog):
    plan = run(Intent(action=Action.CHANNEL_SET, channel="Nonexistent TV",
                      confidence="high"), catalog, State())
    assert not plan.fires_ir


def test_channel_up_defaults_to_stb(catalog):
    plan = run(Intent(action=Action.CHANNEL_UP, confidence="high"), catalog, State())
    assert plan.fires_ir
    assert plan.phrase_key == "stb.channel_up"


# --- compound utterances ------------------------------------------------
#
# From the first real recording: "TV ഓണാക്കുവോ? ഉം. and sound-ഉം കൂടെ കൂട്ടണേ
# കുറച്ച്." -- one breath, two requests. This is normal speech, not an edge case.


def test_two_actions_both_fire(catalog):
    plan = run_many(
        [
            Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"),
            Intent(device=Device.TV, action=Action.VOLUME_UP, steps=2, confidence="high"),
        ],
        catalog,
        State(),
    )
    assert ir_count(plan) == 3          # power + two volume presses
    assert [p.key for p in plan.phrases] == ["tv.power_on", "tv.volume_up"]


def test_power_on_is_followed_by_a_wait(catalog):
    """A TV that was just switched on is not listening yet.

    Without this gap, "turn it on and turn it up" ends with the volume never
    changing, which reads as the system half-working.
    """
    plan = run_many(
        [
            Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"),
            Intent(device=Device.TV, action=Action.VOLUME_UP, confidence="high"),
        ],
        catalog,
        State(),
    )
    delays = [s.ms for s in plan.steps if s.type == "delay"]
    assert max(delays) >= 2000


def test_partial_success_reports_what_happened(catalog):
    """TV power is debounced but the volume request is still valid.

    Apologising for the whole utterance would be a lie -- the sound did change.
    """
    state = State()
    run(Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"),
        catalog, state, now=1000.0)

    plan = run_many(
        [
            Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"),
            Intent(device=Device.TV, action=Action.VOLUME_UP, confidence="high"),
        ],
        catalog,
        state,
        now=1002.0,
    )
    assert plan.fires_ir
    assert [p.key for p in plan.phrases] == ["tv.volume_up"]


def test_all_actions_refused_speaks_the_reason(catalog):
    state = State()
    run(Intent(device=Device.TV, action=Action.POWER_ON, confidence="high"),
        catalog, state, now=1000.0)

    plan = run_many(
        [Intent(device=Device.TV, action=Action.POWER_ON, confidence="high")],
        catalog, state, now=1002.0,
    )
    assert not plan.fires_ir
    assert plan.phrase_key == "err.too_soon"


def test_action_count_is_bounded(catalog):
    """A garbled transcript must not turn into a twenty-command burst."""
    plan = run_many(
        [Intent(device=Device.TV, action=Action.VOLUME_UP, confidence="high")] * 8,
        catalog,
        State(),
    )
    assert ir_count(plan) <= 3


def test_empty_intent_list_is_refused(catalog):
    plan = run_many([], catalog, State())
    assert not plan.fires_ir
    assert plan.phrase_key == "err.not_understood"


def test_one_bad_action_does_not_poison_the_rest(catalog):
    plan = run_many(
        [
            Intent(action=Action.UNKNOWN, confidence="low"),
            Intent(device=Device.TV, action=Action.VOLUME_DOWN, confidence="high"),
        ],
        catalog,
        State(),
    )
    assert plan.fires_ir
    assert [p.key for p in plan.phrases] == ["tv.volume_down"]


# --- the v1 bug ---------------------------------------------------------


def test_broken_digit_one_never_fires(catalog):
    """stb digit_1 duplicates channel_down in the v1 capture.

    Until it is recaptured, any channel containing a 1 must produce silence and
    an apology rather than a channel change she did not ask for.
    """
    catalog.raw["channels"]["ടെസ്റ്റ്"] = "1"
    plan = run(Intent(action=Action.CHANNEL_SET, channel="ടെസ്റ്റ്",
                      confidence="high"), catalog, State())
    assert not plan.fires_ir
    assert plan.phrase_key == "err.broken_code"


# --- every outcome must be speakable ------------------------------------


def test_every_phrase_key_resolves(catalog):
    """A plan that produces no sound is indistinguishable from a dead device."""
    fallback = catalog.phrase("err.internal")
    for key in catalog.all_phrases():
        assert catalog.phrase(key, channel="x") != fallback or key == "err.internal"
