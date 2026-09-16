import numpy as np
import pandas as pd


def aggregate_by_campaign(df):

    aggregation_rules = {
        "clicks": "sum",
        "impressions": "sum",
        "conversions": "sum",
        "spend": "sum",
    }

    if "conversion_value" in df.columns:

        aggregation_rules[
            "conversion_value"
        ] = "sum"

    return (
        df.groupby(
            "campaign",
            as_index=False
        )
        .agg(aggregation_rules)
    )


def calculate_derived_metrics(df):

    df = df.copy()

    df["ctr"] = np.where(
        df["impressions"] > 0,
        df["clicks"] / df["impressions"],
        np.nan
    )

    df["cpc"] = np.where(
        df["clicks"] > 0,
        df["spend"] / df["clicks"],
        np.nan
    )

    df["cpm"] = np.where(
        df["impressions"] > 0,
        (
            df["spend"] /
            df["impressions"]
        ) * 1000,
        np.nan
    )

    df["conversion_rate"] = np.where(
        df["clicks"] > 0,
        df["conversions"] / df["clicks"],
        np.nan
    )

    df["cpa"] = np.where(
        df["conversions"] > 0,
        df["spend"] / df["conversions"],
        np.nan
    )

    if "conversion_value" in df.columns:

        df["roas"] = np.where(
            df["spend"] > 0,
            df["conversion_value"] / df["spend"],
            np.nan
        )

    return df