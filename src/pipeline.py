from src.loader import load_google_ads_report
from src.cleaner import clean_google_ads_report
from src.metrics import (
    aggregate_by_campaign,
    calculate_derived_metrics
)


def run_ingestion_pipeline(file_path: str):

    # 1. Cargar
    df = load_google_ads_report(file_path)

    # 2. Limpiar
    df = clean_google_ads_report(df)

    # 3. Dataset diario
    df_daily = calculate_derived_metrics(df)

    # 4. Dataset agregado por campaña
    df_campaign = aggregate_by_campaign(df)

    df_campaign = calculate_derived_metrics(
        df_campaign
    )

    return {
        "daily": df_daily,
        "campaign": df_campaign,
    }