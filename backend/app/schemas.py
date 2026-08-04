"""Wire formats. These two schemas ARE the component boundaries.

Remote -> Backend : multipart WAV on POST /command, audio back.
Backend -> Emitter: Plan.to_mqtt() on revgen/emitter/cmd, Ack back on .../ack.

Keep them stable and the three components can be developed independently.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Device(str, Enum):
    TV = "tv"
    STB = "stb"


class Action(str, Enum):
    """The complete intent vocabulary. The LLM may emit nothing outside this.

    Note these are *goals*, not buttons. POWER_ON means "end up on", and it is
    the resolver's job to decide whether that is a discrete code, a toggle, or
    nothing at all.
    """

    POWER_ON = "power_on"
    POWER_OFF = "power_off"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    CHANNEL_UP = "channel_up"
    CHANNEL_DOWN = "channel_down"
    CHANNEL_SET = "channel_set"
    UNKNOWN = "unknown"


class Intent(BaseModel):
    """One action. The LLM returns a list of these -- see intent.py.

    Real speech is compound: "TV ഓണാക്കുവോ... and sound-ഉം കൂടെ കൂട്ടണേ" is two
    actions in one breath, and that is the normal way to ask, not an edge case.
    """

    device: Optional[Device] = None
    action: Action = Action.UNKNOWN
    channel: Optional[str] = Field(
        default=None, description="Channel name as spoken, only for CHANNEL_SET"
    )
    steps: int = Field(default=1, ge=1, le=10, description="Repeat count for volume")
    confidence: Literal["high", "low"] = "low"


# --- Backend -> Emitter -------------------------------------------------


class IRStep(BaseModel):
    type: Literal["ir"] = "ir"
    protocol: Literal["panasonic", "nec_raw"]
    address: Optional[int] = None
    command: Optional[int] = None
    raw: Optional[int] = None
    repeat: int = 0


class DelayStep(BaseModel):
    type: Literal["delay"] = "delay"
    ms: int = Field(ge=0, le=10_000)


Step = IRStep | DelayStep


class Phrase(BaseModel):
    """One thing to say. A plan may produce several, spoken back to back."""

    key: str
    args: dict[str, str] = Field(default_factory=dict)


class Plan(BaseModel):
    """The resolver's output. An empty `steps` list is a valid, meaningful
    result -- it means "understood, but firing IR would be wrong right now"."""

    id: str
    steps: list[Step] = Field(default_factory=list)
    phrases: list[Phrase] = Field(default_factory=list)

    @property
    def fires_ir(self) -> bool:
        return any(s.type == "ir" for s in self.steps)

    @property
    def phrase_key(self) -> str:
        """First phrase key. Convenience for single-action plans and tests."""
        return self.phrases[0].key if self.phrases else "err.internal"


class Ack(BaseModel):
    id: str
    ok: bool
    error: Optional[str] = None
