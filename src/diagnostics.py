"""Reglas de diagnóstico para campañas de Google Ads."""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional

from config.thresholds import (
    CTR_VARIATION_THRESHOLD,
    CPC_VARIATION_THRESHOLD,
    CPA_VARIATION_THRESHOLD,
)


@dataclass
class DiagnosticFinding:
    """Hallazgo diagnóstico individual."""
    campaign: str
    rule_id: str
    rule_name: str
    severity: str  # "high", "medium", "low", "critical"
    message: str
    metric_value: float | None = None
    benchmark_value: float | None = None
    variation_pct: float | None = None
    persistence_count: int = 1


class DiagnosticRules:
    """IDs de reglas de diagnóstico."""

    # Reglas de configuración (siempre se evalúan)
    DISPLAY_IN_SEARCH = "config_display_in_search"

    # Reglas de benchmark histórico (requieren histórico)
    CTR_HIGH = "benchmark_ctr_high"
    CTR_LOW = "benchmark_ctr_low"
    CPC_HIGH = "benchmark_cpc_high"
    CPA_HIGH = "benchmark_cpa_high"
    IMPRESSION_SHARE_DROP = "benchmark_impr_share_drop"
    CONVERSIONS_DROP = "benchmark_conversions_drop"
    CONVERSION_RATE_DROP = "benchmark_conv_rate_drop"

    # Persistencia
    PERSISTENCE_MIN_PERIODS = 2


def check_display_in_search(df_campaign: pd.DataFrame) -> list[DiagnosticFinding]:
    """
    Regla de configuración: Red de Display activada en campaña de tipo Búsqueda.
    Roadmap Etapa 2, punto 2 - Flag inmediato de alta prioridad.
    """
    findings = []

    if "network" not in df_campaign.columns:
        return findings

    for _, row in df_campaign.iterrows():
        network = str(row.get("network", "")).lower()
        campaign = row["campaign"]

        if "display" in network or "content" in network:
            findings.append(DiagnosticFinding(
                campaign=campaign,
                rule_id=DiagnosticRules.DISPLAY_IN_SEARCH,
                rule_name="Red de Display en campaña de Búsqueda",
                severity="critical",
                message=(
                    f"La campaña '{campaign}' tiene Red de Display activada "
                    f"('{row['network']}'). En campañas de Búsqueda esto suele ser "
                    f"un error de configuración que desperdicia presupuesto."
                ),
                metric_value=1.0,
            ))

    return findings


def calculate_benchmark(
    df_history: pd.DataFrame, window: int = 4, quartile_segment: str | None = None
) -> pd.DataFrame:
    """
    Calcula promedio móvil por campaña y métrica para benchmark histórico.

    Args:
        df_history: DataFrame con columnas [campaign, date, ctr, cpc, cpa,
                    impression_share, conversions, conversion_rate, spend_usd]
        window: Ventana de semanas para promedio móvil (default 4)
        quartile_segment: Segmento de cuartil (Q1, Q2, Q3, Q4) por volumen.
            Si es None, calcula benchmark global (todos las campañas juntos).

    Returns:
        DataFrame con benchmark por campaña: campaign, metric, benchmark_value
    """
    if df_history.empty or "campaign" not in df_history.columns:
        return pd.DataFrame(columns=["campaign", "metric", "benchmark_value"])

    df = df_history.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["campaign", "date"])

    metric_cols = ["ctr", "cpc", "cpa", "impression_share", "conversions", "conversion_rate"]
    available_metrics = [c for c in metric_cols if c in df.columns]

    if not available_metrics:
        return pd.DataFrame(columns=["campaign", "metric", "benchmark_value"])

    # Si se especifica segmento de cuartil, filtrar por ese segmento
    if quartile_segment is not None:
        df = df[df["quartile"] == quartile_segment].copy()

    results = []
    for campaign, group in df.groupby("campaign"):
        for metric in available_metrics:
            values = group[metric].dropna()
            if len(values) >= 1:
                # Usar últimos N períodos disponibles (hasta window)
                recent = values.tail(window)
                benchmark = recent.mean()
                results.append({
                    "campaign": campaign,
                    "metric": metric,
                    "benchmark_value": benchmark,
                    "periods_used": len(recent),
                    "quartile_segment": quartile_segment,
                })

    return pd.DataFrame(results)


