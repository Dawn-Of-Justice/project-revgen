"""Format sniffing.

The point of these is that the bytes win over the filename. A phone that labels
an AAC stream `.wav`, or a multipart upload that arrives named `blob`, should
still transcribe rather than fail on a naming technicality.
"""

from __future__ import annotations

import pytest

from app import audio

# Minimal but real container headers.
WAV_HEADER = b"RIFF\x24\x08\x00\x00WAVEfmt "
MP3_ID3 = b"ID3\x03\x00\x00\x00\x00\x00\x00\x00\x00"
MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 8
M4A_HEADER = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00"
MP4_HEADER = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"
OGG_HEADER = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00"
FLAC_HEADER = b"fLaC\x00\x00\x00\x22\x00\x00\x00\x00"
WEBM_HEADER = b"\x1a\x45\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f"
AMR_HEADER = b"#!AMR\n\x00\x00\x00\x00\x00\x00"


@pytest.mark.parametrize(
    "data,expected",
    [
        (WAV_HEADER, "wav"),
        (MP3_ID3, "mp3"),
        (MP3_FRAME, "mp3"),
        (M4A_HEADER, "m4a"),
        (MP4_HEADER, "m4a"),
        (OGG_HEADER, "ogg"),
        (FLAC_HEADER, "flac"),
        (WEBM_HEADER, "webm"),
        (AMR_HEADER, "amr"),
    ],
)
def test_sniffs_container_from_header(data, expected):
    fmt = audio.sniff(data)
    assert fmt is not None
    assert fmt.name == expected


def test_bytes_beat_a_lying_extension():
    """iPhone voice memos get renamed by all sorts of things on the way here."""
    fmt = audio.identify(M4A_HEADER, "recording.wav")
    assert fmt.name == "m4a"
    assert fmt.mime == "audio/mp4"


def test_falls_back_to_extension_when_header_is_unfamiliar():
    fmt = audio.identify(b"\x00" * 32, "voice.mp3")
    assert fmt.name == "mp3"


def test_unknown_bytes_and_unknown_name_raises():
    with pytest.raises(audio.UnsupportedAudio):
        audio.identify(b"\x00" * 32, "notes.txt")


def test_missing_filename_still_works_if_bytes_are_clear():
    """FastAPI uploads sometimes arrive as `blob` with no useful name."""
    assert audio.identify(WAV_HEADER, None).name == "wav"


def test_truncated_input_is_rejected_not_guessed():
    with pytest.raises(audio.UnsupportedAudio):
        audio.identify(b"RI", None)


def test_upload_name_matches_real_contents():
    fmt = audio.identify(M4A_HEADER, "grandma_tv_on.wav")
    assert audio.upload_name(fmt, "grandma_tv_on.wav") == "grandma_tv_on.m4a"


def test_upload_name_handles_no_filename():
    assert audio.upload_name(audio.WAV, None) == "command.wav"


def test_phone_formats_are_all_supported():
    """iPhone writes m4a, Android mp3/opus, WhatsApp re-encodes to ogg."""
    for extension in (".m4a", ".mp3", ".opus", ".ogg", ".wav"):
        assert extension in audio.SUPPORTED_EXTENSIONS
