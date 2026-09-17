import pandas as pd

from src.cleaner import clean_dates, clean_numeric_columns


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
