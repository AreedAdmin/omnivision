"""Central configuration — all secrets via env vars (.env at repo root)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (works whether server is run from repo root or server/)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv()  # also pick up a local .env / shell env


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


@dataclass(frozen=True)
class Settings:
    # AssemblyAI
    assemblyai_api_key: str = field(default_factory=lambda: _env("ASSEMBLYAI_API_KEY"))

    # Anthropic
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    live_model: str = field(default_factory=lambda: _env("LIVE_MODEL", "claude-sonnet-4-6"))
    extraction_model: str = field(default_factory=lambda: _env("EXTRACTION_MODEL", "claude-opus-4-8"))

    # Twilio
    twilio_account_sid: str = field(default_factory=lambda: _env("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str = field(default_factory=lambda: _env("TWILIO_AUTH_TOKEN"))
    twilio_phone_number: str = field(default_factory=lambda: _env("TWILIO_PHONE_NUMBER"))

    # Cartesia
    cartesia_api_key: str = field(default_factory=lambda: _env("CARTESIA_API_KEY"))
    cartesia_voice_id: str = field(default_factory=lambda: _env("CARTESIA_VOICE_ID"))

    # Supabase
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_key: str = field(
        default_factory=lambda: _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_PUBLISHABLE_KEY")
    )
    supabase_schema: str = field(default_factory=lambda: _env("SUPABASE_SCHEMA", "assemblyai"))

    # Telephony / public host
    public_host: str = field(default_factory=lambda: _env("PUBLIC_HOST"))

    # Call persona
    company_name: str = field(default_factory=lambda: _env("COMPANY_NAME", "Omnivision Warehousing"))
    callback_number: str = field(default_factory=lambda: _env("CALLBACK_NUMBER", "our main office line"))

    port: int = field(default_factory=lambda: int(_env("PORT", "8000") or 8000))


settings = Settings()


def assert_core_settings() -> list[str]:
    """Return a list of missing core settings (logged at startup, not fatal —
    telephony-only vars may be absent during Phases 0-4)."""
    missing = []
    for name in ("assemblyai_api_key", "anthropic_api_key", "cartesia_api_key",
                 "supabase_url", "supabase_key"):
        if not getattr(settings, name):
            missing.append(name.upper())
    return missing
