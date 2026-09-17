"""Conversión de importes publicitarios a una moneda de referencia."""

from dataclasses import dataclass
from typing import Mapping

import pandas as pd
import requests


EXCHANGE_RATE_API_URL = "https://open.er-api.com/v6/latest/USD"
TARGET_CURRENCY = "USD"
MONETARY_COLUMNS = ("budget", "conversion_value", "spend")
USD_COLUMN_NAMES = {
    "budget": "budget_usd",
    "conversion_value": "conversion_value_usd",
    "spend": "spend_usd",
}


class CurrencyConversionError(ValueError):
    """Indica que no fue posible obtener o aplicar una cotización."""


@dataclass(frozen=True)
class ExchangeRateSnapshot:
    """Cotizaciones expresadas como unidades de moneda por USD."""

    rates: Mapping[str, float]
    updated_at: str | None
    provider: str


def fetch_usd_exchange_rates() -> ExchangeRateSnapshot:
    """Obtiene cotizaciones públicas actualizadas con USD como moneda base."""

    try:
        response = requests.get(EXCHANGE_RATE_API_URL, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise CurrencyConversionError(
            "No fue posible consultar las cotizaciones para convertir a USD."
        ) from error

    if payload.get("result") != "success" or payload.get("base_code") != TARGET_CURRENCY:
        raise CurrencyConversionError(
            "La API de cotizaciones devolvió una respuesta no válida."
        )

    rates = {
        str(currency).upper(): float(rate)
        for currency, rate in payload.get("rates", {}).items()
    }
    rates[TARGET_CURRENCY] = 1.0

    return ExchangeRateSnapshot(
        rates=rates,
        updated_at=payload.get("time_last_update_utc"),
        provider="ExchangeRate-API",
    )


def add_usd_conversion_columns(
    df: pd.DataFrame,
    snapshot: ExchangeRateSnapshot,
) -> pd.DataFrame:
    """Agrega importes en USD sin modificar los valores ni la moneda de origen."""

    if "currency" not in df.columns:
        raise CurrencyConversionError(
            "El reporte debe incluir una columna de moneda para convertir los importes a USD."
        )

    result = df.copy()
    source_currency = result["currency"].astype("string").str.strip().str.upper()
    missing_currency = source_currency.isna() | source_currency.eq("")
    if missing_currency.any():
        raise CurrencyConversionError(
            "Hay filas sin moneda; no es posible convertir todos los importes a USD."
        )

    rates = source_currency.map(snapshot.rates)
    unsupported = sorted(source_currency[rates.isna()].unique().tolist())
    if unsupported:
        raise CurrencyConversionError(
            "No hay cotización disponible a USD para: " + ", ".join(unsupported)
        )

    result["exchange_rate_to_usd"] = 1 / rates

    for column in MONETARY_COLUMNS:
        if column in result.columns:
            result[USD_COLUMN_NAMES[column]] = (
                result[column] * result["exchange_rate_to_usd"]
            )

    return result
