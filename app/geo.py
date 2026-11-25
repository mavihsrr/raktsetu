"""Distance and rough drive-time estimates (labelled approximate everywhere they are shown)."""
from __future__ import annotations

import math

ROAD_FACTOR = 1.4      # straight line -> road distance, rough for Bengaluru
CITY_KMPH = 20.0       # average city speed
HANDLING_MIN = 10      # issue + pickup handling at the bank


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def eta_minutes(km: float | None) -> int | None:
    """One-way approximate drive time from the bank to the hospital, plus handling. None if unknown."""
    if km is None:
        return None
    return int(round(km * ROAD_FACTOR / CITY_KMPH * 60 + HANDLING_MIN))
