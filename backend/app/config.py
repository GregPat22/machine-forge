"""Runtime settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_rates(raw: str) -> dict[str, float]:
    rates: dict[str, float] = {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        code, value = pair.split("=", 1)
        try:
            rates[code.strip().upper()] = float(value)
        except ValueError:
            continue
    return rates


@dataclass(frozen=True)
class Settings:
    # LLM: "anthropic" (Claude API), "openai_compatible" (Ollama, vLLM, Azure OpenAI, ...) or "mock".
    llm_provider: str = "anthropic"
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "high"
    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = ""
    openai_model: str = "llama3.1"

    db_path: Path = BACKEND_DIR / "data" / "machine-forge.db"

    # Supplier connectors: each one is enabled only when its credentials are set.
    mouser_api_key: str = ""
    nexar_client_id: str = ""
    nexar_client_secret: str = ""
    offer_cache_hours: int = 24

    # All prices are compared in this currency. Rates are "1 unit of X = rate units of base".
    base_currency: str = "EUR"
    fx_rates: dict[str, float] = field(default_factory=dict)

    # Sourcing score weights (normalized at runtime).
    weight_price: float = 0.5
    weight_lead_time: float = 0.3
    weight_availability: float = 0.2

    cors_origins: tuple[str, ...] = ("http://localhost:5173",)


DEFAULT_FX = "USD=0.92,GBP=1.17,CHF=1.06,JPY=0.0061,CNY=0.13"


def load_settings() -> Settings:
    _load_dotenv(BACKEND_DIR / ".env")
    _load_dotenv(BACKEND_DIR.parent / ".env")
    env = os.environ.get
    return Settings(
        llm_provider=env("MF_LLM_PROVIDER", "anthropic").strip().lower(),
        anthropic_model=env("MF_ANTHROPIC_MODEL", "claude-opus-5-5"),
        anthropic_effort=env("MF_ANTHROPIC_EFFORT", "high"),
        openai_base_url=env("MF_OPENAI_BASE_URL", "http://localhost:11434/v1"),
        openai_api_key=env("MF_OPENAI_API_KEY", ""),
        openai_model=env("MF_OPENAI_MODEL", "llama3.1"),
        db_path=Path(env("MF_DB_PATH", str(BACKEND_DIR / "data" / "machine-forge.db"))),
        mouser_api_key=env("MOUSER_API_KEY", ""),
        nexar_client_id=env("NEXAR_CLIENT_ID", ""),
        nexar_client_secret=env("NEXAR_CLIENT_SECRET", ""),
        offer_cache_hours=int(env("MF_OFFER_CACHE_HOURS", "24")),
        base_currency=env("MF_BASE_CURRENCY", "EUR").upper(),
        fx_rates=_parse_rates(env("MF_FX_RATES", DEFAULT_FX)),
        weight_price=float(env("MF_WEIGHT_PRICE", "0.5")),
        weight_lead_time=float(env("MF_WEIGHT_LEAD_TIME", "0.3")),
        weight_availability=float(env("MF_WEIGHT_AVAILABILITY", "0.2")),
        cors_origins=tuple(
            o.strip() for o in env("MF_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        ),
    )
