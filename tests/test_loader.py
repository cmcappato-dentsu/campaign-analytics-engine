import pandas as pd

from config.column_mapping import (
    rename_columns_to_canonical
)


def test_spanish_columns_are_mapped():

    df = pd.DataFrame({
        "Campaña": ["Campaign A"],
        "Clics": [100],
        "Impr.": [1000],
        "Conversiones": [5],
        "Costo": [200],
    })

    result = rename_columns_to_canonical(df)

    assert "campaign" in result.columns
    assert "clicks" in result.columns
    assert "impressions" in result.columns
    assert "conversions" in result.columns
    assert "spend" in result.columns


def test_english_columns_are_mapped():

    df = pd.DataFrame({
        "Campaign": ["Campaign A"],
        "Clicks": [100],
        "Impressions": [1000],
        "Conversions": [5],
        "Cost": [200],
    })

    result = rename_columns_to_canonical(df)

    assert "campaign" in result.columns
    assert "clicks" in result.columns
    assert "impressions" in result.columns
    assert "conversions" in result.columns
    assert "spend" in result.columns