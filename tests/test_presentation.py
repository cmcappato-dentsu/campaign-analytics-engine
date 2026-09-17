import pandas as pd

from src.presentation import (
    format_currency,
    format_integer,
    format_percentage,
    to_display_frame,
)


def test_results_use_descriptive_column_names():
    df = pd.DataFrame({
        "campaign": ["Campaña A"],
        "impressions": [1000],
        "spend": [200],
        "ctr": [0.1],
    })

    result = to_display_frame(df)

    assert list(result.columns) == [
        "Campaña",
        "Impresiones",
        "Inversión original",
        "CTR (tasa de clics)",
    ]


def test_numeric_formats_follow_spanish_display_rules():
    assert format_integer(1234567) == "1.234.567"
    assert format_currency(1234.5) == "USD 1.234,50"
    assert format_percentage(0.1234) == "12,3%"
