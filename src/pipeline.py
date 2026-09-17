from src.loader import load_report
from src.cleaner import clean_report
from src.metrics import (
    aggregate_by_campaign,
    calculate_derived_metrics
)
from src.currency import (
    ExchangeRateSnapshot,
    add_usd_conversion_columns,
    fetch_usd_exchange_rates,
)


def run_ingestion_pipeline(
    file_path: str,
    source: str | None = None,
    exchange_rate_snapshot: ExchangeRateSnapshot | None = None,
):

    # 1. Cargar
    df = load_report(file_path, source=source)

    # 2. Limpiar
    df = clean_report(df)

    if df.empty:
        raise ValueError(
            "El reporte no contiene filas válidas después de la limpieza."
        )

    # 3. Unificar los importes a USD antes de calcular métricas monetarias.
    snapshot = exchange_rate_snapshot or fetch_usd_exchange_rates()
    df = add_usd_conversion_columns(df, snapshot)

    # 4. Dataset diario
    df_daily = calculate_derived_metrics(df)

    # 5. Dataset agregado por campaña
    df_campaign = aggregate_by_campaign(df)

    df_campaign = calculate_derived_metrics(
        df_campaign
    )

    return {
        "daily": df_daily,
        "campaign": df_campaign,
        "currency": {
            "target": "USD",
            "updated_at": snapshot.updated_at,
            "provider": snapshot.provider,
        },
    }
