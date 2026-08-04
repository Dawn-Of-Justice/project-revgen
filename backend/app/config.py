from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Sarvam ---------------------------------------------------------
    sarvam_api_key: str = ""
    sarvam_base: str = "https://api.sarvam.ai"
    stt_model: str = "saaras:v3"
    stt_mode: str = "codemix"          # keeps "TV ഓൺ ആക്കൂ" intact for the LLM
    stt_language: str = "ml-IN"        # explicit; skips detection, saves a failure mode
    # The docs still list sarvam-30b as a primary model, but the live API
    # rejects it as deprecated and points at sarvam-105b. Trust the API.
    chat_model: str = "sarvam-105b"
    # Sarvam defaults reasoning_effort to "medium". For a fixed-vocabulary
    # classifier that is latency we pay for nothing.
    chat_reasoning_effort: str | None = None
    tts_model: str = "bulbul:v3"
    tts_speaker: str = "kavitha"
    tts_pace: float = 0.9              # slightly slow: the listener is elderly

    # --- MQTT -----------------------------------------------------------
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_tls: bool = False             # true for hosted brokers on 8883
    mqtt_username: str = ""
    mqtt_password: str = ""
    topic_cmd: str = "revgen/emitter/cmd"
    topic_ack: str = "revgen/emitter/ack"
    topic_status: str = "revgen/emitter/status"   # emitter LWT publishes here
    ack_timeout_s: float = 2.5

    # --- Safety ---------------------------------------------------------
    # The single most important number in the file. If she repeats herself
    # because the TV was slow to wake, the second toggle must not fire.
    #
    # NOTE: this is enforced against in-process state, which is correct only
    # while exactly one instance is running. Never scale this service past one
    # machine without moving State to a shared store -- two instances would
    # each keep their own timer and the debounce would silently stop working.
    power_debounce_s: float = 8.0
    max_volume_steps: int = 5
    digit_gap_ms: int = 300            # slower than this and the STB sees two channels
    post_power_delay_ms: int = 2500    # a booting TV is not listening yet
    max_actions: int = 3

    # --- Access ---------------------------------------------------------
    # Shared secret the remote sends as X-RevGen-Token. Empty disables the
    # check, which is fine on a LAN and not fine on a public URL.
    device_token: str = ""
    # ~6s of 16kHz mono WAV is 192KB. A megabyte is generous; beyond that
    # something is wrong and we should not pay Saaras to find out what.
    max_upload_bytes: int = 1_000_000

    # --- Paths ----------------------------------------------------------
    catalog_path: Path = REPO_ROOT / "config" / "commands.json"
    # Overridden to the mounted volume in production so the TTS cache and logs
    # survive redeploys. Regenerating the cache on every deploy would be slow
    # and would burn the bulbul:v3 rate limit.
    data_dir: Path = REPO_ROOT / "backend"

    @property
    def tts_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "tts"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs" / "utterances.jsonl"

    # --- Modes ----------------------------------------------------------
    # With no key and no broker you can still exercise the whole chain.
    offline: bool = False


settings = Settings()
