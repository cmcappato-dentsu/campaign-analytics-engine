"""Análisis de concentración Pareto (80/20) para campañas."""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParetoResult:
    """Resultado del análisis Pareto."""
    campaign: str
    spend_usd: float
    conversions: float
    spend_rank: int
    conversion_rank: int
    spend_share: float
    cumulative_spend_share: float
    conversion_share: float
    cumulative_conversion_share: float
    in_spend_pareto: bool
    in_conversion_pareto: bool


@dataclass
class ParetoAnalysis:
    """Análisis completo de concentración Pareto."""
    campaigns: list[ParetoResult]
    spend_pareto_campaigns: list[str]
    conversion_pareto_campaigns: list[str]
    misaligned_campaigns: list[str]
    spend_concentration_pct: float
    conversion_concentration_pct: float
    total_campaigns: int
    pareto_campaigns_count: int


def build_pareto_detail(
    df_campaign: pd.DataFrame,
    spend_col: str = "spend_usd",
    conversion_col: str = "conversions",
    pareto_threshold: float = 0.80,
) -> list[ParetoResult]:
    """
    Construye detalle Pareto por campaña.

    Args:
        df_campaign: DataFrame con campañas y métricas
        spend_col: Columna de inversión
        conversion_col: Columna de conversiones
        pareto_threshold: Umbral Pareto (default 0.80 = 80%)

    Returns:
        Lista de ParetoResult con detalle por campaña
    """
    df = df_campaign.copy()

    # Validar columnas
    if spend_col not in df.columns or conversion_col not in df.columns:
        raise ValueError(f"Columnas requeridas: {spend_col}, {conversion_col}")

    total_spend = df[spend_col].sum()
    total_conversions = df[conversion_col].sum()

    # Ordenar por inversión descendente
    df_spend = df.sort_values(spend_col, ascending=False).reset_index(drop=True)
    df_spend["spend_rank"] = df_spend.index + 1
    df_spend["spend_share"] = np.where(
        total_spend > 0,
        df_spend[spend_col] / total_spend,
        0,
    )
    df_spend["cumulative_spend_share"] = df_spend["spend_share"].cumsum()
    df_spend["in_spend_pareto"] = df_spend["cumulative_spend_share"] <= pareto_threshold

    # Ordenar por conversiones descendente
    df_conv = df.sort_values(conversion_col, ascending=False).reset_index(drop=True)
    df_conv["conversion_rank"] = df_conv.index + 1
    df_conv["conversion_share"] = np.where(
        total_conversions > 0,
        df_conv[conversion_col] / total_conversions,
        0,
    )
    df_conv["cumulative_conversion_share"] = df_conv["conversion_share"].cumsum()
    df_conv["in_conversion_pareto"] = df_conv["cumulative_conversion_share"] <= pareto_threshold

    # Merge resultados
    spend_info = df_spend.set_index("campaign")[
        ["spend_rank", "spend_share", "cumulative_spend_share", "in_spend_pareto"]
    ]
    conv_info = df_conv.set_index("campaign")[
        ["conversion_rank", "conversion_share", "cumulative_conversion_share", "in_conversion_pareto"]
    ]

    results = []
    for _, row in df.iterrows():
        campaign = row["campaign"]
        s = spend_info.loc[campaign]
        c = conv_info.loc[campaign]

        results.append(ParetoResult(
            campaign=campaign,
            spend_usd=row[spend_col],
            conversions=row[conversion_col],
            spend_rank=int(s["spend_rank"]),
            conversion_rank=int(c["conversion_rank"]),
            spend_share=float(s["spend_share"]),
            cumulative_spend_share=float(s["cumulative_spend_share"]),
            conversion_share=float(c["conversion_share"]),
            cumulative_conversion_share=float(c["cumulative_conversion_share"]),
            in_spend_pareto=bool(s["in_spend_pareto"]),
            in_conversion_pareto=bool(c["in_conversion_pareto"]),
        ))

    return results


