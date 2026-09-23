"""Scoring y priorización de hallazgos para el reporte final."""

import pandas as pd
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class FindingSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_WEIGHTS = {
    FindingSeverity.CRITICAL: 100,
    FindingSeverity.HIGH: 50,
    FindingSeverity.MEDIUM: 20,
    FindingSeverity.LOW: 10,
}


@dataclass
class ScoredFinding:
    """Hallazgo con score calculado."""
    rule_id: str
    rule_name: str
    campaign: str
    severity: FindingSeverity
    message: str
    impact_score: float
    magnitude_score: float
    multi_metric_bonus: float
    total_score: float
    metric_values: dict
    persistence_count: int = 1
    is_outlier: bool = False


def calculate_impact_score(
    campaign: str,
    df_campaign: pd.DataFrame,
    metric: str = "spend_usd",
) -> float:
    """
    Calcula score de impacto relativo de la campaña.
    Roadmap: "impacto relativo de la campaña (peso sobre inversión o resultados totales de la cuenta)"
    """
    if df_campaign.empty or campaign not in df_campaign["campaign"].values:
        return 0.0

    row = df_campaign[df_campaign["campaign"] == campaign].iloc[0]
    total = df_campaign[metric].sum()

    if total == 0:
        return 0.0

    return row[metric] / total


def calculate_magnitude_score(
    variation_pct: float | None,
    benchmark_value: float | None,
    current_value: float | None,
    metric: str,
) -> float:
    """
    Calcula score de magnitud de la variación.
    Roadmap: "magnitud de la variación"
    """
    if variation_pct is None or variation_pct == 0:
        return 0.0

    # Normalizar: variación absoluta como porcentaje
    return min(abs(variation_pct) * 100, 100)  # Cap at 100


def calculate_multi_metric_bonus(
    campaign: str,
    all_findings: list,
    current_rule_id: str,
) -> float:
    """
    Bonus si 2+ métricas de la misma campaña están afectadas.
    Roadmap: "plus si 2 o más métricas de la misma campaña están afectadas a la vez"
    """
    def _get_id(f):
        return getattr(f, 'rule_id', None) or getattr(f, 'outlier_type', None) or ''

    campaign_findings = [
        f for f in all_findings
        if (getattr(f, 'campaign', '') == campaign) and (_get_id(f) != current_rule_id)
    ]
    unique_metrics = set()

    for f in campaign_findings:
        rid = _get_id(f)
        # Extraer métrica del rule_id
        if "ctr" in rid:
            unique_metrics.add("ctr")
        elif "cpc" in rid:
            unique_metrics.add("cpc")
        elif "cpa" in rid:
            unique_metrics.add("cpa")
        elif "impr" in rid or "impression" in rid:
            unique_metrics.add("impression_share")
        elif "conversion" in rid and "rate" not in rid:
            unique_metrics.add("conversions")
        elif "conv_rate" in rid:
            unique_metrics.add("conversion_rate")
        elif "display" in rid:
            unique_metrics.add("config")
        elif "spend_no" in rid:
            unique_metrics.add("spend_no_results")
        elif "pareto" in rid:
            unique_metrics.add("pareto")

    # Bonus: 10 puntos por cada métrica adicional afectada (máx 30)
    bonus = max(0, (len(unique_metrics) - 1)) * 10
    return min(bonus, 30)


