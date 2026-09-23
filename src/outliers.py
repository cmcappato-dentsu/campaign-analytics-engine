"""Detección de outliers críticos (casos extremos)."""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional

from config.thresholds import (
    OUTLIER_ZSCORE_THRESHOLD,
    MIN_CLICKS_FOR_ANALYSIS,
    MIN_INVESTMENT_SHARE,
)


@dataclass
class OutlierFinding:
    """Hallazgo de outlier crítico."""
    campaign: str
    outlier_type: str
    severity: str  # "critical"
    message: str
    metric_value: float | None = None
    threshold_value: float | None = None
    zscore: float | None = None


class OutlierTypes:
    """Tipos de outliers críticos."""
    SPEND_NO_CLICKS = "spend_no_clicks"
    SPEND_NO_CONVERSIONS = "spend_no_conversions"
    CTR_EXTREME = "ctr_extreme"
    CPC_EXTREME = "cpc_extreme"
    CPA_EXTREME = "cpa_extreme"
    IMPRESSION_SHARE_COLLAPSE = "impr_share_collapse"
    CONVERSIONS_COLLAPSE = "conversions_collapse"


def detect_spend_no_results(
    df_campaign: pd.DataFrame,
    spend_threshold: float,
) -> list[OutlierFinding]:
    """
    Outlier crítico: Gasto > umbral con 0 clics O 0 conversiones.
    Roadmap Etapa 2, punto 5: "Campaña con inversión por encima del umbral
    de la excepción del punto 1 y cero clics o cero conversiones."
    """
    findings = []

    for _, row in df_campaign.iterrows():
        campaign = row["campaign"]
        spend = row.get("spend_usd", 0)
        clicks = row.get("clicks", 0)
        conversions = row.get("conversions", 0)

        if spend > spend_threshold:
            if clicks == 0:
                findings.append(OutlierFinding(
                    campaign=campaign,
                    outlier_type=OutlierTypes.SPEND_NO_CLICKS,
                    severity="critical",
                    message=(
                        f"La campaña '{campaign}' gastó ${spend:,.2f} "
                        f"(> umbral ${spend_threshold:,.2f}) y no generó "
                        f"ni un solo clic. Revisar configuración urgentemente."
                    ),
                    metric_value=spend,
                    threshold_value=spend_threshold,
                ))

            if conversions == 0 and clicks > 0:
                findings.append(OutlierFinding(
                    campaign=campaign,
                    outlier_type=OutlierTypes.SPEND_NO_CONVERSIONS,
                    severity="critical",
                    message=(
                        f"La campaña '{campaign}' gastó ${spend:,.2f} "
                        f"con {int(clicks)} clics pero 0 conversiones. "
                        f"Posible problema en landing page, oferta o tracking."
                    ),
                    metric_value=spend,
                    threshold_value=spend_threshold,
                ))

    return findings


def detect_metric_outliers_zscore(
    df_campaign: pd.DataFrame,
    df_benchmark: pd.DataFrame,
    eligible_campaigns: Optional[list[str]] = None,
) -> list[OutlierFinding]:
    """
    Detecta outliers usando z-score vs benchmark histórico.
    Roadmap: "Variación mayor al doble del umbral normal en un solo corte".
    """
    findings = []

    if df_benchmark.empty:
        return findings

    benchmark_map = df_benchmark.set_index(["campaign", "metric"])["benchmark_value"].to_dict()

    # Métricas y sus umbrales base (el doble = outlier)
    metric_thresholds = {
        "ctr": 0.25,
        "cpc": 0.25,
        "cpa": 0.30,
        "impression_share": 0.10,
        "conversions": 0.30,
        "conversion_rate": 0.30,
    }

    for _, row in df_campaign.iterrows():
        campaign = row["campaign"]

        if eligible_campaigns and campaign not in eligible_campaigns:
            continue

        for metric, base_threshold in metric_thresholds.items():
            if metric not in row or pd.isna(row[metric]):
                continue

            current = row[metric]
            bench = benchmark_map.get((campaign, metric))

            if not bench or bench == 0:
                continue

            variation = (current - bench) / bench
            outlier_threshold = 2 * base_threshold  # doble del umbral normal

            is_outlier = False
            direction = ""

            if metric in ["ctr"]:
                if abs(variation) > outlier_threshold:
                    is_outlier = True
                    direction = "subió" if variation > 0 else "bajó"
            elif metric in ["cpc", "cpa"]:
                if variation > outlier_threshold:
                    is_outlier = True
                    direction = "subió"
            elif metric in ["impression_share"]:
                drop = bench - current
                if drop > outlier_threshold:  # caída en puntos porcentuales
                    is_outlier = True
                    direction = "colapsó"
                    variation = -drop / bench
            elif metric in ["conversions", "conversion_rate"]:
                if variation < -outlier_threshold:
                    is_outlier = True
                    direction = "colapsó"

            if is_outlier:
                zscore = abs(variation) / base_threshold if base_threshold > 0 else 0
                findings.append(OutlierFinding(
                    campaign=campaign,
                    outlier_type=f"{metric}_extreme",
                    severity="critical",
                    message=(
                        f"La campaña '{campaign}' tiene {metric.upper()} que {direction} "
                        f"{abs(variation):.0%} vs benchmark ({bench:.4f} → {current:.4f}). "
                        f"Variación de {zscore:.1f}x el umbral normal ({base_threshold:.0%}). "
                        f"Requiere atención inmediata."
                    ),
                    metric_value=current,
                    threshold_value=bench,
                    zscore=zscore,
                ))

    return findings


