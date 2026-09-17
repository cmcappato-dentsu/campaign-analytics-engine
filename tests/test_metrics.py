import pandas as pd

from src.metrics import calculate_derived_metrics


def test_derived_metrics_are_calculated():
    df = pd.DataFrame({
        "clicks": [100],
        "impressions": [1000],
        "conversions": [5],
        "spend": [200],
        "conversion_value": [600],
    })

    result = calculate_derived_metrics(df)

    assert result.loc[0, "ctr"] == 0.1
    assert result.loc[0, "cpc"] == 2
    assert result.loc[0, "cpa"] == 40
    assert result.loc[0, "roas"] == 3


def test_campaign_aggregation_keeps_currencies_separate():
    from src.metrics import aggregate_by_campaign

    df = pd.DataFrame({
        "campaign": ["A", "A"],
        "currency": ["ARS", "USD"],
        "clicks": [10, 20],
        "impressions": [100, 200],
        "conversions": [1, 2],
        "spend": [1000, 10],
    })

    result = aggregate_by_campaign(df)

    assert len(result) == 2
    assert set(result["currency"]) == {"ARS", "USD"}


def test_usd_values_are_used_for_monetary_metrics_and_aggregation():
    from src.metrics import aggregate_by_campaign

    df = pd.DataFrame({
        "campaign": ["A", "A"],
        "currency": ["ARS", "USD"],
        "clicks": [10, 10],
        "impressions": [100, 100],
        "conversions": [2, 2],
        "spend": [1500, 10],
        "spend_usd": [1, 10],
    })

    metrics = calculate_derived_metrics(df)
    aggregated = aggregate_by_campaign(df)

    assert metrics.loc[0, "cpc"] == 0.1
    assert len(aggregated) == 1
    assert aggregated.loc[0, "spend_usd"] == 11
