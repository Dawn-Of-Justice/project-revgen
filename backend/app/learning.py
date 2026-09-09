"""Validated, persistent learned commands. Broker ACL/TLS authenticates the emitter."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .emitter_protocol import validate_steps


class LearningUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,48}$")
    producer: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,48}$")
    sequence: int = Field(ge=1, le=0xFFFFFFFF)
    kind: Literal["command", "channel"] = "command"
    device: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    device_name: str = Field(min_length=1, max_length=64)
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    name: str = Field(min_length=1, max_length=64)
    behavior: Literal["button", "power_toggle", "power_on", "power_off"] = "button"
    code: dict | None = None
    channel_number: str | None = Field(default=None, pattern=r"^[0-9]{1,6}$")

    @model_validator(mode="after")
    def check(self):
        if any(not s.strip() or any(ord(c) < 32 for c in s) for s in [self.name, self.device_name]):
            raise ValueError("names must be printable and nonempty")
        if self.kind == "command":
            if self.action == "power" and self.behavior != "power_toggle":
                raise ValueError("power is a toggle; declare its behavior")
            if self.action in {"power_on", "power_off"} and self.behavior != self.action:
                raise ValueError("discrete power action requires matching behavior")
            if self.code is None or self.channel_number is not None:
                raise ValueError("command requires code only")
            error = validate_steps([self.code])
            if error:
                raise ValueError(error)
            if self.code.get("type") != "ir" or self.code.get("repeat", 0) != 0:
                raise ValueError("learn one IR command without repeats")
            fields = {"type", "protocol", "repeat"} | ({"raw"} if self.code["protocol"] == "nec_raw" else {"address", "command"})
            if set(self.code) - fields:
                raise ValueError("unexpected IR fields")
        elif self.code is not None or self.channel_number is None or self.device != "stb":
            raise ValueError("channel maps digits on the primary stb; no IR code")
        return self


class LearningStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"entries": {}, "sequences": {}, "receipts": {}}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            for entry in raw["entries"].values():
                LearningUpdate.model_validate(entry)
            self.data = raw

    def accept(self, payload: bytes) -> dict:
        if len(payload) > 1536:
            raise ValueError("mapping exceeds 1536 bytes")
        update = LearningUpdate.model_validate_json(payload)
        if update.id in self.data["receipts"]:
            return self.data["receipts"][update.id]
        if update.sequence <= self.data["sequences"].get(update.producer, 0):
            raise ValueError("stale mapping sequence")
        if update.producer not in self.data["sequences"] and len(self.data["sequences"]) >= 8:
            raise ValueError("producer limit reached")
        key = f"{update.kind}:{update.device}:{update.action}"
        if key not in self.data["entries"] and len(self.data["entries"]) >= 128:
            raise ValueError("mapping limit reached")
        warnings = []
        for other_key, other in self.data["entries"].items():
            if other_key != key and update.kind == "command" and other.get("code") == update.code:
                warnings.append("This IR signal is already assigned to another action")
                break
        ack = {"id": update.id, "ok": True, "warning": "; ".join(warnings)}
        next_data = copy.deepcopy(self.data)
        next_data["entries"][key] = update.model_dump(exclude_none=True)
        next_data["sequences"][update.producer] = update.sequence
        next_data["receipts"][update.id] = ack
        while len(next_data["receipts"]) > 256:
            del next_data["receipts"][next(iter(next_data["receipts"]))]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(next_data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        self.data = next_data  # No ACK or in-memory activation before durable write.
        return ack

    def apply(self, catalog):
        if not hasattr(catalog, "_learning_base"):
            catalog._learning_base = copy.deepcopy(catalog.raw)
        raw = copy.deepcopy(catalog._learning_base)
        learned = {}
        for entry in self.data["entries"].values():
            if entry["kind"] == "channel":
                raw.setdefault("channels", {})[entry["name"]] = entry["channel_number"]
                continue
            learned[f'{entry["device"]}.{entry["action"]}'] = entry
            # Standard actions immediately improve the existing TV/STB resolver.
            if entry["device"] in {"tv", "stb"}:
                dev = raw["devices"][entry["device"]]
                button = entry["action"]
                code = {k: v for k, v in entry["code"].items() if k not in {"type", "repeat"}}
                if "raw" in code:
                    code["raw"] = hex(code["raw"])
                if button in {"power_on", "power_off"}:
                    if entry["behavior"] != button:
                        continue  # Never advertise a toggle as a discrete command.
                    dev.setdefault("discrete", {})[button] = code
                else:
                    dev.setdefault("buttons", {})[button] = code
                    dev.get("_broken_buttons", {}).pop(button, None)
        raw["learned"] = learned
        catalog.raw = raw
