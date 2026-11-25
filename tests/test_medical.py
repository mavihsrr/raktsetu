from datetime import date, timedelta

import pytest

from app.medical import InputError, compatible_groups, donor_eligibility, parse_blood_group, parse_component

TODAY = date(2026, 11, 25)


@pytest.mark.parametrize("raw,want", [
    ("B+", "B+"), ("b positive", "B+"), ("B-positive", "B+"), ("B-", "B-"), ("AB neg", "AB-"),
    ("O−", "O-"), ("o +ve", "O+"), ("ab+", "AB+"), ("A Negative", "A-"), ("0+", "O+"),
])
def test_parse_blood_group(raw, want):
    assert parse_blood_group(raw) == want


@pytest.mark.parametrize("raw", ["B", "", "C+", "positive"])
def test_parse_blood_group_rejects(raw):
    with pytest.raises(InputError):
        parse_blood_group(raw)


def test_component_default_is_flagged_as_assumed():
    assert parse_component(None) == ("packed_red_cells", True)
    assert parse_component("PRBC") == ("packed_red_cells", False)
    assert parse_component("whole blood") == ("whole_blood", False)
    assert parse_component("platelets") == ("platelets", False)
    with pytest.raises(InputError):
        parse_component("cryo")


def test_whole_blood_and_platelets_same_group_only():
    for g in ("O-", "B+", "AB+"):
        assert compatible_groups(g, "whole_blood") == [g]
        assert compatible_groups(g, "platelets") == [g]


def test_red_cell_table():
    assert compatible_groups("B+", "packed_red_cells") == ["B+", "B-", "O+", "O-"]
    assert compatible_groups("O-", "packed_red_cells") == ["O-"]
    assert set(compatible_groups("AB+", "packed_red_cells")) == {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"}
    assert compatible_groups("A-", "packed_red_cells") == ["A-", "O-"]
    # never give Rh+ red cells to an Rh- recipient
    for g in ("O-", "A-", "B-", "AB-"):
        assert all(x.endswith("-") for x in compatible_groups(g, "packed_red_cells"))
    # exact group always first
    for g in ("O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"):
        assert compatible_groups(g, "packed_red_cells")[0] == g


def _donor(**kw):
    d = {"recall_consent": True, "dob": date(1995, 1, 1), "gender": "M", "last_donation": None}
    d.update(kw)
    return d


def test_eligibility_rules():
    assert donor_eligibility(_donor(), TODAY)[0]
    assert not donor_eligibility(_donor(recall_consent=False), TODAY)[0]
    assert not donor_eligibility(_donor(dob=date(2009, 1, 1)), TODAY)[0]          # 17
    assert donor_eligibility(_donor(dob=date(2008, 11, 25)), TODAY)[0]            # exactly 18
    assert donor_eligibility(_donor(dob=date(1961, 11, 26)), TODAY)[0]            # 64, turns 65 tomorrow
    assert not donor_eligibility(_donor(dob=date(1960, 1, 1)), TODAY)[0]          # 66
    m = _donor(gender="M")
    assert not donor_eligibility({**m, "last_donation": TODAY - timedelta(days=89)}, TODAY)[0]
    assert donor_eligibility({**m, "last_donation": TODAY - timedelta(days=90)}, TODAY)[0]
    f = _donor(gender="F")
    assert not donor_eligibility({**f, "last_donation": TODAY - timedelta(days=100)}, TODAY)[0]
    assert donor_eligibility({**f, "last_donation": TODAY - timedelta(days=120)}, TODAY)[0]
