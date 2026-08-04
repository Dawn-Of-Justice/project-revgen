"""Loads commands.json and answers questions about what is actually firable.

The important job here is refusing to pretend. A button that is missing, or
flagged broken, must fail loudly at plan time rather than silently emitting the
wrong IR code -- that is exactly how v1 ended up with stb.1 changing channels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .schemas import Device, IRStep


class BrokenCode(Exception):
    """Raised when a button is known-bad rather than merely absent."""


@dataclass
class Catalog:
    raw: dict

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    # --- devices --------------------------------------------------------

    def _device(self, device: Device) -> dict:
        return self.raw["devices"][device.value]

    def label(self, device: Device) -> str:
        return self._device(device).get("label_ml", device.value)

    def has_discrete(self, device: Device, name: str) -> bool:
        return self._device(device).get("discrete", {}).get(name) is not None

    # --- buttons --------------------------------------------------------

    def step(self, device: Device, button: str) -> IRStep:
        """Build an IR step, or refuse."""
        dev = self._device(device)

        if button in dev.get("_broken_buttons", {}):
            raise BrokenCode(
                f"{device.value}.{button} is flagged broken in commands.json: "
                f"{dev['_broken_buttons'][button].get('note', '')}"
            )

        entry = dev.get("buttons", {}).get(button)
        if entry is None:
            discrete = dev.get("discrete", {}).get(button)
            if discrete is None:
                raise KeyError(f"{device.value}.{button} not in catalog")
            entry = discrete

        protocol = entry.get("protocol", dev["protocol"])
        if protocol == "nec_raw":
            return IRStep(protocol="nec_raw", raw=int(entry["raw"], 16))
        return IRStep(
            protocol="panasonic",
            address=entry.get("address", dev.get("address")),
            command=entry["command"],
        )

    def digits_available(self, device: Device) -> set[str]:
        dev = self._device(device)
        return {
            k.removeprefix("digit_")
            for k in dev.get("buttons", {})
            if k.startswith("digit_")
        }

    # --- channels -------------------------------------------------------

    def channel_number(self, name: str) -> str | None:
        for key, value in self.raw.get("channels", {}).items():
            if key.startswith("_"):
                continue
            if key == name and value:
                return str(value)
        return None

    def channel_names(self) -> list[str]:
        return [k for k, v in self.raw.get("channels", {}).items() if not k.startswith("_")]

    # --- phrases --------------------------------------------------------

    def phrase(self, key: str, **args: str) -> str:
        text = self.raw["phrases"].get(key)
        if text is None:
            return self.raw["phrases"]["err.internal"]
        return text.format(**args) if args else text

    def all_phrases(self) -> dict[str, str]:
        """Everything the cache builder needs to pre-generate."""
        return {k: v for k, v in self.raw["phrases"].items() if not k.startswith("_")}
