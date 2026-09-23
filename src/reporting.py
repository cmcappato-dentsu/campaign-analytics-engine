"""Generación de reportes e insights textuales (70% visual, 30% texto)."""

import os
import pandas as pd
from typing import Optional
from dataclasses import dataclass, field

# LLM opcional
try:
    from src.llm_client import generate_llm_narrative
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    def generate_llm_narrative(*args, **kwargs):
        return None


@dataclass
class InsightSection:
    """Sección del reporte con título, contenido y orden."""
    order: int
    title: str
    content: str
    chart_suggestion: str | None = None


@dataclass
class CampaignInsight:
    """Insight generado para el reporte final."""
    question_number: int
    question: str
    answer: str
    supporting_data: dict = field(default_factory=dict)
    chart_type: str | None = None


def format_currency(value: float, currency: str = "USD") -> str:
    """Formatea moneda."""
    if pd.isna(value):
        return "—"
    return f"{currency} {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_percentage(value: float) -> str:
    """Formatea porcentaje."""
    if pd.isna(value):
        return "—"
    pct = value * 100 if abs(value) <= 1 else value
    return f"{pct:.1f}%".replace(".", ",")


def format_number(value: float, decimals: int = 0) -> str:
    """Formatea número con separador de miles."""
    if pd.isna(value):
        return "—"
    fmt = f"{{:,.{decimals}f}}".format(value)
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")


def generate_executive_summary(
    df_campaign: pd.DataFrame,
    df_daily: pd.DataFrame,
    total_spend: float,
    total_conversions: float,
    total_clicks: int,
    total_impressions: int,
) -> str:
    """Pregunta 1: ¿Cuánto se invirtió y qué resultado se obtuvo en total?"""

    ctr = total_clicks / total_impressions if total_impressions > 0 else 0
    cpa = total_spend / total_conversions if total_conversions > 0 else None
    cvr = total_conversions / total_clicks if total_clicks > 0 else 0

    lines = [
        f"**Resumen general del período**",
        f"",
        f"En el período analizado se invirtieron **{format_currency(total_spend)}** "
        f"generando **{format_number(total_impressions)} impresiones**, "
        f"**{format_number(total_clicks)} clics** (CTR: {format_percentage(ctr)}) y "
        f"**{format_number(total_conversions, 1)} conversiones** "
        f"(CPA: {format_currency(cpa) if cpa else 'N/A'}, Tasa conversión: {format_percentage(cvr)}).",
        f"",
    ]

    return "\n".join(lines)


def generate_top_campaigns_summary(
    df_campaign: pd.DataFrame,
    top_n: int = 5,
) -> str:
    """Pregunta 2: ¿Qué campañas concentran la mayor parte de la inversión y los resultados?"""

    top_spend = df_campaign.nlargest(top_n, "spend_usd")
    top_conv = df_campaign.nlargest(top_n, "conversions")

    spend_pct = top_spend["spend_usd"].sum() / df_campaign["spend_usd"].sum() * 100
    conv_pct = top_conv["conversions"].sum() / df_campaign["conversions"].sum() * 100 if df_campaign["conversions"].sum() > 0 else 0

    lines = [
        f"**Concentración de inversión y resultados (Top {top_n})**",
        f"",
        f"Las **{top_n} campañas con mayor inversión** concentran el **{spend_pct:.0f}%** del gasto total:",
        f"",
    ]

    for _, row in top_spend.iterrows():
        lines.append(f"- **{row['campaign']}**: {format_currency(row['spend_usd'])} ({row['spend_usd']/df_campaign['spend_usd'].sum()*100:.1f}% del total)")

    lines.extend([
        f"",
        f"Las **{top_n} campañas con más conversiones** concentran el **{conv_pct:.0f}%** de los resultados:",
        f"",
    ])

    for _, row in top_conv.iterrows():
        lines.append(f"- **{row['campaign']}**: {format_number(row['conversions'], 1)} conv. ({row['conversions']/df_campaign['conversions'].sum()*100:.1f}% del total)")

    return "\n".join(lines)


