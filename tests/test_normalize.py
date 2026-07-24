import pandas as pd
import pytest

from hhpanel.normalize import (
    add_ccn,
    flag_financial_owner,
    normalize_ccn,
    snake,
    to_numeric,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("197001", "197001"),
        (197001, "197001"),
        (197001.0, "197001"),
        ("  7001 ", "007001"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_ccn(raw, expected):
    assert normalize_ccn(raw) == expected


def test_snake_handles_cms_titles():
    assert (
        snake("Quality of Patient Care Star Rating")
        == "quality_of_patient_care_star_rating"
    )
    assert snake("CMS Certification Number (CCN)") == "cms_certification_number_ccn"


def test_add_ccn_finds_aliased_column():
    df = pd.DataFrame({"CMS Certification Number (CCN)": ["7001"], "x": [1]})
    assert add_ccn(df)["ccn"].tolist() == ["007001"]


def test_add_ccn_raises_readable_error():
    with pytest.raises(KeyError, match="No CMS Certification Number"):
        add_ccn(pd.DataFrame({"nothing": [1]}))


def test_to_numeric_survives_suppression_markers():
    s = to_numeric(pd.Series(["4.5", "Not Available", "-", "1,200"]))
    assert s[0] == 4.5
    assert pd.isna(s[1]) and pd.isna(s[2])
    assert s[3] == 1200


def test_flag_financial_owner():
    s = pd.Series(["INVESTMENT FIRM", "Individual", "Holding Company", None])
    assert flag_financial_owner(s).tolist() == [True, False, True, False]
