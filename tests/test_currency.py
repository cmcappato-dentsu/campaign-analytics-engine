import pandas as pd
import pytest

from src.currency import (
    CurrencyConversionError,
    ExchangeRateSnapshot,
    add_usd_conversion_columns,
)


def test_usd_columns_are_added_without_overwriting_original_values():
    df = pd.DataFrame({
        "currency": ["ARS", "USD"],
        "spend": [1500.0, 20.0],
        "conversion_value": [3000.0, 40.0],
    })
    snapshot = ExchangeRateSnapshot(
        rates={"ARS": 1500.0, "USD": 1.0},
        updated_at="2026-09-17",
        provider="test",
    )

    result = add_usd_conversion_columns(df, snapshot)

    assert result["currency"].tolist() == ["ARS", "USD"]
    assert result["spend"].tolist() == [1500.0, 20.0]
    assert result["conversion_value"].tolist() == [3000.0, 40.0]
    assert result["spend_usd"].tolist() == [1.0, 20.0]
    assert result["conversion_value_usd"].tolist() == [2.0, 40.0]


def test_unsupported_currency_is_reported():
    df = pd.DataFrame({"currency": ["XXX"], "spend": [10.0]})
    snapshot = ExchangeRateSnapshot(
        rates={"USD": 1.0}, updated_at=None, provider="test"
    )

    with pytest.raises(CurrencyConversionError, match="XXX"):
        add_usd_conversion_columns(df, snapshot)
