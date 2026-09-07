import asyncio
import threading
from types import SimpleNamespace

import pytest
from paho.mqtt import client as mqtt

from app.config import settings
from app.emitter import Emitter, EmitterOffline, EmitterTimeout
from app.emitter_protocol import encode_command, validate_steps
from app.schemas import IRStep, Plan


@pytest.fixture
def link(monkeypatch):
    monkeypatch.setattr(settings, "offline", False)
    monkeypatch.setattr(settings, "ack_timeout_s", .03)
    link = Emitter()
    link.online = True
    link._client = SimpleNamespace(publish=lambda *a, **kw: SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS))
    return link


def plan():
    return Plan(id="test-1", steps=[IRStep(protocol="panasonic", address=8, command=32)])


@pytest.mark.asyncio
async def test_ack_from_network_thread(link):
    link._loop = asyncio.get_running_loop()
    pending = asyncio.create_task(link.send(plan()))
    await asyncio.sleep(0)
    msg = SimpleNamespace(topic=settings.topic_ack, payload=b'{"id":"test-1","ok":true}')
    thread = threading.Thread(target=link._on_message, args=(None, None, msg))
    thread.start()
    thread.join()
    assert (await pending).ok
    assert not link._pending


@pytest.mark.asyncio
async def test_late_ack_after_timeout_is_harmless(link):
    with pytest.raises(EmitterTimeout):
        await link.send(plan())
    from app.schemas import Ack
    link._accept_ack(Ack(id="test-1", ok=True))
    assert not link._pending


@pytest.mark.asyncio
async def test_cancel_removes_pending(link):
    pending = asyncio.create_task(link.send(plan()))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not link._pending


@pytest.mark.asyncio
async def test_publish_failure_and_disconnect(link):
    link._client.publish = lambda *a, **kw: SimpleNamespace(rc=mqtt.MQTT_ERR_NO_CONN)
    with pytest.raises(EmitterOffline):
        await link.send(plan())
    assert not link._pending
    link._client.publish = lambda *a, **kw: SimpleNamespace(rc=0)
    pending = asyncio.create_task(link.send(plan()))
    await asyncio.sleep(0)
    link._mark_disconnected()
    with pytest.raises(EmitterOffline):
        await pending
    assert not link._pending


@pytest.mark.parametrize("step", [None, {"type":"delay","ms":-1}, {"type":"delay","ms":True},
    {"type":"ir","protocol":"panasonic","address":4096,"command":1},
    {"type":"ir","protocol":"nec_raw","raw":2**32},
    {"type":"ir","protocol":"nec_raw","raw":1,"repeat":256}])
def test_invalid_numeric_and_step_types(step):
    assert validate_steps([step]) is not None


def test_buffer_includes_mqtt_topic_and_header():
    with pytest.raises(ValueError, match="buffer"):
        encode_command(plan(), "x" * 2040)


def test_oversized_id_is_rejected():
    p = plan()
    p.id = "x" * 48
    with pytest.raises(ValueError, match="id"):
        encode_command(p, settings.topic_cmd)
