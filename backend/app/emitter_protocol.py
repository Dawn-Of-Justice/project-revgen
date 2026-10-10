"""Limits shared by the backend and hardware-free emitter validator."""
import json

from .schemas import Plan

MAX_STEPS = 24
MAX_REPEAT = 10
MAX_PACKET_BYTES = 8192
MAX_RAW_TIMINGS = 512


def integer(value, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def validate_steps(steps) -> str | None:
    if not isinstance(steps, list):
        return "no steps"
    if not steps:
        return "empty sequence"
    if len(steps) > MAX_STEPS:
        return "too many steps"
    raw_count = 0
    for step in steps:
        if not isinstance(step, dict):
            return "invalid step"
        if step.get("type") == "delay":
            if not integer(step.get("ms"), 10_000):
                return "invalid delay"
        elif step.get("type") == "ir":
            if not integer(step.get("repeat", 0), MAX_REPEAT):
                return "invalid repeat"
            if step.get("protocol") == "panasonic":
                if not integer(step.get("address"), 0xFFF) or not integer(step.get("command"), 0xFF):
                    return "invalid panasonic fields"
            elif step.get("protocol") == "nec_raw":
                if not integer(step.get("raw"), 0xFFFFFFFF):
                    return "invalid raw"
            elif step.get("protocol") == "raw_timings":
                timings = step.get("timings")
                if (not isinstance(timings, list) or not 3 <= len(timings) <= MAX_RAW_TIMINGS
                        or len(timings) % 2 != 1
                        or any(not integer(t, 65000) or t < 100 for t in timings)
                        or sum(timings) > 500000
                        or not integer(step.get("carrier_khz"), 60)
                        or step["carrier_khz"] < 30 or step.get("repeat", 0) != 0):
                    return "invalid raw timings"
                raw_count += len(timings)
                if raw_count > MAX_RAW_TIMINGS:
                    return "too many raw timings"
            else:
                return "unsupported protocol"
        else:
            return "unknown step type"
    return None


def encode_command(plan: Plan, topic: str) -> bytes:
    if not plan.id or len(plan.id.encode("utf-8")) > 47 or "\0" in plan.id:
        raise ValueError("command id must be 1–47 UTF-8 bytes without NUL")
    steps = [step.model_dump(exclude_none=True) for step in plan.steps]
    error = validate_steps(steps)
    if error:
        raise ValueError(error)
    payload = json.dumps({"id": plan.id, "steps": steps}, separators=(",", ":")).encode()
    # MQTT maximum fixed header + topic length field + topic + QoS1 packet ID.
    if len(payload) + 5 + 2 + len(topic.encode()) + 2 > MAX_PACKET_BYTES:
        raise ValueError("command exceeds emitter MQTT buffer")
    return payload
