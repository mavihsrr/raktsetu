"""FICTIONAL donor registry (placeholder until a real opted-in registry exists).

Blood banks are NOT seeded: they come live from e-RaktKosh on every request (app/eraktkosh.py).
Donor phone numbers use the +91-00000 prefix so nothing real can be dialled; only donors listed
in LIVE_TARGETS are ever phoned for real.

`sim` describes how a simulated donor call goes: answer (answered|no_answer|busy|failed), willing.
"""
from __future__ import annotations

from datetime import date, timedelta


# id, name, gender, age, group, lat, lng, last_donation_days_ago (None=never), consent, sim_answer, willing
_DONORS = [
    ("D01", "Arjun R.", "M", 29, "B+", 12.9450, 77.5800, 200, True, "answered", "yes"),
    ("D02", "Meera S.", "F", 34, "B+", 12.9600, 77.5900, 150, True, "no_answer", None),
    ("D03", "Ravi K.", "M", 41, "B+", 12.9400, 77.5900, 60, True, "answered", "yes"),
    ("D04", "Fatima N.", "F", 27, "B+", 12.9350, 77.5950, 100, True, "answered", "yes"),
    ("D05", "Suresh P.", "M", 67, "B+", 12.9550, 77.5750, 400, True, "answered", "yes"),
    ("D06", "Kavya M.", "F", 24, "B+", 12.9500, 77.6000, 300, False, "answered", "yes"),
    ("D07", "Imran A.", "M", 35, "B+", 12.8500, 77.6600, 365, True, "answered", "yes"),
    ("D08", "Priya D.", "F", 30, "O+", 12.9480, 77.5850, 180, True, "answered", "yes"),
    ("D09", "Rahul V.", "M", 22, "A+", 12.9420, 77.5790, 120, True, "answered", "later"),
    ("D10", "Deepa J.", "F", 45, "B-", 12.9380, 77.5880, None, True, "answered", "yes"),
    ("D11", "Kiran T.", "M", 17, "B+", 12.9520, 77.5820, None, True, "answered", "yes"),
    ("D12", "Anil G.", "M", 52, "AB+", 12.9600, 77.5800, None, True, "answered", "yes"),
    ("D13", "Sneha L.", "F", 38, "A-", 12.9700, 77.6100, 240, True, "answered", "no"),
    ("D14", "Vikram B.", "M", 31, "O-", 12.9300, 77.5700, 95, True, "answered", "yes"),
]


def _fake_phone(prefix: int, n: int) -> str:
    return f"+91-00000-{prefix}{n:04d}"


def donors(today: date) -> list[dict]:
    out = []
    for i, (did, name, gender, age, group, lat, lng, days_ago, consent, answer, willing) in enumerate(_DONORS, start=1):
        dob = date(today.year - age, 6, 15) if (today.month, today.day) >= (6, 15) else date(today.year - age - 1, 6, 15)
        out.append({
            "id": did, "name": name, "gender": gender, "dob": dob, "blood_group": group,
            "lat": lat, "lng": lng, "phone": _fake_phone(2, i),
            "last_donation": (today - timedelta(days=days_ago)) if days_ago is not None else None,
            "recall_consent": consent,
            "sim": {"answer": answer, "willing": willing},
        })
    return out