def check_benchmark_variations(
    df_campaign: pd.DataFrame,
    df_benchmark: pd.DataFrame,
    persistence_df: pd.DataFrame | None = None,
    quartile_segments: dict | None = None,
) -> list[DiagnosticFinding]:
    """
    Reglas de benchmark histórico (Roadmap Etapa 2, punto 3).
    Compara métricas actuales vs promedio móvil propio (4 semanas).

    Umbrales:
    - CTR: variación ±25% → "CTR alto" / "CTR bajo"
    - CPC: variación +25% → "CPC alto"
    - CPA: variación +30% o muy encima del promedio cuenta → "costo por resultado alto"
    - Impression Share: caída >10pp → "perdiendo visibilidad"
    - Conversions/CVR: caída >30% con clics estables/subiendo → "problema landing/oferta"

    Persistencia: debe sustentarce ≥2 cortes consecutivos (salvo outliers).
    quartile_segments: Diccionario opcional mapping campaign -> cuartil (Q1-Q4) para benchmarks segmentados.
    """
    findings = []

    if df_benchmark.empty:
        return findings

    # Create benchmark map: campaign -> metric -> benchmark_value
    benchmark_map = df_benchmark.set_index(["campaign", "metric"])["benchmark_value"].to_dict()

    # Create quartile-aware benchmark map if quartile_segments provided
    if quartile_segments is not None:
        # Build a map: campaign -> (metric -> benchmark_value for its quartile)
        quartile_benchmark_map = {}
        for campaign, quartile in quartile_segments.items():
            # Find benchmarks for this campaign in its quartile
            camp_benchmarks = df_benchmark[
                (df_benchmark["campaign"] == campaign) & 
                (df_benchmark["quartile_segment"] == quartile)
            ]
            if not camp_benchmarks.empty:
                camp_map = camp_benchmarks.set_index(["campaign", "metric"])["benchmark_value"].to_dict()
                quartile_benchmark_map[campaign] = camp_map
        # We'll use quartile-specific benchmarks when available below
    else:
        quartile_benchmark_map = None

    for _, row in df_campaign.iterrows():
        campaign = row["campaign"]

        # CTR
        if "ctr" in row and pd.notna(row["ctr"]) and row["ctr"] > 0:
            # Try quartile-specific benchmark first, then global
            bench = None
            if quartile_benchmark_map and campaign in quartile_benchmark_map:
                bench = quartile_benchmark_map[campaign].get("ctr")
            if bench is None:
                bench = benchmark_map.get((campaign, "ctr"))
            if bench and bench > 0:
                var = (row["ctr"] - bench) / bench
                _check_persistence_and_add(
                    findings, campaign, row["ctr"], bench, var,
                    DiagnosticRules.CTR_HIGH, "CTR sobre el benchmark",
                    DiagnosticRules.CTR_LOW, "CTR por debajo del benchmark",
                    CTR_VARIATION_THRESHOLD, persistence_df, "ctr"
                )

        # CPC
        if "cpc" in row and pd.notna(row["cpc"]) and row["cpc"] > 0:
            # Try quartile-specific benchmark first, then global
            bench = None
            if quartile_benchmark_map and campaign in quartile_benchmark_map:
                bench = quartile_benchmark_map[campaign].get("cpc")
            if bench is None:
                bench = benchmark_map.get((campaign, "cpc"))
            if bench and bench > 0:
                var = (row["cpc"] - bench) / bench
                if var > CPC_VARIATION_THRESHOLD:
                    _add_finding_if_persistent(
                        findings, campaign, row["cpc"], bench, var,
                        DiagnosticRules.CPC_HIGH, "CPC sobre el benchmark",
                        "El CPC subió {:.0%} sobre el benchmark ({:.2f} → {:.2f}). "
                        "Puede indicar mayor competencia o pérdida de calidad.",
                        persistence_df, "cpc"
                    )

        # CPA
        if "cpa" in row and pd.notna(row["cpa"]) and row["cpa"] > 0:
            # Try quartile-specific benchmark first, then global
            bench = None
            if quartile_benchmark_map and campaign in quartile_benchmark_map:
                bench = quartile_benchmark_map[campaign].get("cpa")
            if bench is None:
                bench = benchmark_map.get((campaign, "cpa"))
            if bench and bench > 0:
                var = (row["cpa"] - bench) / bench
                if var > CPA_VARIATION_THRESHOLD:
                    _add_finding_if_persistent(
                        findings, campaign, row["cpa"], bench, var,
                        DiagnosticRules.CPA_HIGH, "CPA sobre el benchmark",
                        "El CPA subió {:.0%} sobre el benchmark ({:.2f} → {:.2f}). "
                        "Costo por conversión significativamente mayor al habitual.",
                        persistence_df, "cpa"
                    )

        # Impression Share
        if "impression_share" in row and pd.notna(row["impression_share"]):
            # Try quartile-specific benchmark first, then global
            bench = None
            if quartile_benchmark_map and campaign in quartile_benchmark_map:
                bench = quartile_benchmark_map[campaign].get("impression_share")
            if bench is None:
                bench = benchmark_map.get((campaign, "impression_share"))
            if bench and bench > 0:
                drop = bench - row["impression_share"]
                if drop > 0.10:  # 10 puntos porcentuales
                    _add_finding_if_persistent(
                        findings, campaign, row["impression_share"], bench, -drop/bench,
                        DiagnosticRules.IMPRESSION_SHARE_DROP, "Pérdida de impression share",
                        "La cuota de impresiones cayó {:.1f}pp vs benchmark ({:.1%} → {:.1%}). "
                        "Perdiendo visibilidad frente a la competencia.",
                        persistence_df, "impression_share"
                    )

        # Top Impression Share
        if "top_impression_share" in row and pd.notna(row["top_impression_share"]):
            if row["top_impression_share"] < 0.30:  # Menor a 30% = baja prominencia
                _add_finding_if_persistent(
                    findings, campaign, row["top_impression_share"], None, -row["top_impression_share"],
                    DiagnosticRules.IMPRESSION_SHARE_DROP, "Baja Top Impression Share",
                    "Top Impression Share bajo ({:.0%}). Las anuncios no aparecen en la posición principal.",
                    persistence_df, "top_impression_share"
                )

        # Lost IS Budget
        if "lost_is_budget" in row and pd.notna(row["lost_is_budget"]):
            if row["lost_is_budget"] > 0.20:  # Mayor a 20% = presupuesto insuficiente
                _add_finding_if_persistent(
                    findings, campaign, row["lost_is_budget"], None, row["lost_is_budget"],
                    DiagnosticRules.IMPRESSION_SHARE_DROP, "Lost IS Budget alto",
                    "Lost IS Budget {:.0%}. Presupuesto insuficiente para capturar todas las impresiones.",
                    persistence_df, "lost_is_budget"
                )

        # Conversions drop
        if "conversions" in row and pd.notna(row["conversions"]):
            # Try quartile-specific benchmark first, then global
            bench = None
            if quartile_benchmark_map and campaign in quartile_benchmark_map:
                bench = quartile_benchmark_map[campaign].get("conversions")
            if bench is None:
                bench = benchmark_map.get((campaign, "conversions"))
            if bench and bench > 0:
                var = (row["conversions"] - bench) / bench
                if var < -0.30:  # caída >30%
                    clicks_stable = True
                    if "clicks" in row and "clicks" in df_benchmark.columns:
                        click_bench = benchmark_map.get((campaign, "clicks"))
                        if click_bench and click_bench > 0:
                            click_var = (row["clicks"] - click_bench) / click_bench
                            clicks_stable = click_var >= -0.10  # clics no cayeron >10%
                    if clicks_stable:
                        _add_finding_if_persistent(
                            findings, campaign, row["conversions"], bench, var,
                            DiagnosticRules.CONVERSIONS_DROP, "Caída de conversiones",
                            "Las conversiones cayeron {:.0%} vs benchmark ({:.0f} → {:.0f}) "
                            "con clics estables. Posible problema en landing page u oferta.",
                            persistence_df, "conversions"
                        )

        # Conversion rate drop
        if "conversion_rate" in row and pd.notna(row["conversion_rate"]) and row["conversion_rate"] > 0:
            # Try quartile-specific benchmark first, then global
            bench = None
            if quartile_benchmark_map and campaign in quartile_benchmark_map:
                bench = quartile_benchmark_map[campaign].get("conversion_rate")
            if bench is None:
                bench = benchmark_map.get((campaign, "conversion_rate"))
            if bench and bench > 0:
                var = (row["conversion_rate"] - bench) / bench
                if var < -0.30:  # caída >30%
                    _add_finding_if_persistent(
                        findings, campaign, row["conversion_rate"], bench, var,
                        DiagnosticRules.CONVERSION_RATE_DROP, "Caída de tasa de conversión",
                        "La tasa de conversión cayó {:.0%} vs benchmark ({:.2%} → {:.2%}). "
                        "Posible problema de calidad del tráfico o en la conversión.",
                        persistence_df, "conversion_rate"
                    )

    return findings


