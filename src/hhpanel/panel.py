"""Build stage: snapshots -> agency x snapshot panel with ownership features.

The research object is a balanced-ish panel keyed on (ccn, snapshot_date),
carrying quality outcomes alongside ownership structure, so that within-agency
change in ownership can be lined up against subsequent change in quality.

Join path (this is the part that is easy to get wrong):

    all_owners.enrollment_id  ->  enrollments.enrollment_id
    enrollments.ccn           ->  quality.ccn

Owners are NOT keyed on CCN directly. Anyone who joins the ownership file
straight onto Care Compare is joining on a column that does not exist.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .config import PROCESSED_DIR
from .normalize import (
    add_ccn,
    first_present,
    flag_financial_owner,
    normalize_columns,
    to_numeric,
)

QUALITY_STAR_ALIASES = [
    "quality_of_patient_care_star_rating",
    "quality_of_patient_care_star_rating_1",
    "star_rating",
]
SURVEY_STAR_ALIASES = [
    "hhcahps_survey_summary_star_rating",
    "survey_summary_star_rating",
]
OWNERSHIP_TYPE_ALIASES = ["type_of_ownership", "ownership_type"]
ENROLLMENT_ID_ALIASES = ["enrollment_id", "enrlmt_id", "enrollmentid"]
OWNER_TYPE_ALIASES = [
    "type_owner",
    "owner_type",
    "role_text_owner",
    "role_code_owner",
]
OWNER_ID_ALIASES = ["associate_id_owner", "associate_id", "owner_associate_id"]
PCT_ALIASES = ["percentage_ownership", "percent_ownership", "pct_ownership"]


class SchemaDrift(RuntimeError):
    """CMS renamed a column we depend on."""


def prepare_quality(raw: pd.DataFrame) -> pd.DataFrame:
    df = add_ccn(raw)
    star = first_present(df, QUALITY_STAR_ALIASES)
    if star is None:
        raise SchemaDrift(
            "No quality star rating column in the Care Compare snapshot. "
            f"Columns seen: {sorted(df.columns)[:15]}"
        )
    out = pd.DataFrame(
        {
            "ccn": df["ccn"],
            "snapshot_date": df.get("snapshot_date"),
            "provider_name": df.get("provider_name"),
            "state": df.get("state"),
            "quality_star": to_numeric(df[star]),
        }
    )
    survey = first_present(df, SURVEY_STAR_ALIASES)
    out["survey_star"] = to_numeric(df[survey]) if survey else pd.NA

    declared = first_present(df, OWNERSHIP_TYPE_ALIASES)
    out["declared_ownership_type"] = df[declared] if declared else pd.NA

    return out.drop_duplicates(subset=["ccn", "snapshot_date"])


def prepare_ownership(
    owners_raw: pd.DataFrame, enrollments_raw: pd.DataFrame
) -> pd.DataFrame:
    """Collapse the owner-level file to one row per agency-snapshot."""
    owners = normalize_columns(owners_raw)
    enrollments = add_ccn(enrollments_raw)

    owner_enrl = first_present(owners, ENROLLMENT_ID_ALIASES)
    enrl_enrl = first_present(enrollments, ENROLLMENT_ID_ALIASES)
    if owner_enrl is None or enrl_enrl is None:
        raise SchemaDrift(
            "Cannot bridge owners to agencies: no enrollment id column on "
            f"{'owners' if owner_enrl is None else 'enrollments'}."
        )

    owner_type = first_present(owners, OWNER_TYPE_ALIASES)
    owner_id = first_present(owners, OWNER_ID_ALIASES)
    pct = first_present(owners, PCT_ALIASES)

    work = pd.DataFrame(
        {
            "enrollment_id": owners[owner_enrl].astype(str).str.strip(),
            "owner_id": (
                owners[owner_id].astype(str) if owner_id else owners.index.astype(str)
            ),
            "owner_type": owners[owner_type].astype(str) if owner_type else "",
            "pct": to_numeric(owners[pct]) if pct else pd.NA,
            "snapshot_date": owners.get("snapshot_date"),
        }
    )
    work["is_financial"] = flag_financial_owner(work["owner_type"])

    bridge = pd.DataFrame(
        {
            "enrollment_id": enrollments[enrl_enrl].astype(str).str.strip(),
            "ccn": enrollments["ccn"],
        }
    ).drop_duplicates()

    merged = work.merge(bridge, on="enrollment_id", how="inner")

    grouped = (
        merged.groupby(["ccn", "snapshot_date"], dropna=False)
        .agg(
            owner_count=("owner_id", "nunique"),
            financial_owner_count=("is_financial", "sum"),
            max_owner_pct=("pct", "max"),
        )
        .reset_index()
    )
    grouped["any_financial_owner"] = grouped["financial_owner_count"] > 0
    return grouped


PANEL_SQL = """
WITH joined AS (
    SELECT
        q.ccn,
        q.snapshot_date,
        q.provider_name,
        q.state,
        q.quality_star,
        q.survey_star,
        q.declared_ownership_type,
        COALESCE(o.owner_count, 0)            AS owner_count,
        COALESCE(o.financial_owner_count, 0)  AS financial_owner_count,
        COALESCE(o.any_financial_owner, FALSE) AS any_financial_owner,
        o.max_owner_pct
    FROM quality q
    LEFT JOIN ownership o
      ON q.ccn = o.ccn AND q.snapshot_date = o.snapshot_date
)
SELECT
    *,
    LAG(quality_star) OVER w  AS prev_quality_star,
    quality_star - LAG(quality_star) OVER w AS quality_star_delta,
    LAG(owner_count) OVER w   AS prev_owner_count,
    owner_count - LAG(owner_count) OVER w   AS owner_count_delta,
    CASE
        WHEN LAG(any_financial_owner) OVER w = FALSE
         AND any_financial_owner = TRUE THEN TRUE
        ELSE FALSE
    END AS became_financially_owned