def generate_wasted_budget_insight(
    df_campaign: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    display_findings: list,
    spend_no_results_findings: list,
) -> str:
    """Pregunta 3: ¿Hay presupuesto que se está desperdiciando (ej. Display en Búsqueda)?"""

    lines = [
        f"**Detección de presupuesto desperdiciado**",
        f"",
    ]

    # Display en búsqueda
    if display_findings:
        lines.append(f"🔴 **Red de Display activada en campañas de Búsqueda** (error de configuración):")
        for f in display_findings:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    # Gasto sin resultados
    if spend_no_results_findings:
        lines.append(f"🔴 **Gasto sin resultados (clics/conversiones = 0)**:")
        for f in spend_no_results_findings:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    # Campañas no elegibles por bajo volumen pero con gasto
    low_volume_spend = eligibility_df[
        (eligibility_df["eligibility_status"] == "insufficient_volume") &
        (eligibility_df["is_eligible"] == False)
    ]
    if not low_volume_spend.empty:
        total_wasted = low_volume_spend.merge(
            df_campaign[["campaign", "spend_usd"]], on="campaign"
        )["spend_usd"].sum()
        lines.append(f"🟡 **Campañas con volumen insuficiente para análisis pero con gasto**: {format_currency(total_wasted)} en {len(low_volume_spend)} campañas.")
        lines.append(f"   Estas campañas no generan señal estadística confiable. Revisar si mantener activas.")

    if not display_findings and not spend_no_results_findings and low_volume_spend.empty:
        lines.append(f"✅ No se detectaron desperdicios evidentes de presupuesto en esta corrida.")

    return "\n".join(lines)


def generate_scale_opportunities(
    df_campaign: pd.DataFrame,
    pareto_findings: list,
    benchmark_findings: list,
) -> str:
    """Pregunta 4: ¿Qué campañas tienen buen resultado y podrían recibir más presupuesto?"""

    lines = [
        f"**Oportunidades de escalar inversión**",
        f"",
    ]

    # Campañas en Pareto de conversiones pero no en Pareto de inversión
    pareto_opp = [f for f in pareto_findings if f.get("rule_id") == "pareto_opportunity"]
    if pareto_opp:
        lines.append(f"🟢 **Campañas con buenos resultados pero inversión acotada** (Pareto conversiones ≠ Pareto inversión):")
        for f in pareto_opp:
            camps = f.get("campaigns", [])
            for c in camps[:3]:
                row = df_campaign[df_campaign["campaign"] == c]
                if not row.empty:
                    r = row.iloc[0]
                    lines.append(f"   - **{c}**: {format_number(r['conversions'], 1)} conv, CPA {format_currency(r.get('cpa', 0))}, inversión actual {format_currency(r['spend_usd'])}")
        lines.append(f"")

    # Campañas con buen ROAS y limitadas por presupuesto (impression share perdido por presupuesto)
    budget_limited = [f for f in benchmark_findings if "budget" in f.rule_id.lower() or "impr_share" in f.rule_id.lower()]
    if budget_limited:
        lines.append(f"🟢 **Campañas eficientes limitadas por presupuesto** (pierden impression share por presupuesto):")
        for f in budget_limited:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    if not pareto_opp and not budget_limited:
        lines.append(f"⚠️ No se identificaron oportunidades claras de escala en esta corrida.")

    return "\n".join(lines)


