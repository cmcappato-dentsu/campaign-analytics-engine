import pandas as pd

from src.analysis import (
    build_campaign_pareto,
    build_daily_performance,
    top_campaigns_by_spend,
)


def test_daily_performance_aggregates_and_calculates_metrics():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-01", "2026-08-01", "2026-08-02"]),
        "spend_usd": [10.0, 20.0, 30.0],
        "clicks": [10, 20, 30],
        "impressions": [100, 200, 300],
        "conversions": [2, 3, 5],
    })

    result = build_daily_performance(df)

    assert len(result) == 2
    assert result.loc[0, "spend_usd"] == 30
    assert result.loc[0, "ctr"] == 0.1
    assert result.loc[0, "cpa"] == 6


def test_top_campaigns_uses_usd_investment():
    df = pd.DataFrame({
        "campaign": ["A", "B", "C"],
        "spend_usd": [10, 30, 20],
    })

    result = top_campaigns_by_spend(df, limit=2)

    assert result["campaign"].tolist() == ["B", "C"]


def test_campaign_pareto_calculates_cumulative_shares():
    df = pd.DataFrame({
        "campaign": ["A", "B", "C"],
        "spend_usd": [50, 30, 20],
        "conversions": [5, 3, 2],
    })

    result = build_campaign_pareto(df)

    assert result["campaign"].tolist() == ["A", "B", "C"]
    assert result.loc[0, "cumulative_investment_share"] == 0.5
    assert result.loc[1, "cumulative_conversion_share"] == 0.8
