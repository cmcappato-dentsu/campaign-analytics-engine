import numpy as np
import pandas as pd


def aggregate_by_campaign(df):

    aggregation_rules = {
        "clicks": "sum",
        "impressions": "sum",
        "conversions": "sum",
    }

    spend_column = "spend_usd" if "spend_usd" in df.columns else "spend"
    aggregation_rules[spend_column] = "sum"

    conversion_value_column = (
        "conversion_value_usd"
        if "conversion_value_usd" in df.columns
        else "conversion_value"
    )
    if conversion_value_column in df.columns:
        aggregation_rules[conversion_value_column] = "sum"

    group_columns = ["campaign"]
    if "currency" in df.columns and spend_column == "spend":
        group_columns.append("currency")

    result = (
        df.groupby(
            group_columns,
            as_index=False,
            dropna=False,
        )
        .agg(aggregation_rules)
    )

    return result


def calculate_derived_metrics(df):

    df = df.copy()
    spend_column = "spend_usd" if "spend_usd" in df.columns else "spend"
    conversion_value_column = (
        "conversion_value_usd"
        if "conversion_value_usd" in df.columns
        else "conversion_value"
    )

    df["ctr"] = np.where(
        df["impressions"] > 0,
        df["clicks"] / df["impressions"],
        np.nan
    )

    df["cpc"] = np.where(
        df["clicks"] > 0,
        df[spend_column] / df["clicks"],
        np.nan
    )

    df["cpm"] = np.where(
        df["impressions"] > 0,
        (
            df[spend_column] /
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
        df[spend_column] / df["conversions"],
        np.nan
    )

    if conversion_value_column in df.columns:

        df["roas"] = np.where(
            df[spend_column] > 0,
            df[conversion_value_column] / df[spend_column],
            np.nan
        )

    return df