def generate_visibility_loss_insight(
    benchmark_findings: list,
) -> str:
    """Pregunta 5: ¿Qué campañas están perdiendo visibilidad frente a la competencia?"""

    lines = [
        f"**Pérdida de visibilidad (Impression Share)**",
        f"",
    ]

    is_drop = [f for f in benchmark_findings if "impression_share" in f.rule_id.lower() or "impr_share" in f.rule_id.lower()]

    if is_drop:
        lines.append(f"🔴 **Campañas perdiendo cuota de impresiones vs benchmark histórico**:")
        for f in is_drop:
            lines.append(f"   - {f.message}")
    else:
        lines.append(f"✅ No se detectaron caídas significativas de Impression Share vs benchmark.")

    return "\n".join(lines)


def generate_clicks_vs_conversions_insight(
    benchmark_findings: list,
) -> str:
    """Pregunta 6: ¿Qué campañas atraen clics pero no logran conversiones (o al revés)?"""

    lines = [
        f"**Análisis clics vs conversiones (CTR / Tasa conversión)**",
        f"",
    ]

    ctr_findings = [f for f in benchmark_findings if "ctr" in f.rule_id.lower()]
    cvr_findings = [f for f in benchmark_findings if "conversion_rate" in f.rule_id.lower() or "conversions_drop" in f.rule_id.lower()]

    if ctr_findings:
        lines.append(f"📊 **Variaciones de CTR vs benchmark**:")
        for f in ctr_findings:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    if cvr_findings:
        lines.append(f"📊 **Variaciones de Tasa de Conversión / Conversiones vs benchmark**:")
        for f in cvr_findings:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    if not ctr_findings and not cvr_findings:
        lines.append(f"✅ CTR y tasa de conversión dentro de rangos esperados vs benchmark histórico.")

    return "\n".join(lines)


def generate_high_cpa_insight(
    df_campaign: pd.DataFrame,
    benchmark_findings: list,
    outlier_findings: list,
) -> str:
    """Pregunta 7: ¿Qué campañas tienen un costo por resultado demasiado alto?"""

    lines = [
        f"**Campañas con CPA/ROAS elevado**",
        f"",
    ]

    cpa_findings = [f for f in benchmark_findings if "cpa" in f.rule_id.lower()]
    cpa_outliers = [f for f in outlier_findings if "cpa" in f.outlier_type.lower()]

    if cpa_findings:
        lines.append(f"🔴 **CPA significativamente por encima del benchmark histórico**:")
        for f in cpa_findings:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    if cpa_outliers:
        lines.append(f"🔴 **Outliers críticos de CPA** (variación >2x umbral normal):")
        for f in cpa_outliers:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    # Top CPA actual
    if "cpa" in df_campaign.columns:
        top_cpa = df_campaign[df_campaign["cpa"].notna()].nlargest(3, "cpa")
        if not top_cpa.empty:
            lines.append(f"📊 **Top 3 CPA actual en la cuenta**:")
            for _, row in top_cpa.iterrows():
                lines.append(f"   - **{row['campaign']}**: CPA {format_currency(row['cpa'])}, {format_number(row['conversions'], 1)} conv.")
        lines.append(f"")

    if not cpa_findings and not cpa_outliers:
        lines.append(f"✅ No se detectaron CPAs anómalamente altos vs benchmark.")

    return "\n".join(lines)


def generate_insufficient_data_insight(
    eligibility_df: pd.DataFrame,
) -> str:
    """Pregunta 8: ¿Qué campañas tienen tan pocos datos que conviene esperar?"""

    lines = [
        f"**Campañas con datos insuficientes**",
        f"",
    ]

    insufficient_hist = eligibility_df[eligibility_df["eligibility_status"] == "insufficient_history"]
    insufficient_vol = eligibility_df[eligibility_df["eligibility_status"] == "insufficient_volume"]

    if not insufficient_hist.empty:
        lines.append(f"🟡 **Campañas nuevas (< 7 días activa) - esperar historial**:")
        for _, row in insufficient_hist.iterrows():
            lines.append(f"   - **{row['campaign']}**: {row['active_days']} días activa (mínimo 7)")
        lines.append(f"")

    if not insufficient_vol.empty:
        lines.append(f"🟡 **Campañas con volumen insuficiente para análisis confiable**:")
        for _, row in insufficient_vol.iterrows():
            lines.append(f"   - **{row['campaign']}**: {row['eligibility_reason']}")
        lines.append(f"")

    if insufficient_hist.empty and insufficient_vol.empty:
        lines.append(f"✅ Todas las campañas tienen historial y volumen suficiente para análisis.")

    return "\n".join(lines)