def _check_persistence_and_add(
    findings: list,
    campaign: str,
    current: float,
    benchmark: float,
    variation: float,
    rule_id_high: str,
    name_high: str,
    rule_id_low: str,
    name_low: str,
    threshold: float,
    persistence_df: pd.DataFrame | None,
    metric: str,
):
    """Helper para métricas con umbral bilateral (CTR sobre/por debajo del benchmark)."""
    if variation > threshold:
        _add_finding_if_persistent(
            findings, campaign, current, benchmark, variation,
            rule_id_high, name_high,
            f"El CTR subió {variation:.0%} en {campaign} ({benchmark:.2f} → {current:.2f}). "
            f"Mayor interacción de lo habitual.",
            persistence_df, metric
        )
    elif variation < -threshold:
        _add_finding_if_persistent(
            findings, campaign, current, benchmark, variation,
            rule_id_low, name_low,
            f"El CTR bajó {abs(variation):.0%} en {campaign} ({benchmark:.2f} → {current:.2f}). "
            f"Menor interacción de lo habitual.",
            persistence_df, metric
        )


def _add_finding_if_persistent(
    findings: list,
    campaign: str,
    current: float,
    benchmark: float,
    variation: float,
    rule_id: str,
    name: str,
    message_template: str,
    persistence_df: pd.DataFrame | None,
    metric: str,
):
    """Añade hallazgo solo si cumple persistencia (≥2 períodos) o es outlier crítico."""
    persistence_count = 1

    if persistence_df is not None and not persistence_df.empty:
        # Verificar cuántos períodos consecutivos cumple la condición
        camp_persist = persistence_df[
            (persistence_df["campaign"] == campaign) &
            (persistence_df["metric"] == metric) &
            (persistence_df["condition_met"] == True)
        ]
        if not camp_persist.empty:
            persistence_count = len(camp_persist)

    # Reglas de persistencia: ≥2 períodos consecutivos
    # EXCEPCIÓN: si variación > 2x umbral, es outlier crítico y no requiere persistencia
    is_outlier = abs(variation) > (2 * _get_threshold_for_metric(metric))

    if persistence_count >= DiagnosticRules.PERSISTENCE_MIN_PERIODS or is_outlier:
        severity = "critical" if is_outlier else "high"
        findings.append(DiagnosticFinding(
            campaign=campaign,
            rule_id=rule_id,
            rule_name=name,
            severity=severity,
            message=message_template.format(variation, benchmark, current),
            metric_value=current,
            benchmark_value=benchmark,
            variation_pct=variation,
            persistence_count=persistence_count,
        ))