FROM joined
WINDOW w AS (PARTITION BY ccn ORDER BY snapshot_date)
ORDER BY ccn, snapshot_date
"""


def build_panel(
    quality: pd.DataFrame, ownership: pd.DataFrame | None = None
) -> pd.DataFrame:
    if ownership is None or ownership.empty:
        ownership = pd.DataFrame(
            columns=[
                "ccn",
                "snapshot_date",
                "owner_count",
                "financial_owner_count",
                "max_owner_pct",
                "any_financial_owner",
            ]
        )
    con = duckdb.connect()
    con.register("quality", quality)
    con.register("ownership", ownership)
    try:
        return con.execute(PANEL_SQL).df()
    finally:
        con.close()


def summarize(panel: pd.DataFrame) -> pd.DataFrame:
    """One-screen sanity table -- the first thing to look at after a build."""
    return pd.DataFrame(
        [
            {"metric": "agencies", "value": panel["ccn"].nunique()},
            {"metric": "snapshots", "value": panel["snapshot_date"].nunique()},
            {"metric": "rows", "value": len(panel)},
            {
                "metric": "agencies_with_owner_data",
                "value": int((panel["owner_count"] > 0).groupby(panel["ccn"]).any().sum()),
            },
            {
                "metric": "financially_owned_share",
                "value": round(float(panel["any_financial_owner"].mean()), 4),
            },
            {
                "metric": "mean_quality_star",
                "value": round(float(panel["quality_star"].mean(skipna=True)), 3)
                if panel["quality_star"].notna().any()
                else None,
            },
            {
                "metric": "ownership_transitions_observed",
                "value": int(panel["became_financially_owned"].sum()),
            },
        ]
    )


def write_outputs(panel: pd.DataFrame, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    panel_path = out_dir / "panel.parquet"
    summary_path = out_dir / "panel_summary.csv"
    panel.to_parquet(panel_path, index=False)
    summarize(panel).to_csv(summary_path, index=False)
    return {"panel": panel_path, "summary": summary_path}
