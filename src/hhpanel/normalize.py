"""Turning CMS's inconsistent column naming into something joinable.

CMS ships the same identifier as ``CMS Certification Number (CCN)``,
``CCN``, ``PRVDR_NUM``, and ``ccn`` depending on which office published the
file. Everything downstream assumes these helpers have already run.
"""

from __future__ import annotations

import re

import pandas as pd

CCN_ALIASES = [
    "ccn",
    "cms_certification_number_ccn",
    "cms_certification_number",
    "prvdr_num",
    "provider_number",
    "federal_provider_number",
]

STATE_ALIASES = ["state", "state_cd", "provider_state", "state_abbreviation"]

NAME_ALIASES = [
    "provider_name",
    "organization_name",
    "doing_business_as_name",
    "associate_id_owner_name",
    "legal_business_name",
]

# Owner-type keywords that flag financial (as opposed to operating) ownership.
# This is a HEURISTIC, not a CMS-sanctioned classification -- see docs.
FINANCIAL_OWNER_PATTERNS = [
    "investment firm",
    "private equity",
    "holding company",
    "bank or financial",
    "real estate investment",
    "management services",
]


def snake(name: str) -> str:
    name = re.sub(r"[^\w\s]", " ", str(name))
    name = re.sub(r"\s+", "_", name.strip())
    return re.sub(r"_+", "_", name).lower()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [snake(c) for c in df.columns]
    return df


def first_present(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def normalize_ccn(value) -> str | None:
    """CCNs are 6-character, zero-padded, and frequently mangled by Excel."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "NA"}:
        return None
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def add_ccn(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee a canonical ``ccn`` column, or raise something readable."""
    df = normalize_columns(df)
    column = first_present(df, CCN_ALIASES)
    if column is None:
        raise KeyError(
            "No CMS Certification Number column found. Saw: "
            f"{sorted(df.columns)[:12]}... "
            "Add the real column name to CCN_ALIASES in normalize.py."
        )
    df["ccn"] = df[column].map(normalize_ccn)
    return df.dropna(subset=["ccn"])


def to_numeric(series: pd.Series) -> pd.Series:
    """CMS encodes suppressed values as text ('Not Available', '-', '*')."""
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def flag_financial_owner(series: pd.Series) -> pd.Series:
    lowered = series.astype(str).str.lower()
    hit = pd.Series(False, index=series.index)
    for pattern in FINANCIAL_OWNER_PATTERNS:
        hit |= lowered.str.contains(pattern, regex=False, na=False)
    return hit
