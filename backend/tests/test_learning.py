import copy
import json
from types import SimpleNamespace

import pytest

from app.catalog import Catalog
from app.config import settings
from app.emitter import Emitter
from app.intent import build_system_prompt
from app.learning import LearningStore
from app.resolver import State, resolve
from app.schemas import Action, Intent


def update(**changes):
    item = dict(id="capture-0001", producer="emitter-0001", sequence=1,
                kind="command", device="bedroom_tv", device_name="Bedroom television",
                action="volume_up", name="Volume up", behavior="button",
                code={"type": "ir", "protocol": "nec_raw", "raw": 1234, "repeat": 0})
    item.update(changes)
    return json.dumps(item).encode()


@pytest.fixture
def store(tmp_path):
    return LearningStore(tmp_path / "learned.json")


def test_durable_round_trip_and_duplicate_ack(store):
    ack = store.accept(update())
    restarted = LearningStore(store.path)
    assert restarted.accept(update()) == ack
    assert len(restarted.data["entries"]) == 1


def test_old_updates_cannot_replace_new_mapping(store):
    store.accept(update())
    store.accept(update(id="capture-0002", sequence=2, name="Louder"))
    assert store.accept(update())["ok"]  # Redelivery ACK, no reapplication.
    assert next(iter(store.data["entries"].values()))["name"] == "Louder"
    with pytest.raises(ValueError, match="stale"):
        store.accept(update(id="capture-0003"))


@pytest.mark.parametrize("change", [
    {"code": {"type": "ir", "protocol": "raw", "raw": 123}},
    {"code": {"type": "delay", "ms": 0}},
    {"code": {"type": "ir", "protocol": "nec_raw", "raw": True}},
    {"code": {"type": "ir", "protocol": "nec_raw", "raw": 2**32}},
    {"code": {"type": "ir", "protocol": "nec_raw", "raw": 1, "repeat": 1}},
    {"code": {"type": "ir", "protocol": "panasonic", "address": 4096, "command": 1}},
    {"action": "power_on", "behavior": "power_toggle"},
    {"action": "power", "behavior": "button"},
    {"device": "../../escape"}, {"name": "\nInjected"}, {"name": " "},
    {"kind": "channel", "channel_number": "123"},
])
def test_invalid_mapping_does_not_write(store, change):
    with pytest.raises(ValueError):
        store.accept(update(**change))
    assert not store.path.exists()


def test_failed_disk_write_never_activates_mapping(store, monkeypatch):
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr("app.learning.os.replace", fail)
    with pytest.raises(OSError):
        store.accept(update())
    assert store.data["entries"] == {}


def test_duplicate_signal_warns_but_does_not_silently_rename(store):
    store.accept(update())
    ack = store.accept(update(id="capture-0002", sequence=2, action="channel_down"))
    assert "already assigned" in ack["warning"]
    assert len(store.data["entries"]) == 2


def test_captured_digit_fixes_broken_catalog_and_channel_mapping(store):
    store.accept(update(device="stb", action="digit_1"))
    store.accept(update(id="capture-0002", sequence=2, device="stb", kind="channel",
                        action="news_hd", name="News HD", channel_number="101", code=None))
    catalog = Catalog.load(settings.catalog_path)
    store.apply(catalog)
    from app.schemas import Device
    assert catalog.step(Device.STB, "digit_1").raw == 1234
    assert catalog.channel_number("News HD") == "101"
    assert "News HD" in build_system_prompt(catalog)


def test_learned_command_resolves_only_registered_key(store):
    store.accept(update())
    catalog = Catalog.load(settings.catalog_path)
    store.apply(catalog)
    assert "bedroom_tv.volume_up" in build_system_prompt(catalog)
    good = Intent(action=Action.LEARNED, command_key="bedroom_tv.volume_up", confidence="high")
    assert resolve([good], catalog, State(), 10, debounce_s=8, max_volume_steps=5, digit_gap_ms=300).steps[0].raw == 1234
    bad = good.model_copy(update={"command_key": "invented.power"})
    assert not resolve([bad], catalog, State(), 10, debounce_s=8, max_volume_steps=5, digit_gap_ms=300).fires_ir


def test_learned_power_toggle_is_debounced(store):
    store.accept(update(action="power", behavior="power_toggle"))
    catalog = Catalog.load(settings.catalog_path)
    store.apply(catalog)
    state = State()
    intent = Intent(action=Action.LEARNED, command_key="bedroom_tv.power", confidence="high")
    args = dict(debounce_s=8, max_volume_steps=5, digit_gap_ms=300)
    assert resolve([intent], catalog, state, 100, **args).fires_ir
    assert not resolve([intent], catalog, state, 101, **args).fires_ir


def test_mqtt_handler_acknowledges_only_after_store(store):
    events = []
    link = Emitter()
    def handler(payload):
        ack = store.accept(payload)
        events.append("stored")
        return ack
    link.learning_handler = handler
    link._client = SimpleNamespace(publish=lambda *a, **k: events.append(json.loads(a[1])))
    link._accept_learning(update())
    assert events[0] == "stored"
    assert events[1]["ok"] is True


def test_retained_learning_message_is_not_replayed(store):
    link = Emitter()
    calls = []
    link._dispatch = lambda *a: calls.append(a)
    link._on_message(None, None, SimpleNamespace(topic=settings.topic_learn, payload=update(), retain=True))
    assert calls == []


def test_channel_rename_removes_old_learned_name(store):
    catalog = Catalog.load(settings.catalog_path)
    store.accept(update(kind="channel", device="stb", action="my_news",
                        name="My News", channel_number="101", code=None))
    store.apply(catalog)
    store.accept(update(id="capture-0002", sequence=2, kind="channel", device="stb",
                        action="my_news", name="My News HD", channel_number="102", code=None))
    store.apply(catalog)
    assert catalog.channel_number("My News") is None
    assert catalog.channel_number("My News HD") == "102"


def test_mqtt_storage_failure_leaves_upload_pending():
    link = Emitter()
    published = []
    def fail(payload):
        raise OSError("disk unavailable")
    link.learning_handler = fail
    link._client = SimpleNamespace(publish=lambda *a, **k: published.append(a))
    link._accept_learning(update())
    assert published == []
