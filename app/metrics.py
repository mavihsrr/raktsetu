"""Prometheus metrics for Cloud Monitoring (Google Managed Prometheus) and NudgeBee.

Aggregate counts only: no names, phone numbers, locations or request ids ever go into a label.
Scraped from inside the cluster at /metrics (the route refuses requests that came through the public tunnel).
"""
from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP = Counter("raktsetu_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_SECONDS = Histogram("raktsetu_http_request_seconds", "HTTP request latency", ["route"],
                         buckets=(.05, .1, .25, .5, 1, 2, 4, 8, 15))
SEARCHES = Counter("raktsetu_searches_total", "Blood searches (find_leads)", ["outcome"])
SEARCH_SECONDS = Histogram("raktsetu_search_seconds", "find_leads duration", buckets=(1, 2, 4, 6, 8, 12, 20, 40))
PORTAL = Counter("raktsetu_eraktkosh_requests_total", "Live e-RaktKosh portal lookups", ["outcome"])
CALLS = Counter("raktsetu_calls_total", "Calls that reached a final status", ["target", "route", "status"])
VOICE_ACTIVE = Gauge("raktsetu_voice_sessions_active", "Browser voice sessions open right now")
VOICE_SESSIONS = Counter("raktsetu_voice_sessions_total", "Browser voice sessions", ["outcome"])
STARTED = Gauge("raktsetu_process_start_time_seconds", "Unix time the app started")
STARTED.set(time.time())


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