def score_finding(
    finding,
    df_campaign: pd.DataFrame,
    all_findings: list,
    impact_metric: str = "spend_usd",
) -> ScoredFinding:
    """
    Calcula score total para un hallazgo.
    Roadmap: Score = impacto relativo × magnitud variación + bonus multi-métrica
    """
    def _get(obj, attr, default=None):
        if hasattr(obj, attr):
            return getattr(obj, attr)
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return default

    # Determinar severidad
    severity_str = _get(finding, 'severity', 'medium')
    try:
        severity = FindingSeverity(severity_str)
    except ValueError:
        severity = FindingSeverity.MEDIUM

    # Obtener campos básicos
    campaign = _get(finding, 'campaign', '')
    rule_id = _get(finding, 'rule_id', '')
    rule_name = _get(finding, 'rule_name', '')
    message = _get(finding, 'message', '')

    # Obtener variación y valores
    variation_pct = _get(finding, 'variation_pct')
    benchmark_value = _get(finding, 'benchmark_value')
    current_value = _get(finding, 'metric_value')
    persistence_count = _get(finding, 'persistence_count', 1)

    # Identificar métrica principal del hallazgo
    metric = _extract_metric_from_rule(rule_id)

    # Calcular componentes
    impact = calculate_impact_score(campaign, df_campaign, impact_metric)
    magnitude = calculate_magnitude_score(variation_pct, benchmark_value, current_value, metric)
    multi_metric = calculate_multi_metric_bonus(campaign, all_findings, rule_id)

    # Score base: impacto * magnitud (normalizado)
    base_score = impact * magnitude

    # Bonus por persistencia
    persistence_bonus = min(persistence_count - 1, 3) * 5  # +5 por cada período extra (máx 15)

    # Score por severidad
    severity_score = SEVERITY_WEIGHTS[severity]

    # Total score
    total_score = base_score + severity_score + multi_metric + persistence_bonus

    # Outliers críticos siempre tienen score alto
    is_outlier = _get(finding, 'is_outlier', False) or _get(finding, 'outlier_type', None) is not None
    if is_outlier:
        total_score += 200  # Boost para outliers críticos

    return ScoredFinding(
        rule_id=rule_id,
        rule_name=rule_name,
        campaign=campaign,
        severity=severity,
        message=message,
        impact_score=impact,
        magnitude_score=magnitude,
        multi_metric_bonus=multi_metric,
        total_score=total_score,
        metric_values={
            "variation_pct": variation_pct,
            "benchmark_value": benchmark_value,
            "current_value": current_value,
        },
        persistence_count=persistence_count,
        is_outlier=is_outlier,
    )


def _extract_metric_from_rule(rule_id: str) -> str:
    """Extrae nombre de métrica del rule_id."""
    if "ctr" in rule_id:
        return "ctr"
    elif "cpc" in rule_id:
        return "cpc"
    elif "cpa" in rule_id:
        return "cpa"
    elif "impr" in rule_id or "impression" in rule_id:
        return "impression_share"
    elif "conversion" in rule_id and "rate" not in rule_id:
        return "conversions"
    elif "conv_rate" in rule_id:
        return "conversion_rate"
    elif "display" in rule_id:
        return "config"
    elif "spend_no" in rule_id:
        return "spend_no_results"
    elif "pareto" in rule_id:
        return "pareto"
    return "unknown"


def prioritize_findings(
    findings: list,
    df_campaign: pd.DataFrame,
    max_findings: int = 5,
    impact_metric: str = "spend_usd",
) -> list[ScoredFinding]:
    """
    Prioriza hallazgos y retorna top N.
    Roadmap: "Techo por corrida: reportar como máximo 5 hallazgos (top 5 por score).
    Los outliers críticos siempre entran al top, independientemente del score."
    """
    if not findings:
        return []

    # Scored all findings
    scored = [score_finding(f, df_campaign, findings, impact_metric) for f in findings]

    # Separar outliers críticos
    outliers = [s for s in scored if s.is_outlier]
    regular = [s for s in scored if not s.is_outlier]

    # Ordenar por score descendente
    outliers.sort(key=lambda x: x.total_score, reverse=True)
    regular.sort(key=lambda x: x.total_score, reverse=True)

    # Los outliers siempre entran primero
    result = outliers[:max_findings]

    # Completar con regulares hasta max_findings
    remaining_slots = max_findings - len(result)
    if remaining_slots > 0:
        result.extend(regular[:remaining_slots])

    return result


def get_finding_summary(scored_findings: list[ScoredFinding]) -> dict:
    """Genera resumen de hallazgos priorizados."""
    return {
        "total_findings": len(scored_findings),
        "critical_count": sum(1 for f in scored_findings if f.severity == FindingSeverity.CRITICAL),
        "high_count": sum(1 for f in scored_findings if f.severity == FindingSeverity.HIGH),
        "medium_count": sum(1 for f in scored_findings if f.severity == FindingSeverity.MEDIUM),
        "low_count": sum(1 for f in scored_findings if f.severity == FindingSeverity.LOW),
        "outlier_count": sum(1 for f in scored_findings if f.is_outlier),
        "top_campaigns": list(set(f.campaign for f in scored_findings)),
    }