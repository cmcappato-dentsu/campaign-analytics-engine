"""Datasets agregados para visualizaciones de performance."""

import numpy as np
import pandas as pd


def build_daily_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Consolida las métricas diarias necesarias para los gráficos."""

    daily = (
        df.groupby("date", as_index=False)
        .agg({
            "spend_usd": "sum",
            "clicks": "sum",
            "impressions": "sum",
            "conversions": "sum",
        })
        .sort_values("date")
    )
    daily["ctr"] = np.where(
        daily["impressions"] > 0,
        daily["clicks"] / daily["impressions"],
        np.nan,
    )
    daily["cpa"] = np.where(
        daily["conversions"] > 0,
        daily["spend_usd"] / daily["conversions"],
        np.nan,
    )
    return daily


def top_campaigns_by_spend(
    df: pd.DataFrame,
    limit: int = 10,
) -> pd.DataFrame:
    """Obtiene las campañas de mayor inversión en USD."""

    return df.nlargest(limit, "spend_usd").copy()


def build_campaign_pareto(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula la concentración acumulada de inversión y conversiones."""

    pareto = df.sort_values("spend_usd", ascending=False).reset_index(drop=True).copy()
    total_spend = pareto["spend_usd"].sum()
    total_conversions = pareto["conversions"].sum()

    pareto["campaign_rank"] = pareto.index + 1
    pareto["investment_share"] = np.where(
        total_spend > 0,
        pareto["spend_usd"] / total_spend,
        0,
    )
    pareto["cumulative_investment_share"] = pareto["investment_share"].cumsum()
    pareto["cumulative_conversion_share"] = np.where(
        total_conversions > 0,
        pareto["conversions"].cumsum() / total_conversions,
        0,
    )
    return pareto
