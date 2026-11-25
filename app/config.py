"""Runtime settings from environment (.env supported). Secrets never leave the server."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _parse_live_targets(raw: str) -> dict[str, str]:
    """LIVE_TARGETS="bank:B02=+9198xxxxxxx,donor:D01=+9197xxxxxxx" -> {"bank:B02": "+91..."}.

    Only targets listed here are ever dialled for real (teammates' phones). Everything else
    is simulated and labelled SIM, even when call_mode=live.
    """
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, phone = part.split("=", 1)
        out[key.strip()] = phone.strip()
    return out


_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"


def _parse_origins(raw: str) -> list[str]:
    """CORS_ORIGINS="https://a.example,https://b.example" -> list. "*" means any origin."""
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: _env("DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "raktsetu.db")))
    tool_secret: str = field(default_factory=lambda: _env("TOOL_SECRET", "dev-tool-secret"))
    dashboard_token: str = field(default_factory=lambda: _env("DASHBOARD_TOKEN"))
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"))
    webhook_secret: str = field(default_factory=lambda: _env("WEBHOOK_SECRET", "dev-webhook-secret"))
    # Browser origins allowed to call the API cross-origin (separate frontend). "*" = any origin.
    cors_origins: list[str] = field(default_factory=lambda: _parse_origins(_env("CORS_ORIGINS") or _DEFAULT_CORS_ORIGINS))

    # Simulation: seconds multiplier for simulated call durations (0 = instant, tests).
    sim_speed: float = field(default_factory=lambda: float(_env("SIM_SPEED", "1.0") or 1.0))
    get_status_wait_s: float = field(default_factory=lambda: float(_env("GET_STATUS_WAIT_S", "25")))
    live_call_timeout_s: float = field(default_factory=lambda: float(_env("LIVE_CALL_TIMEOUT_S", "300")))

    # Sarvam (outbound caller agents)
    sarvam_api_key: str = field(default_factory=lambda: _env("SARVAM_API_KEY"))
    sarvam_org_id: str = field(default_factory=lambda: _env("SARVAM_ORG_ID"))
    sarvam_workspace_id: str = field(default_factory=lambda: _env("SARVAM_WORKSPACE_ID"))
    sarvam_connection_id: str = field(default_factory=lambda: _env("SARVAM_CONNECTION_ID"))
    sarvam_agent_phone: str = field(default_factory=lambda: _env("SARVAM_AGENT_PHONE"))
    sarvam_bank_app_id: str = field(default_factory=lambda: _env("SARVAM_BANK_APP_ID"))
    sarvam_bank_app_version: str = field(default_factory=lambda: _env("SARVAM_BANK_APP_VERSION"))
    sarvam_donor_app_id: str = field(default_factory=lambda: _env("SARVAM_DONOR_APP_ID"))
    sarvam_donor_app_version: str = field(default_factory=lambda: _env("SARVAM_DONOR_APP_VERSION"))
    sarvam_intake_app_id: str = field(default_factory=lambda: _env("SARVAM_INTAKE_APP_ID"))
    sarvam_intake_app_version: str = field(default_factory=lambda: _env("SARVAM_INTAKE_APP_VERSION"))
    sarvam_base_url: str = field(default_factory=lambda: _env("SARVAM_BASE_URL", "https://apps.sarvam.ai").rstrip("/"))
    live_targets: dict[str, str] = field(default_factory=lambda: _parse_live_targets(_env("LIVE_TARGETS")))
    # Our own phone(s) that stand in for the real banks while call_real_banks is off.
    demo_bank_phones: list[str] = field(default_factory=lambda: [p.strip() for p in _env("DEMO_BANK_PHONES").split(",") if p.strip()])
    # Demo phone(s) that take the donor restock call (there is no real donor registry yet).
    demo_donor_phones: list[str] = field(default_factory=lambda: [p.strip() for p in _env("DEMO_DONOR_PHONES").split(",") if p.strip()])

    # Flagsmith
    flagsmith_key: str = field(default_factory=lambda: _env("FLAGSMITH_ENVIRONMENT_KEY"))
    flags_ttl_s: float = field(default_factory=lambda: float(_env("FLAGS_TTL_S", "2")))
    local_flags_path: str = field(default_factory=lambda: _env("LOCAL_FLAGS_PATH"))

    # NudgeBee event forwarding (optional, only if their team confirms a webhook trigger)
    nudgebee_webhook_url: str = field(default_factory=lambda: _env("NUDGEBEE_WEBHOOK_URL"))

    def sarvam_ready(self) -> bool:
        return all([self.sarvam_api_key, self.sarvam_org_id, self.sarvam_workspace_id,
                    self.sarvam_connection_id, self.sarvam_agent_phone])


settings = Settings()
