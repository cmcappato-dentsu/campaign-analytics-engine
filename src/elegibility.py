"""Criterios de elegibilidad para análisis de campañas."""

import pandas as pd
import numpy as np

from config.thresholds import (
    MIN_CLICKS_FOR_ANALYSIS,
    MIN_INVESTMENT_SHARE,
    MIN_ACTIVE_DAYS,
)


class EligibilityResult:
    """Resultado de elegibilidad por campaña."""

    ELIGIBLE = "eligible"
    INSUFFICIENT_VOLUME = "insufficient_volume"
    INSUFFICIENT_HISTORY = "insufficient_history"
    SPEND_NO_RESULTS = "spend_no_results"

    LABELS = {
        ELIGIBLE: "Elegible para análisis",
        INSUFFICIENT_VOLUME: "Volumen insuficiente para análisis",
        INSUFFICIENT_HISTORY: "Historial insuficiente (< 7 días)",
        SPEND_NO_RESULTS: "Gasto sin resultados (clics/conversiones = 0)",
    }


def calculate_active_days(df_daily: pd.DataFrame, campaign_col: str = "campaign") -> pd.Series:
    """Calcula días activos por campaña a partir del dataset diario."""

    return df_daily.groupby(campaign_col)["date"].nunique()


def evaluate_eligibility(
    df_campaign: pd.DataFrame,
    df_daily: pd.DataFrame,
    spend_threshold_no_results: float | None = None,
) -> pd.DataFrame:
    """
    Evalúa elegibilidad de cada campaña para análisis diagnóstico.

    Reglas (según roadmap Etapa 2, punto 1):
    - Piso mínimo: ≥100 clics O ≥1% inversión total de la cuenta
    - Excepción: gasto > umbral (1 día presupuesto promedio) con 0 clics O 0 conversiones
    - Campañas <7 días activas: "datos insuficientes, esperar más historial"

    Args:
        df_campaign: Dataset agregado por campaña (con spend_usd, clicks, conversions)
        df_daily: Dataset diario para calcular días activos
        spend_threshold_no_results: Umbral de gasto para excepción "gasto sin resultados".
                                    Si None, se calcula como gasto total / días únicos * 1 (promedio día)

    Returns:
        DataFrame con columnas: campaign, eligibility_status, eligibility_reason, is_eligible
    """

    df = df_campaign.copy()
    total_spend = df["spend_usd"].sum()
    total_clicks = df["clicks"].sum()

    if spend_threshold_no_results is None:
        unique_days = df_daily["date"].nunique()
        avg_daily_spend = total_spend / unique_days if unique_days > 0 else 0
        spend_threshold_no_results = avg_daily_spend

    active_days = calculate_active_days(df_daily)
    df = df.merge(active_days.rename("active_days"), left_on="campaign", right_index=True, how="left")
    df["active_days"] = df["active_days"].fillna(0).astype(int)

    df["investment_share"] = np.where(
        total_spend > 0,
        df["spend_usd"] / total_spend,
        0,
    )

    def _evaluate(row):
        campaign = row["campaign"]
        clicks = row["clicks"]
        conversions = row["conversions"]
        spend = row["spend_usd"]
        inv_share = row["investment_share"]
        active_days = row["active_days"]

        # 1. Campañas nuevas (< 7 días) -> insuficiente historial
        if active_days < MIN_ACTIVE_DAYS:
            return pd.Series({
                "eligibility_status": EligibilityResult.INSUFFICIENT_HISTORY,
                "eligibility_reason": f"Campaña con {active_days} días activa (mínimo {MIN_ACTIVE_DAYS})",
                "is_eligible": False,
            })

        # 2. Excepción: gasto alto sin resultados (0 clics O 0 conversiones)
        if spend > spend_threshold_no_results and (clicks == 0 or conversions == 0):
            return pd.Series({
                "eligibility_status": EligibilityResult.SPEND_NO_RESULTS,
                "eligibility_reason": (
                    f"Gasto ${spend:,.2f} > umbral ${spend_threshold_no_results:,.2f} "
                    f"con {'0 clics' if clicks == 0 else '0 conversiones'}"
                ),
                "is_eligible": True,  # Se analiza SÍ o SÍ por ser caso extremo
            })

        # 3. Piso mínimo de volumen: 100 clics O 1% inversión total
        meets_clicks = clicks >= MIN_CLICKS_FOR_ANALYSIS
        meets_investment_share = inv_share >= MIN_INVESTMENT_SHARE

        if meets_clicks or meets_investment_share:
            return pd.Series({
                "eligibility_status": EligibilityResult.ELIGIBLE,
                "eligibility_reason": (
                    f"Clics: {clicks:,.0f} (≥{MIN_CLICKS_FOR_ANALYSIS}) "
                    f"| Part. inversión: {inv_share:.1%} (≥{MIN_INVESTMENT_SHARE:.0%})"
                ),
                "is_eligible": True,
            })

        # 4. No cumple piso mínimo
        return pd.Series({
            "eligibility_status": EligibilityResult.INSUFFICIENT_VOLUME,
            "eligibility_reason": (
                f"Clics: {clicks:,.0f} (<{MIN_CLICKS_FOR_ANALYSIS}) "
                f"| Part. inversión: {inv_share:.1%} (<{MIN_INVESTMENT_SHARE:.0%})"
            ),
            "is_eligible": False,
        })

    result = df.apply(_evaluate, axis=1)
    df = pd.concat([df, result], axis=1)

    return df[["campaign", "eligibility_status", "eligibility_reason", "is_eligible", "active_days"]]


def get_eligible_campaigns(df_campaign: pd.DataFrame, df_daily: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Retorna solo campañas elegibles para análisis de benchmark/outliers."""

    eligibility = evaluate_eligibility(df_campaign, df_daily, **kwargs)
    eligible = eligibility[eligibility["is_eligible"]]["campaign"].tolist()
    return df_campaign[df_campaign["campaign"].isin(eligible)].copy()


def get_eligibility_summary(eligibility_df: pd.DataFrame) -> dict:
    """Genera resumen de elegibilidad para reporte."""

    counts = eligibility_df["eligibility_status"].value_counts().to_dict()
    return {
        "total_campaigns": len(eligibility_df),
        "eligible": counts.get(EligibilityResult.ELIGIBLE, 0),
        "insufficient_volume": counts.get(EligibilityResult.INSUFFICIENT_VOLUME, 0),
        "insufficient_history": counts.get(EligibilityResult.INSUFFICIENT_HISTORY, 0),
        "spend_no_results": counts.get(EligibilityResult.SPEND_NO_RESULTS, 0),
    }