def detect_statistical_outliers(
    df_campaign: pd.DataFrame,
    metrics: list[str] = None,
    zscore_threshold: float = OUTLIER_ZSCORE_THRESHOLD,
) -> list[OutlierFinding]:
    """
    Detecta outliers estadísticos usando z-score dentro de la cuenta actual.
    Útil para detectar campañas que se comportan muy distinto al resto de la cuenta.
    """
    findings = []

    if metrics is None:
        metrics = ["ctr", "cpc", "cpa", "spend_usd", "conversions", "conversion_rate"]

    available_metrics = [m for m in metrics if m in df_campaign.columns]
    if not available_metrics:
        return findings

    for metric in available_metrics:
        values = df_campaign[metric].dropna()
        if len(values) < 3:  # Mínimo para calcular std significativo
            continue

        mean_val = values.mean()
        std_val = values.std()

        if std_val == 0:
            continue

        for _, row in df_campaign.iterrows():
            val = row[metric]
            if pd.isna(val):
                continue

            zscore = abs(val - mean_val) / std_val

            if zscore > zscore_threshold:
                direction = "muy por encima" if val > mean_val else "muy por debajo"
                findings.append(OutlierFinding(
                    campaign=row["campaign"],
                    outlier_type=f"{metric}_statistical_outlier",
                    severity="high",
                    message=(
                        f"La campaña '{row['campaign']}' tiene {metric.upper()} "
                        f"{direction} del promedio de la cuenta "
                        f"({mean_val:.4f} ± {std_val:.4f}, z-score: {zscore:.1f}). "
                        f"Valor actual: {val:.4f}."
                    ),
                    metric_value=val,
                    threshold_value=mean_val,
                    zscore=zscore,
                ))

    return findings


def run_outlier_detection(
    df_campaign: pd.DataFrame,
    df_daily: pd.DataFrame,
    df_benchmark: pd.DataFrame | None = None,
    spend_threshold_no_results: float | None = None,
    eligible_campaigns: list[str] | None = None,
) -> list[OutlierFinding]:
    """
    Ejecuta toda la detección de outliers críticos.

    Args:
        df_campaign: Dataset agregado por campaña actual
        df_daily: Dataset diario actual (para calcular umbral gasto si no se provee)
        df_benchmark: Benchmark histórico (opcional, para outliers vs histórico)
        spend_threshold_no_results: Umbral gasto para "gasto sin resultados"
        eligible_campaigns: Lista de campañas elegibles (para filtrar outliers métricos)

    Returns:
        Lista de hallazgos de outliers críticos
    """
    all_findings = []

    # 1. Calcular umbral de gasto si no se provee
    if spend_threshold_no_results is None:
        total_spend = df_campaign["spend_usd"].sum()
        unique_days = df_daily["date"].nunique() if "date" in df_daily.columns else 1
        spend_threshold_no_results = total_spend / unique_days if unique_days > 0 else 0

    # 2. Outliers: Gasto sin resultados (siempre se evalúan)
    all_findings.extend(detect_spend_no_results(df_campaign, spend_threshold_no_results))

    # 3. Outliers vs benchmark histórico (requiere histórico)
    if df_benchmark is not None and not df_benchmark.empty:
        all_findings.extend(detect_metric_outliers_zscore(
            df_campaign, df_benchmark, eligible_campaigns
        ))

    # 4. Outliers estadísticos vs cuenta actual (siempre)
    all_findings.extend(detect_statistical_outliers(df_campaign))

    return all_findings