def _get_threshold_for_metric(metric: str) -> float:
    """Retorna umbral base para cada métrica."""
    thresholds = {
        "ctr": CTR_VARIATION_THRESHOLD,
        "cpc": CPC_VARIATION_THRESHOLD,
        "cpa": CPA_VARIATION_THRESHOLD,
        "impression_share": 0.10,
        "conversions": 0.30,
        "conversion_rate": 0.30,
        "lost_is_budget": 0.10,
        "top_impression_share": 0.15,
    }
    return thresholds.get(metric, 0.25)


def build_persistence_tracker(
    df_history: pd.DataFrame,
    df_benchmark: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye tracker de persistencia para cada campaña/métrica/período.
    Marca si se cumple la condición de variación en cada corte histórico.
    """
    if df_history.empty or df_benchmark.empty:
        return pd.DataFrame(columns=["campaign", "date", "metric", "condition_met"])

    df = df_history.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["campaign", "date"])

    benchmark_map = df_benchmark.set_index(["campaign", "metric"])["benchmark_value"].to_dict()

    records = []
    for _, row in df.iterrows():
        campaign = row["campaign"]
        for metric in ["ctr", "cpc", "cpa", "impression_share", "conversions", "conversion_rate", "lost_is_budget", "top_impression_share"]:
            if metric not in row or pd.isna(row[metric]):
                continue
            bench = benchmark_map.get((campaign, metric))
            if not bench or bench == 0:
                continue

            current = row[metric]
            var = (current - bench) / bench
            threshold = _get_threshold_for_metric(metric)

            if metric == "ctr":
                condition = abs(var) > threshold
            elif metric in ["cpc", "cpa", "conversions", "conversion_rate"]:
                condition = var > threshold if metric in ["cpc", "cpa"] else var < -threshold
            elif metric == "impression_share":
                condition = (bench - current) > 0.10
            else:
                condition = False

            records.append({
                "campaign": campaign,
                "date": row["date"],
                "metric": metric,
                "condition_met": condition,
                "variation": var,
            })

    return pd.DataFrame(records)





def _assign_quartile(df: pd.DataFrame, column: str) -> pd.Series:
    """
    Asigna cuartiles a cada fila basándose en el valor de una columna.
    Returns series with values Q1, Q2, Q3, Q4.
    Q1 = top 25% (mayor volumen), Q4 = bottom 25% (menor volumen).
    """
    quartiles = pd.qcut(df[column], q=4, labels=["Q4", "Q3", "Q2", "Q1"])
    return quartiles


def run_diagnostics(
    df_campaign: pd.DataFrame,
    df_daily: pd.DataFrame,
    df_history: pd.DataFrame | None = None,
    df_benchmark: pd.DataFrame | None = None,
    persistence_df: pd.DataFrame | None = None,
) -> list[DiagnosticFinding]:
    """
    Ejecuta todas las reglas de diagnóstico.

    Args:
        df_campaign: Dataset agregado por campaña actual
        df_daily: Dataset diario actual
        df_history: Histórico diario (opcional, para benchmark)
        df_benchmark: Benchmark precalculado (opcional)
        persistence_df: Tracker de persistencia precalculado (opcional)

    Returns:
        Lista de hallazgos diagnósticos
    """
    all_findings = []

    # 1. Reglas de configuración (siempre)
    all_findings.extend(check_display_in_search(df_campaign))

    # 2. Reglas de benchmark (requieren histórico)
    if df_history is not None and not df_history.empty:
        if df_benchmark is None:
            df_benchmark = calculate_benchmark(df_history)
        if persistence_df is None:
            persistence_df = build_persistence_tracker(df_history, df_benchmark)
        all_findings.extend(check_benchmark_variations(df_campaign, df_benchmark, persistence_df))

    return all_findings