def generate_top_findings_summary(
    scored_findings: list,
) -> str:
    """Pregunta 9: ¿Cuáles son los 2 a 5 hallazgos más relevantes de la semana?"""

    lines = [
        f"**🎯 Top {len(scored_findings)} hallazgos más relevantes de la semana**",
        f"",
    ]

    for i, f in enumerate(scored_findings, 1):
        severity_icon = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }.get(f.severity.value, "⚪")

        outlier_mark = " ⚡ OUTLIER" if f.is_outlier else ""
        lines.append(f"**{i}. {severity_icon} {f.rule_name}** ({f.campaign}){outlier_mark}")
        lines.append(f"   {f.message}")
        lines.append(f"")

    return "\n".join(lines)


def build_full_report(
    df_campaign: pd.DataFrame,
    df_daily: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    diagnostics_findings: list,
    outlier_findings: list,
    pareto_analysis,
    scored_findings: list,
    currency_info: dict,
) -> list[CampaignInsight]:
    """
    Construye el reporte completo respondiendo las 9 preguntas del roadmap.
    Retorna lista de CampaignInsight (uno por pregunta).
    """

    # Métricas agregadas
    total_spend = df_daily["spend_usd"].sum()
    total_clicks = int(df_daily["clicks"].sum())
    total_impressions = int(df_daily["impressions"].sum())
    total_conversions = df_daily["conversions"].sum()

    # Filtrar hallazgos por tipo
    display_findings = [f for f in diagnostics_findings if "display" in f.rule_id.lower()]
    benchmark_findings = [f for f in diagnostics_findings if "benchmark" in f.rule_id.lower() or "impression_share" in f.rule_id.lower()]
    spend_no_results = [f for f in outlier_findings if "spend_no" in f.outlier_type.lower()]
    cpa_outliers = [f for f in outlier_findings if "cpa" in f.outlier_type.lower()]

    # Pareto findings
    from src.pareto import get_pareto_findings
    pareto_findings = get_pareto_findings(pareto_analysis)

    insights = []

    # Pregunta 1
    insights.append(CampaignInsight(
        question_number=1,
        question="¿Cuánto se invirtió y qué resultado se obtuvo en total?",
        answer=generate_executive_summary(df_campaign, df_daily, total_spend, total_conversions, total_clicks, total_impressions),
        supporting_data={
            "total_spend": total_spend,
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "total_conversions": total_conversions,
        },
        chart_type="kpi_cards",
    ))

    # Pregunta 2
    insights.append(CampaignInsight(
        question_number=2,
        question="¿Qué campañas concentran la mayor parte de la inversión y los resultados?",
        answer=generate_top_campaigns_summary(df_campaign),
        supporting_data={"pareto_analysis": pareto_analysis},
        chart_type="pareto_chart",
    ))

    # Pregunta 3
    insights.append(CampaignInsight(
        question_number=3,
        question="¿Hay presupuesto que se está desperdiciando (ej. Display en Búsqueda)?",
        answer=generate_wasted_budget_insight(df_campaign, eligibility_df, display_findings, spend_no_results),
        supporting_data={
            "display_findings": display_findings,
            "spend_no_results": spend_no_results,
        },
        chart_type="network_breakdown",
    ))

    # Pregunta 4
    insights.append(CampaignInsight(
        question_number=4,
        question="¿Qué campañas tienen buen resultado y podrían recibir más presupuesto?",
        answer=generate_scale_opportunities(df_campaign, pareto_findings, benchmark_findings),
        supporting_data={"pareto_opportunities": pareto_findings},
        chart_type="scatter_cpa_conversions",
    ))

    # Pregunta 5
    insights.append(CampaignInsight(
        question_number=5,
        question="¿Qué campañas están perdiendo visibilidad frente a la competencia?",
        answer=generate_visibility_loss_insight(benchmark_findings),
        supporting_data={"impression_share_findings": [f for f in benchmark_findings if "impr" in f.rule_id.lower()]},
        chart_type="impression_share_trend",
    ))

    # Pregunta 6
    insights.append(CampaignInsight(
        question_number=6,
        question="¿Qué campañas atraen clics pero no logran conversiones (o al revés)?",
        answer=generate_clicks_vs_conversions_insight(benchmark_findings),
        supporting_data={"ctr_findings": [f for f in benchmark_findings if "ctr" in f.rule_id.lower()]},
        chart_type="ctr_vs_cvr_matrix",
    ))

    # Pregunta 7
    insights.append(CampaignInsight(
        question_number=7,
        question="¿Qué campañas tienen un costo por resultado demasiado alto?",
        answer=generate_high_cpa_insight(df_campaign, benchmark_findings, cpa_outliers),
        supporting_data={"cpa_findings": cpa_outliers},
        chart_type="cpa_ranking",
    ))

    # Pregunta 8
    insights.append(CampaignInsight(
        question_number=8,
        question="¿Qué campañas tienen tan pocos datos que conviene esperar antes de sacar conclusiones?",
        answer=generate_insufficient_data_insight(eligibility_df),
        supporting_data={"eligibility_summary": eligibility_df["eligibility_status"].value_counts().to_dict()},
        chart_type=None,
    ))

    # Pregunta 9
    insights.append(CampaignInsight(
        question_number=9,
        question="¿Cuáles son los 2 a 5 hallazgos más relevantes de la semana?",
        answer=generate_top_findings_summary(scored_findings),
        supporting_data={"scored_findings": scored_findings},
        chart_type=None,
    ))

    return insights


