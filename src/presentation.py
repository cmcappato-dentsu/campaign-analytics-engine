"""Presentación de resultados para la interfaz y archivos descargables."""

import pandas as pd


DISPLAY_COLUMN_LABELS = {
    "date": "Fecha",
    "campaign": "Campaña",
    "campaign_status": "Estado de la campaña",
    "budget": "Presupuesto original",
    "budget_usd": "Presupuesto en USD",
    "budget_name": "Nombre del presupuesto",
    "budget_type": "Tipo de presupuesto",
    "currency": "Moneda original",
    "exchange_rate_to_usd": "Tipo de cambio a USD",
    "status": "Estado",
    "status_reasons": "Motivos del estado",
    "clicks": "Clics",
    "impressions": "Impresiones",
    "conversions": "Conversiones",
    "conversion_value": "Valor de conversiones original",
    "conversion_value_usd": "Valor de conversiones en USD",
    "spend": "Inversión original",
    "spend_usd": "Inversión en USD",
    "network": "Red publicitaria",
    "bid_strategy": "Estrategia de puja",
    "impression_share": "Cuota de impresiones",
    "lost_is_rank": "Cuota perdida por ranking",
    "lost_is_budget": "Cuota perdida por presupuesto",
    "ctr": "CTR (tasa de clics)",
    "cpc": "CPC en USD",
    "cpm": "CPM en USD",
    "conversion_rate": "Tasa de conversión",
    "cpa": "CPA en USD",
    "roas": "ROAS (retorno de inversión publicitaria)",
}

INTEGER_COLUMNS = {"clicks", "impressions"}
ORIGINAL_MONEY_COLUMNS = {"budget", "conversion_value", "spend"}
USD_MONEY_COLUMNS = {
    "budget_usd",
    "conversion_value_usd",
    "spend_usd",
    "cpc",
    "cpm",
    "cpa",
}
PERCENTAGE_COLUMNS = {
    "ctr",
    "conversion_rate",
    "impression_share",
    "lost_is_rank",
    "lost_is_budget",
}


def format_integer(value) -> str:
    """Formatea enteros con separador de miles para una interfaz en español."""

    if pd.isna(value):
        return "—"
    return f"{float(value):,.0f}".replace(",", ".")


def format_decimal(value, decimals: int = 2) -> str:
    """Formatea decimales con punto de miles y coma decimal."""

    if pd.isna(value):
        return "—"
    formatted = f"{float(value):,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_currency(value, currency: str = "USD") -> str:
    """Formatea un importe monetario con dos decimales."""

    if pd.isna(value):
        return "—"
    return f"{currency} {format_decimal(value)}"


def format_percentage(value) -> str:
    """Formatea proporciones como porcentaje con un decimal."""

    if pd.isna(value):
        return "—"
    percentage = float(value) * 100 if abs(float(value)) <= 1 else float(value)
    return f"{format_decimal(percentage, decimals=1)}%"


def to_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una copia con nombres de columnas orientados al usuario."""

    display = df.copy()

    if "date" in display.columns:
        display["date"] = pd.to_datetime(
            display["date"], errors="coerce"
        ).dt.strftime("%d/%m/%Y").fillna("—")

    for column in INTEGER_COLUMNS.intersection(display.columns):
        display[column] = display[column].map(format_integer)

    for column in ORIGINAL_MONEY_COLUMNS.intersection(display.columns):
        display[column] = display.apply(
            lambda row: format_currency(row[column], row.get("currency", "USD")),
            axis=1,
        )

    for column in USD_MONEY_COLUMNS.intersection(display.columns):
        display[column] = display[column].map(format_currency)

    for column in PERCENTAGE_COLUMNS.intersection(display.columns):
        display[column] = display[column].map(format_percentage)

    if "conversions" in display.columns:
        display["conversions"] = display["conversions"].map(format_decimal)
    if "roas" in display.columns:
        display["roas"] = display["roas"].map(format_decimal)
    if "exchange_rate_to_usd" in display.columns:
        display["exchange_rate_to_usd"] = display[
            "exchange_rate_to_usd"
        ].map(lambda value: format_decimal(value, decimals=6))

    return display.rename(
        columns={
            column: DISPLAY_COLUMN_LABELS.get(column, column)
            for column in df.columns
        }
    )
