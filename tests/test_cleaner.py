import pandas as pd
import pytest

from src.cleaner import clean_dates, clean_numeric_columns, derive_impression_share


def test_iso_dates_are_not_parsed_as_day_first():
    df = pd.DataFrame({"date": ["2026-08-01", "01/08/2026"]})

    result = clean_dates(df)

    assert result.loc[0, "date"] == pd.Timestamp("2026-08-01")
    assert result.loc[1, "date"] == pd.Timestamp("2026-08-01")


def test_google_ads_thousands_separators_are_cleaned():
    df = pd.DataFrame({
        "clicks": ["2,877"],
        "impressions": ["10,000"],
        "spend": ["181,709.52"],
    })

    result = clean_numeric_columns(df)

    assert result.loc[0, "clicks"] == 2877
    assert result.loc[0, "impressions"] == 10000
    assert result.loc[0, "spend"] == 181709.52


def test_percentage_columns_are_normalized_to_fractions():
    df = pd.DataFrame({
        "lost_is_budget": ["70.97%"],
        "lost_is_rank": ["29.03%"],
        "impression_share": ["--"],
    })

    result = clean_numeric_columns(df)

    assert result.loc[0, "lost_is_budget"] == pytest.approx(0.7097)
    assert result.loc[0, "lost_is_rank"] == pytest.approx(0.2903)
    assert pd.isna(result.loc[0, "impression_share"])


def test_impression_share_is_derived_from_lost_shares():
    df = pd.DataFrame({
        "lost_is_budget": [0.10],
        "lost_is_rank": [0.20],
    })

    result = derive_impression_share(df)

    assert result.loc[0, "impression_share"] == pytest.approx(0.70)
