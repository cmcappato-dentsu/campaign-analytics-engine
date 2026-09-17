import pandas as pd

from config.column_mapping import (
    rename_columns_to_canonical
)
from src.loader import load_report
from src.sources import available_sources


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


def test_sources_are_exposed_through_registry():
    sources = available_sources()

    assert "google_ads" in sources
    assert sources["google_ads"].label == "Google Ads"


def test_generic_loader_can_use_registered_source():
    result = load_report("data/input/GADS ENG.csv", source="google_ads")

    assert len(result) > 0
    assert {"date", "campaign", "spend"}.issubset(result.columns)
