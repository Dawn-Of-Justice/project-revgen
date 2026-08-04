"""Audio format detection for uploads.

Saaras accepts WAV, MP3, M4A/MP4, AAC, OGG, OPUS, FLAC, AIFF, AMR, WMA and
WebM directly, so nothing here transcodes -- the job is only to hand the API a
correct MIME type and filename so its codec detection works.

Formats are sniffed from magic bytes rather than trusted from the extension.
The remote will always send WAV, but the recordings you feed `check_sarvam.py`
come off a phone, where an iPhone writes .m4a, Android tends to write .mp3 or
.opus, and WhatsApp re-encodes everything to .ogg with whatever name it likes.

One real caveat: the docs note Saaras works best at 16 kHz and that multi-channel
audio is merged to mono. Phone recordings are typically 44.1/48 kHz stereo. They
work, but if `check_sarvam.py` accuracy looks worse than you expect, downsample
before blaming the model:

    ffmpeg -i in.m4a -ar 16000 -ac 1 out.wav
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class UnsupportedAudio(Exception):
    pass


@dataclass(frozen=True)
class Format:
    name: str
    extension: str
    mime: str


WAV = Format("wav", ".wav", "audio/wav")
MP3 = Format("mp3", ".mp3", "audio/mpeg")
M4A = Format("m4a", ".m4a", "audio/mp4")
AAC = Format("aac", ".aac", "audio/aac")
OGG = Format("ogg", ".ogg", "audio/ogg")
OPUS = Format("opus", ".opus", "audio/opus")
FLAC = Format("flac", ".flac", "audio/flac")
AIFF = Format("aiff", ".aiff", "audio/aiff")
AMR = Format("amr", ".amr", "audio/amr")
WEBM = Format("webm", ".webm", "audio/webm")
WMA = Format("wma", ".wma", "audio/x-ms-wma")

BY_EXTENSION: dict[str, Format] = {
    f.extension: f
    for f in (WAV, MP3, M4A, AAC, OGG, OPUS, FLAC, AIFF, AMR, WEBM, WMA)
}
BY_EXTENSION.update({".mp4": M4A, ".aif": AIFF, ".aifc": AIFF, ".oga": OGG})

SUPPORTED_EXTENSIONS = frozenset(BY_EXTENSION)


def sniff(data: bytes) -> Format | None:
    """Identify the container from its header, or None if unrecognised."""
    if len(data) < 12:
        return None

    head = data[:12]

    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return WAV
    if head[:4] == b"fLaC":
        return FLAC
    if head[:4] == b"OggS":
        # Ogg carries either Vorbis or Opus; both are accepted, and the API
        # sorts out the codec itself, so the distinction does not matter here.
        return OGG
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return AIFF
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return WEBM
    if head[:5] == b"#!AMR":
        return AMR
    if head[:3] == b"ID3":
        return MP3
    # MPEG audio frame sync: 11 set bits.
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return MP3
    # ISO base media (MP4/M4A) puts 'ftyp' at offset 4.
    if head[4:8] == b"ftyp":
        return M4A
    if head[:4] == b"\x30\x26\xb2\x75":
        return WMA
    if head[:4] == b"ADIF" or (head[0] == 0xFF and (head[1] & 0xF6) == 0xF0):
        return AAC

    return None


def identify(data: bytes, filename: str | None = None) -> Format:
    """Sniffed format, falling back to the extension, else raise.

    Bytes win over the filename: a phone that labels an AAC stream `.wav`, or an
    upload that arrives as `blob`, should still transcribe rather than fail on a
    naming technicality.
    """
    detected = sniff(data)
    if detected is not None:
        return detected

    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix in BY_EXTENSION:
            return BY_EXTENSION[suffix]

    raise UnsupportedAudio(
        f"unrecognised audio (filename={filename!r}, {len(data)} bytes, "
        f"header={data[:8].hex()}). Supported: "
        f"{', '.join(sorted(e.lstrip('.') for e in SUPPORTED_EXTENSIONS))}"
    )


def upload_name(fmt: Format, filename: str | None) -> str:
    """A filename whose extension matches the real contents."""
    stem = Path(filename).stem if filename else "command"
    return f"{stem or 'command'}{fmt.extension}"
