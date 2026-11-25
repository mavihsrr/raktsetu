"""Operator controls via Flagsmith (SDK 6.x), with safe defaults if Flagsmith is unreachable.

Safe defaults mean: calls stay SIMULATED, autopilot OFF, real banks never dialled.
- call_mode=live lets RaktSetu dial the demo line / LIVE_TARGETS (our own phones).
- call_real_banks=true (Flagsmith only, never a local override) lets it dial real e-RaktKosh bank numbers.

Precedence: runtime overrides (tests / dashboard dev panel) > Flagsmith > local JSON file > defaults.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from .config import settings

log = logging.getLogger("raktsetu.flags")

DEFAULTS: dict[str, Any] = {
    "outbound_calls_enabled": True,   # kill switch, re-read before every dial
    "call_mode": "simulated",         # simulated | live
    "max_parallel_calls": 5,
    "autopilot_mode": False,          # skip human approval for wave 2
    "bank_radius_km": 8.0,
    "donor_radius_km": 10.0,
    "wave2_radius_multiplier": 2.5,
    "max_banks_per_wave": 3,          # shortlist size: banks phoned (or listed as leads) per wave
    "call_real_banks": False,         # dial the REAL bank numbers from e-RaktKosh. Off = demo line only.
}
BOOL_FLAGS = {"outbound_calls_enabled", "autopilot_mode", "call_real_banks"}
# Only Flagsmith itself can turn these on: local file and runtime overrides are ignored.
FLAGSMITH_ONLY = {"call_real_banks"}

# Validation bounds so a typo in the Flagsmith UI can't do something silly.
BOUNDS = {
    "max_parallel_calls": (1, 20),
    "bank_radius_km": (1.0, 50.0),
    "donor_radius_km": (1.0, 50.0),
    "wave2_radius_multiplier": (1.0, 5.0),
    "max_banks_per_wave": (1, 10),
}


def _coerce(name: str, value: Any) -> Any:
    default = DEFAULTS[name]
    try:
        if name == "call_mode":
            v = str(value).strip().lower()
            return v if v in ("simulated", "live") else default
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        v = type(default)(value)
        lo, hi = BOUNDS.get(name, (None, None))
        if lo is not None and not (lo <= v <= hi):
            return default
        return v
    except (TypeError, ValueError):
        return default


class Flags:
    def __init__(self) -> None:
        self._client = None
        self._cache: dict[str, Any] = {}
        self._cache_at = 0.0
        self._source = "defaults"
        self._lock = threading.Lock()
        self.overrides: dict[str, Any] = {}
        if settings.flagsmith_key:
            try:
                from flagsmith import Flagsmith

                from urllib3.util.retry import Retry

                self._client = Flagsmith(environment_key=settings.flagsmith_key, request_timeout_seconds=3,
                                         retries=Retry(total=1, backoff_factor=0.2))
            except Exception as e:  # pragma: no cover
                log.warning("Flagsmith init failed, using safe defaults: %s", e)

    def _from_flagsmith(self) -> dict[str, Any] | None:
        if not self._client:
            return None
        try:
            fl = self._client.get_environment_flags()
            out: dict[str, Any] = {}
            for name in DEFAULTS:
                try:
                    if name in BOOL_FLAGS:
                        out[name] = fl.is_feature_enabled(name)
                    else:
                        val = fl.get_feature_value(name)
                        if val is not None and val != "":
                            out[name] = val
                except Exception:
                    continue  # flag not created in Flagsmith -> default
            return out
        except Exception as e:
            log.warning("Flagsmith unreachable, using safe defaults: %s", e)
            return None

    def _from_file(self) -> dict[str, Any]:
        if not settings.local_flags_path:
            return {}
        try:
            with open(settings.local_flags_path) as f:
                return json.load(f)
        except Exception:
            return {}

    def refresh(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if not force and self._cache and time.time() - self._cache_at < settings.flags_ttl_s:
                return self._cache
            values = dict(DEFAULTS)
            source = "defaults"
            filed = self._from_file()
            if filed:
                values.update({k: v for k, v in filed.items() if k in DEFAULTS and k not in FLAGSMITH_ONLY})
                source = "local-file"
            remote = self._from_flagsmith()
            if remote is not None:
                values.update(remote)
                source = "flagsmith"
            elif self._client:
                source = "defaults (flagsmith unreachable)"
            self._cache = {k: _coerce(k, v) for k, v in values.items()}
            self._cache_at = time.time()
            self._source = source
            return self._cache

    def get(self, name: str) -> Any:
        if name in self.overrides and name not in FLAGSMITH_ONLY:
            return _coerce(name, self.overrides[name])
        return self.refresh()[name]

    async def aget(self, name: str) -> Any:
        """Re-read (TTL-bounded) without blocking the event loop. Use before every dial."""
        if name in self.overrides and name not in FLAGSMITH_ONLY:
            return _coerce(name, self.overrides[name])
        vals = await asyncio.to_thread(self.refresh)
        return vals[name]

    def snapshot(self) -> dict[str, Any]:
        vals = dict(self.refresh())
        for k, v in self.overrides.items():
            if k not in FLAGSMITH_ONLY:
                vals[k] = _coerce(k, v)
        return {"values": vals, "source": self._source, "overridden": sorted(self.overrides)}


flags = Flags()