def analyze_pareto_concentration(
    df_campaign: pd.DataFrame,
    spend_col: str = "spend_usd",
    conversion_col: str = "conversions",
    pareto_threshold: float = 0.80,
) -> ParetoAnalysis:
    """
    Analiza concentración de inversión vs resultados (Regla Pareto 80/20).
    Roadmap Etapa 2, punto 4: "Si el grupo que concentra la inversión
    no coincide con el grupo que concentra los resultados, se marca como hallazgo."

    Returns:
        ParetoAnalysis con campañas Pareto, desalineación y métricas
    """
    pareto_detail = build_pareto_detail(df_campaign, spend_col, conversion_col, pareto_threshold)

    # Campañas en el 80% de inversión
    spend_pareto = [r.campaign for r in pareto_detail if r.in_spend_pareto]
    # Campañas en el 80% de conversiones
    conversion_pareto = [r.campaign for r in pareto_detail if r.in_conversion_pareto]

    # Desalineación: campañas en inversión Pareto pero NO en conversiones Pareto
    misaligned = [c for c in spend_pareto if c not in conversion_pareto]
    # También: campañas en conversiones Pareto pero NO en inversión Pareto (oportunidad)
    opportunity = [c for c in conversion_pareto if c not in spend_pareto]

    total_campaigns = len(pareto_detail)
    pareto_count = len(spend_pareto)

    # % de inversión concentrada en el 20% de campañas (aprox)
    top_20_pct = max(1, int(total_campaigns * 0.2))
    top_20_spend = sum(r.spend_usd for r in pareto_detail if r.spend_rank <= top_20_pct)
    total_spend = sum(r.spend_usd for r in pareto_detail)
    spend_concentration_pct = (top_20_spend / total_spend * 100) if total_spend > 0 else 0

    top_20_conv = sum(r.conversions for r in pareto_detail if r.conversion_rank <= top_20_pct)
    total_conv = sum(r.conversions for r in pareto_detail)
    conversion_concentration_pct = (top_20_conv / total_conv * 100) if total_conv > 0 else 0

    return ParetoAnalysis(
        campaigns=pareto_detail,
        spend_pareto_campaigns=spend_pareto,
        conversion_pareto_campaigns=conversion_pareto,
        misaligned_campaigns=misaligned,
        spend_concentration_pct=spend_concentration_pct,
        conversion_concentration_pct=conversion_concentration_pct,
        total_campaigns=total_campaigns,
        pareto_campaigns_count=pareto_count,
    )


def get_pareto_findings(pareto_analysis: ParetoAnalysis) -> list[dict]:
    """
    Genera hallazgos tipo diagnóstico a partir del análisis Pareto.
    """
    findings = []

    # Hallazgo: Desalineación gasto vs resultados
    if pareto_analysis.misaligned_campaigns:
        campaigns_str = ", ".join(pareto_analysis.misaligned_campaigns[:3])
        if len(pareto_analysis.misaligned_campaigns) > 3:
            campaigns_str += f" y {len(pareto_analysis.misaligned_campaigns) - 3} más"
        findings.append({
            "rule_id": "pareto_misaligned_spend",
            "rule_name": "Desalineación inversión vs resultados",
            "severity": "high",
            "message": (
                f"Las campañas que concentran el 80% de la inversión "
                f"({campaigns_str}) NO son las mismas que concentran el 80% "
                f"de las conversiones. Posible desperdicio de presupuesto."
            ),
            "campaigns": pareto_analysis.misaligned_campaigns,
        })

    # Hallazgo: Oportunidad - campañas con resultados pero poca inversión
    opportunity = [
        c for c in pareto_analysis.conversion_pareto_campaigns
        if c not in pareto_analysis.spend_pareto_campaigns
    ]
    if opportunity:
        campaigns_str = ", ".join(opportunity[:3])
        if len(opportunity) > 3:
            campaigns_str += f" y {len(opportunity) - 3} más"
        findings.append({
            "rule_id": "pareto_opportunity",
            "rule_name": "Oportunidad: resultados con poca inversión",
            "severity": "medium",
            "message": (
                f"Campañas que generan el 80% de conversiones pero reciben "
                f"poca inversión: {campaigns_str}. Candidatas a escalar presupuesto."
            ),
            "campaigns": opportunity,
        })

    # Hallazgo: Concentración extrema
    if pareto_analysis.spend_concentration_pct > 90:
        findings.append({
            "rule_id": "pareto_extreme_concentration",
            "rule_name": "Concentración extrema de inversión",
            "severity": "medium",
            "message": (
                f"El {pareto_analysis.spend_concentration_pct:.0f}% de la inversión "
                f"se concentra en el 20% de campañas ({pareto_analysis.pareto_campaigns_count} de "
                f"{pareto_analysis.total_campaigns}). Riesgo de dependencia de pocas campañas."
            ),
        })

    return findings


def get_pareto_summary_df(pareto_analysis: ParetoAnalysis) -> pd.DataFrame:
    """Convierte análisis Pareto a DataFrame para visualización."""
    data = []
    for r in pareto_analysis.campaigns:
        data.append({
            "Campaña": r.campaign,
            "Inversión (USD)": r.spend_usd,
            "Conversiones": r.conversions,
            "Rank Inversión": r.spend_rank,
            "Rank Conversiones": r.conversion_rank,
            "% Inversión": r.spend_share,
            "% Inversión Acum.": r.cumulative_spend_share,
            "% Conversiones": r.conversion_share,
            "% Conversiones Acum.": r.cumulative_conversion_share,
            "En Pareto Inversión": "Sí" if r.in_spend_pareto else "No",
            "En Pareto Conversiones": "Sí" if r.in_conversion_pareto else "No",
        })
    return pd.DataFrame(data)