def format_report_markdown(insights: list[CampaignInsight]) -> str:
    """Formatea todos los insights como Markdown para mostrar en UI."""

    lines = [
        "# 📊 Reporte de Análisis de Campañas - Miau",
        f"",
        f"*Generado automáticamente - Análisis general (Search)*",
        f"",
        f"---",
        f"",
    ]

    for insight in insights:
        lines.append(f"## {insight.question_number}. {insight.question}")
        lines.append(f"")
        lines.append(insight.answer)
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

    return "\n".join(lines)


def build_enhanced_report(
    df_campaign: pd.DataFrame,
    df_daily: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    diagnostics_findings: list,
    outlier_findings: list,
    pareto_analysis,
    scored_findings: list,
    currency_info: dict,
    use_llm: bool = True,
) -> tuple[list[CampaignInsight], Optional[str]]:
    """
    Construye reporte completo + narrativa ejecutiva opcional con LLM.
    Retorna (insights, llm_narrative_or_none).
    """
    # 1. Reporte base (9 preguntas)
    insights = build_full_report(
        df_campaign, df_daily, eligibility_df,
        diagnostics_findings, outlier_findings,
        pareto_analysis, scored_findings, currency_info
    )

    # 2. Narrativa LLM (opcional, solo si está disponible y habilitado)
    llm_narrative = None
    if use_llm and LLM_AVAILABLE:
        llm_narrative = generate_llm_narrative(scored_findings, df_campaign)
        if llm_narrative:
            # Insertar como insight 0 (resumen ejecutivo narrativo)
            insights.insert(0, CampaignInsight(
                question_number=0,
                question="📋 Resumen Ejecutivo (IA)",
                answer=llm_narrative,
                supporting_data={"generated_by": "llm"},
                chart_type=None,
            ))

    return insights, llm_narrative