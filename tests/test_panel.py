import pandas as pd

from hhpanel.panel import build_panel, prepare_ownership, prepare_quality, summarize


def quality_snapshot(date, star, ccn="017001"):
    return pd.DataFrame(
        {
            "CMS Certification Number (CCN)": [ccn],
            "Provider Name": ["RIVERBEND HOME HEALTH"],
            "State": ["MS"],
            "Quality of Patient Care Star Rating": [star],
            "HHCAHPS Survey Summary Star Rating": [3.5],
            "Type of Ownership": ["Proprietary"],
            "snapshot_date": [date],
        }
    )


def owners_snapshot(date, owner_types):
    return pd.DataFrame(
        {
            "ENROLLMENT_ID": ["O20040101000001"] * len(owner_types),
            "ASSOCIATE_ID_OWNER": [f"A{i}" for i in range(len(owner_types))],
            "TYPE_OWNER": owner_types,
            "PERCENTAGE_OWNERSHIP": [100 / len(owner_types)] * len(owner_types),
            "snapshot_date": [date] * len(owner_types),
        }
    )


def enrollments_snapshot(date):
    return pd.DataFrame(
        {
            "ENROLLMENT_ID": ["O20040101000001"],
            "CCN": ["017001"],
            "ORGANIZATION_NAME": ["RIVERBEND HOME HEALTH LLC"],
            "snapshot_date": [date],
        }
    )


def test_prepare_quality_shapes_outcome_columns():
    out = prepare_quality(quality_snapshot("2026-01-01", "4.5"))
    assert out.loc[0, "ccn"] == "017001"
    assert out.loc[0, "quality_star"] == 4.5
    assert out.loc[0, "declared_ownership_type"] == "Proprietary"


def test_prepare_ownership_bridges_enrollment_to_ccn():
    out = prepare_ownership(
        owners_snapshot("2026-01-01", ["INDIVIDUAL", "INVESTMENT FIRM"]),
        enrollments_snapshot("2026-01-01"),
    )
    assert out.loc[0, "ccn"] == "017001"
    assert out.loc[0, "owner_count"] == 2
    assert out.loc[0, "financial_owner_count"] == 1
    assert bool(out.loc[0, "any_financial_owner"]) is True


def test_ownership_transition_is_detected_across_snapshots():
    quality = pd.concat(
        [
            prepare_quality(quality_snapshot("2026-01-01", "4.5")),
            prepare_quality(quality_snapshot("2026-04-01", "3.5")),
        ],
        ignore_index=True,
    )
    ownership = pd.concat(
        [
            prepare_ownership(
                owners_snapshot("2026-01-01", ["INDIVIDUAL"]),
                enrollments_snapshot("2026-01-01"),
            ),
            prepare_ownership(
                owners_snapshot("2026-04-01", ["INDIVIDUAL", "INVESTMENT FIRM"]),
                enrollments_snapshot("2026-04-01"),
            ),
        ],
        ignore_index=True,
    )

    panel = build_panel(quality, ownership).sort_values("snapshot_date")
    first, second = panel.iloc[0], panel.iloc[1]

    assert bool(first["became_financially_owned"]) is False
    assert bool(second["became_financially_owned"]) is True
    assert second["quality_star_delta"] == -1.0
    assert second["owner_count_delta"] == 1


def test_panel_builds_without_ownership_data():
    quality = prepare_quality(quality_snapshot("2026-01-01", "4.5"))
    panel = build_panel(quality, None)
    assert panel.loc[0, "owner_count"] == 0
    assert bool(panel.loc[0, "any_financial_owner"]) is False


def test_summary_is_one_row_per_metric():
    quality = prepare_quality(quality_snapshot("2026-01-01", "4.5"))
    summary = summarize(build_panel(quality, None))
    assert set(summary.columns) == {"metric", "value"}
    assert summary.loc[summary.metric == "agencies", "value"].iloc[0] == 1
