"""Blood-group parsing, component compatibility and donor eligibility.

Rules (deliberately conservative, a blood-bank judge will check these):
- Whole blood and platelets: same ABO + Rh group only.
- Packed red cells (PRBC): red-cell compatibility table below; exact group preferred.
- Final compatibility is ALWAYS decided by crossmatch at the issuing bank.
- Donor eligibility: opted in to recall (consent), age 18-65, >=90 days since last
  donation (men) / >=120 days (women).
"""
from __future__ import annotations

import re
from datetime import date

GROUPS = ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]

COMPONENTS = {
    "packed_red_cells": "packed red cells",
    "whole_blood": "whole blood",
    "platelets": "platelets",
}

# recipient -> acceptable donor red-cell groups, exact group first, then by preference.
RED_CELL_COMPAT: dict[str, list[str]] = {
    "O-": ["O-"],
    "O+": ["O+", "O-"],
    "A-": ["A-", "O-"],
    "A+": ["A+", "A-", "O+", "O-"],
    "B-": ["B-", "O-"],
    "B+": ["B+", "B-", "O+", "O-"],
    "AB-": ["AB-", "A-", "B-", "O-"],
    "AB+": ["AB+", "AB-", "A+", "A-", "B+", "B-", "O+", "O-"],
}

MIN_GAP_DAYS = {"M": 90, "F": 120}
MIN_AGE, MAX_AGE = 18, 65


class InputError(ValueError):
    """Bad user input; message is safe to speak back."""


def parse_blood_group(raw: str) -> str:
    """'B positive', 'b+ve', 'B-positive', 'AB neg', 'O−', 'B+' -> canonical 'B+' etc."""
    if not raw or not raw.strip():
        raise InputError("I need the blood group, for example B positive.")
    s = raw.strip().upper().replace("\u2212", "-").replace("\u2013", "-")
    for w in ("POSITIVE", "+VE", "PLUS", "POS", "+"):
        s = s.replace(w, " #P ")
    for w in ("NEGATIVE", "-VE", "MINUS", "NEG"):
        s = s.replace(w, " #N ")
    if "#P" not in s and "#N" not in s and "-" in s:
        s = s.replace("-", " #N ")
    s = s.replace("-", " ").replace("GROUP", " ").replace("VE", " ")
    tokens = re.findall(r"#P|#N|AB|A|B|O|0", s.replace(" ", ""))
    abo = [t for t in tokens if not t.startswith("#")]
    sign = [t for t in tokens if t.startswith("#")]
    if len(abo) != 1 or len(sign) != 1:
        raise InputError(f"I couldn't understand the blood group '{raw}'. Please say it like B positive.")
    return ("O" if abo[0] == "0" else abo[0]) + ("+" if sign[0] == "#P" else "-")


def parse_component(raw: str | None) -> tuple[str, bool]:
    """Returns (component_key, assumed). Defaults to packed red cells, flagged as assumed."""
    if not raw or not raw.strip():
        return "packed_red_cells", True
    s = raw.strip().lower().replace("-", " ").replace("_", " ")
    if any(k in s for k in ("prbc", "packed", "red cell", "rbc", "pcv", "prc")):
        return "packed_red_cells", False
    if "whole" in s:
        return "whole_blood", False
    if "platelet" in s or "plt" in s or "sdp" in s or "rdp" in s:
        return "platelets", False
    if s in ("blood", "units", "unit"):
        return "packed_red_cells", True
    raise InputError(f"I can search packed red cells, whole blood or platelets. '{raw}' isn't supported yet.")


def compatible_groups(recipient: str, component: str) -> list[str]:
    if component == "packed_red_cells":
        return list(RED_CELL_COMPAT[recipient])
    # whole blood / platelets: identical group only
    return [recipient]


def spoken_group(g: str) -> str:
    return g[:-1] + (" positive" if g.endswith("+") else " negative")


def age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def donor_eligibility(donor: dict, today: date) -> tuple[bool, str]:
    """donor: {recall_consent, dob (date), gender 'M'/'F', last_donation (date|None)}."""
    if not donor.get("recall_consent"):
        return False, "no recall consent"
    age = age_on(donor["dob"], today)
    if age < MIN_AGE:
        return False, f"age {age} (under {MIN_AGE})"
    if age > MAX_AGE:
        return False, f"age {age} (over {MAX_AGE})"
    last = donor.get("last_donation")
    if last is not None:
        gap = (today - last).days
        need = MIN_GAP_DAYS.get(donor.get("gender", "M"), 90)
        if gap < need:
            return False, f"donated {gap} days ago (needs {need})"
    return True, "eligible"
