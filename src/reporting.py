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
    title: str = ""
    status: str = "info"  # "critical", "warning", "ok", "info"
    supporting_data: dict = field(default_factory=dict)
    chart_type: str | None = None


def format_currency(value: float, currency: str = "USD") -> str:
    """Formatea moneda con separador de miles siempre.

    - < 10000: 2 decimales (ej: USD 1.234,50)
    - >= 10000: 0 decimales (ej: USD 15.000)
    """
    if pd.isna(value):
        return "—"
    abs_value = abs(float(value))
    decimals = 2 if abs_value < 10000 else 0
    formatted = f"{float(value):,.{decimals}f}"
    # Spanish format: punto de miles, coma decimal
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency} {formatted}"


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
        f"**{format_number(total_conversions)} conversiones** "
        f"(CPA: {format_currency(cpa) if cpa else 'N/A'}, Tasa conversión: {format_percentage(cvr)}).",
        f"",
    ]

    return "\n".join(lines)


def generate_top_campaigns_summary(
    df_campaign: pd.DataFrame,
    top_n: int = 5,
) -> str:
    """Pregunta 2: ¿Qué campañas concentran la mayor parte de la inversión y los resultados?"""

    total_campaigns = len(df_campaign)
    effective_n = min(top_n, total_campaigns)
    top_spend = df_campaign.nlargest(effective_n, "spend_usd")
    top_conv = df_campaign.nlargest(effective_n, "conversions")

    spend_pct = top_spend["spend_usd"].sum() / df_campaign["spend_usd"].sum() * 100 if df_campaign["spend_usd"].sum() > 0 else 0
    conv_pct = top_conv["conversions"].sum() / df_campaign["conversions"].sum() * 100 if df_campaign["conversions"].sum() > 0 else 0

    if total_campaigns <= top_n:
        lines = [
            f"**Distribución de inversión y resultados**",
            f"",
            f"La cuenta tiene **{total_campaigns} campañas** en total, así que el presupuesto se reparte entre todas ellas:",
            f"",
        ]
    else:
        lines = [
            f"**Concentración de inversión y resultados (Top {effective_n})**",
            f"",
            f"Las **{effective_n} campañas con mayor inversión** concentran el **{spend_pct:.0f}%** del gasto total:",
            f"",
        ]

    for _, row in top_spend.iterrows():
        lines.append(f"- **{row['campaign']}**: {format_currency(row['spend_usd'])} ({row['spend_usd']/df_campaign['spend_usd'].sum()*100:.1f}% del total)")

    if total_campaigns <= top_n:
        lines.extend([
            f"",
            f"De la misma forma, las conversiones se reparten entre las **{total_campaigns} campañas**:",
            f"",
        ])
    else:
        lines.extend([
            f"",
            f"Las **{effective_n} campañas con más conversiones** concentran el **{conv_pct:.0f}%** de los resultados:",
            f"",
        ])

    for _, row in top_conv.iterrows():
        lines.append(f"- **{row['campaign']}**: {format_number(row['conversions'])} conv. ({row['conversions']/df_campaign['conversions'].sum()*100:.1f}% del total)")

    return "\n".join(lines)


def _display_network_mask(network_series: pd.Series) -> pd.Series:
    """Detecta filas servidas en la Red de Display (incluye 'content'/'contenido')."""

    normalized = network_series.astype("string").str.lower()
    return normalized.str.contains("display|content|contenido", na=False, regex=True)


def _display_network_metrics_by_campaign(df_daily: pd.DataFrame | None) -> dict:
    """Suma la inversión y los resultados generados en la Red de Display por campaña."""

    if df_daily is None or "network" not in df_daily.columns:
        return {}

    display_rows = df_daily[_display_network_mask(df_daily["network"])]
    if display_rows.empty:
        return {}

    spend_column = "spend_usd" if "spend_usd" in display_rows.columns else "spend"
    aggregations = {"spend": (spend_column, "sum")}
    if "conversions" in display_rows.columns:
        aggregations["conversions"] = ("conversions", "sum")

    grouped = display_rows.groupby("campaign", as_index=False).agg(**aggregations)
    return {row["campaign"]: row for _, row in grouped.iterrows()}


def _display_network_labels(df_daily: pd.DataFrame | None, campaign: str) -> list[str]:
    """Devuelve las etiquetas de Red de Display observadas para una campaña."""

    if df_daily is None or "network" not in df_daily.columns:
        return []

    mask = (df_daily["campaign"] == campaign) & _display_network_mask(df_daily["network"])
    labels = df_daily.loc[mask, "network"].dropna().astype(str).unique()
    return [label.strip() for label in labels if label.strip()]


def generate_wasted_budget_insight(
    df_campaign: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    display_findings: list,
    spend_no_results_findings: list,
    network_available: bool = True,
    df_daily: pd.DataFrame | None = None,
) -> str:
    """Pregunta 3: ¿Hay presupuesto que se está desperdiciando (ej. Display en Búsqueda)?"""

    lines = [
        f"**Detección de presupuesto desperdiciado**",
        f"",
    ]

    if not network_available:
        lines.append("⚠️ **No se pudo evaluar la red (Network):** el reporte no incluye la columna de Red/Network, por lo que no es posible detectar gasto de Display en campañas de Búsqueda. Pedile al cliente/proveedor que exporte el reporte con la columna de Red incluida.")
        lines.append(f"")

    # Display en búsqueda: el comentario de configuración va arriba del detalle
    if display_findings:
        lines.append(
            "🔴 **Red de Display activada en campañas de Búsqueda** "
            "(esto es un error de configuración que desperdicia presupuesto):"
        )
        display_metrics = _display_network_metrics_by_campaign(df_daily)
        for finding in display_findings:
            labels = _display_network_labels(df_daily, finding.campaign)
            metrics = display_metrics.get(finding.campaign)
            detail = f"   - **{finding.campaign}** está activa en la Red de Display"
            if labels:
                detail += f" (figura como: {', '.join(labels)})"
            detail += "."
            if metrics is not None:
                detail += f" En esa red gastó {format_currency(metrics['spend'])}"
                if "conversions" in metrics.index:
                    conversions = metrics["conversions"]
                    if pd.isna(conversions) or conversions == 0:
                        detail += " y no generó ninguna conversión."
                    else:
                        detail += f" y generó {format_number(conversions)} conversiones."
                else:
                    detail += "."
            lines.append(detail)
        lines.append(
            "   Conviene revisar la configuración de estas campañas y desactivar la "
            "Red de Display, salvo que sea una decisión intencional."
        )
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

    if not display_findings and not spend_no_results_findings and low_volume_spend.empty and network_available:
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
                    lines.append(f"   - **{c}**: {format_number(r['conversions'])} conv, CPA {format_currency(r.get('cpa', 0))}, inversión actual {format_currency(r['spend_usd'])}")
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
            lines.append(f"   - **{f.campaign}**: {f.message}")
        lines.append(f"")

    if cpa_outliers:
        lines.append(f"🔴 **Outliers críticos de CPA** (variación >2x umbral normal):")
        for f in cpa_outliers:
            lines.append(f"   - **{f.campaign}**: {f.message}")
        lines.append(f"")

    # Top CPA actual
    if "cpa" in df_campaign.columns:
        top_cpa = df_campaign[df_campaign["cpa"].notna()].nlargest(3, "cpa")
        if not top_cpa.empty:
            lines.append(f"📊 **Top 3 CPA actual en la cuenta**:")
            for _, row in top_cpa.iterrows():
                lines.append(f"   - **{row['campaign']}**: CPA {format_currency(row['cpa'])}, {format_number(row['conversions'])} conv.")
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
        title="Performance de las campañas en el período",
        status="info",
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
        title="Dónde está concentrada la plata y los resultados",
        status="info",
        answer=generate_top_campaigns_summary(df_campaign),
        supporting_data={"pareto_analysis": pareto_analysis},
        chart_type="pareto_chart",
    ))

    # Pregunta 3
    network_available = "network" in df_daily.columns
    low_volume_flagged = eligibility_df[
        (eligibility_df["eligibility_status"] == "insufficient_volume") &
        (eligibility_df["is_eligible"] == False)
    ]
    if display_findings or spend_no_results:
        waste_status = "critical"
    elif not low_volume_flagged.empty:
        waste_status = "warning"
    else:
        waste_status = "ok"
    insights.append(CampaignInsight(
        question_number=3,
        question="¿Hay presupuesto que se está desperdiciando (ej. Display en Búsqueda)?",
        title="Plata que puede estar desperdiciándose",
        status=waste_status,
        answer=generate_wasted_budget_insight(
            df_campaign,
            eligibility_df,
            display_findings,
            spend_no_results,
            network_available=network_available,
            df_daily=df_daily,
        ),
        supporting_data={
            "display_findings": display_findings,
            "spend_no_results": spend_no_results,
        },
        chart_type="network_breakdown",
    ))

    # Pregunta 4
    scale_opportunities = [f for f in pareto_findings if f.get("rule_id") == "pareto_opportunity"]
    budget_limited = [f for f in benchmark_findings if "budget" in f.rule_id.lower() or "impr_share" in f.rule_id.lower()]
    insights.append(CampaignInsight(
        question_number=4,
        question="¿Qué campañas tienen buen resultado y podrían recibir más presupuesto?",
        title="Campañas a las que conviene darles más presupuesto",
        status="ok" if (scale_opportunities or budget_limited) else "info",
        answer=generate_scale_opportunities(df_campaign, pareto_findings, benchmark_findings),
        supporting_data={"pareto_opportunities": pareto_findings},
        chart_type="scatter_cpa_conversions",
    ))

    # Pregunta 5
    is_drop = [f for f in benchmark_findings if "impression_share" in f.rule_id.lower() or "impr_share" in f.rule_id.lower()]
    insights.append(CampaignInsight(
        question_number=5,
        question="¿Qué campañas están perdiendo visibilidad frente a la competencia?",
        title="Pérdida de visibilidad frente a la competencia",
        status="warning" if is_drop else "ok",
        answer=generate_visibility_loss_insight(benchmark_findings),
        supporting_data={"impression_share_findings": [f for f in benchmark_findings if "impr" in f.rule_id.lower()]},
        chart_type="impression_share_trend",
    ))

    # Pregunta 6
    ctr_findings = [f for f in benchmark_findings if "ctr" in f.rule_id.lower()]
    cvr_findings = [f for f in benchmark_findings if "conversion_rate" in f.rule_id.lower() or "conversions_drop" in f.rule_id.lower()]
    insights.append(CampaignInsight(
        question_number=6,
        question="¿Qué campañas atraen clics pero no logran conversiones (o al revés)?",
        title="Clics que no se convierten (y viceversa)",
        status="warning" if (ctr_findings or cvr_findings) else "ok",
        answer=generate_clicks_vs_conversions_insight(benchmark_findings),
        supporting_data={"ctr_findings": ctr_findings},
        chart_type="ctr_vs_cvr_matrix",
    ))

    # Pregunta 7
    cpa_findings = [f for f in benchmark_findings if "cpa" in f.rule_id.lower()]
    insights.append(CampaignInsight(
        question_number=7,
        question="¿Qué campañas tienen un costo por resultado demasiado alto?",
        title="Campañas con costo por resultado elevado",
        status="critical" if (cpa_findings or cpa_outliers) else "ok",
        answer=generate_high_cpa_insight(df_campaign, benchmark_findings, cpa_outliers),
        supporting_data={"cpa_findings": cpa_outliers},
        chart_type="cpa_ranking",
    ))

    # Pregunta 8
    insufficient_count = len(
        eligibility_df[eligibility_df["eligibility_status"].isin(["insufficient_volume", "insufficient_history"])]
    )
    insights.append(CampaignInsight(
        question_number=8,
        question="¿Qué campañas tienen tan pocos datos que conviene esperar antes de sacar conclusiones?",
        title="Campañas con pocos datos: esperar antes de decidir",
        status="warning" if insufficient_count else "ok",
        answer=generate_insufficient_data_insight(eligibility_df),
        supporting_data={"eligibility_summary": eligibility_df["eligibility_status"].value_counts().to_dict()},
        chart_type=None,
    ))

    # Pregunta 9
    insights.append(CampaignInsight(
        question_number=9,
        question="¿Cuáles son los 2 a 5 hallazgos más relevantes de la semana?",
        title="Los 2 a 5 hallazgos más importantes de la semana",
        status="critical" if any(getattr(f, "is_outlier", False) for f in scored_findings) else "info",
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
        heading = insight.title or insight.question
        lines.append(f"## {insight.question_number}. {heading}")
        lines.append(f"")
        lines.append(insight.answer)
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

    return "\n".join(lines)


def generate_template_executive_summary(
    insights: list[CampaignInsight],
    df_campaign: pd.DataFrame,
    scored_findings: list | None = None,
) -> str:
    """
    Genera resumen ejecutivo narrativo usando templates locales (sin IA).
    Estructura obligatoria siguiendo las 9 preguntas del roadmap.
    """
    # Extraer KPIs globales
    total_spend = df_campaign["spend_usd"].sum()
    total_conv = df_campaign["conversions"].sum()
    total_clicks = int(df_campaign["clicks"].sum())
    total_impr = int(df_campaign["impressions"].sum())
    ctr = total_clicks / total_impr if total_impr > 0 else 0
    cpa = total_spend / total_conv if total_conv > 0 else 0

    # Helper para buscar insights por palabras clave
    def find_insights(keywords):
        found = []
        for ins in insights:
            ans = getattr(ins, "answer", "").lower()
            if any(kw.lower() in ans for kw in keywords):
                found.append(ins)
        return found

    def extract_msg(insights_list, max_chars=120):
        return "; ".join([getattr(i, "answer", "")[:max_chars] for i in insights_list[:3]])

    # Construir secciones
    sections = []

    # 1. QUÉ PASÓ
    sections.append(
        f"**1. QUÉ PASÓ**: Inversión total ${total_spend:,.0f} | "
        f"{total_impr:,} impresiones | {total_clicks:,} clics (CTR {ctr:.1%}) | "
        f"{total_conv:.1f} conversiones (CPA ${cpa:,.0f})"
    )

    # 2. CONCENTRACIÓN (Pareto)
    pareto_top = df_campaign.nlargest(5, "spend_usd")
    spend_pct = (
        pareto_top["spend_usd"].sum() / total_spend * 100
        if total_spend > 0 else 0
    )
    conv_pct = (
        pareto_top["conversions"].sum() / total_conv * 100
        if total_conv > 0 else 0
    )
    pareto_lines = "; ".join(
        f"{r['campaign']}: ${r['spend_usd']:,.0f} ({r['conversions']:.1f} conv)"
        for _, r in pareto_top.iterrows()
    )
    sections.append(
        f"**2. CONCENTRACIÓN**: Top 5 = {spend_pct:.0f}% gasto, "
        f"{conv_pct:.0f}% conv | {pareto_lines}"
    )

    # 3. DESPERDICIO
    disp = find_insights(["display", "red de display"])
    spend_nr = find_insights(["gasto sin", "sin clic", "sin convers"])
    waste_parts = []
    if disp: waste_parts.append(f"Display en Search: {len(disp)} campaña(s)")
    if spend_nr: waste_parts.append(f"Gasto sin resultados: {len(spend_nr)} campaña(s)")
    sections.append(
        f"**3. DESPERDICIO**: {'; '.join(waste_parts) if waste_parts else 'Sin desperdicios detectados'}"
    )

    # 4. ESCALA
    scale = find_insights(["escal", "oportunidad", "pareto oportunidad"])
    sections.append(
        f"**4. ESCALA**: {extract_msg(scale) if scale else 'Sin oportunidades claras'}"
    )

    # 5. VISIBILIDAD
    vis = find_insights(["visibilidad", "impression share", "impr share", "cuota de impres"])
    sections.append(
        f"**5. VISIBILIDAD**: {extract_msg(vis) if vis else 'Sin pérdidas significativas de IS'}"
    )

    # 6. CLICS VS CONVERSIONES
    ctr_f = find_insights(["ctr", "tasa de clic"])
    cvr_f = find_insights(["tasa de convers", "conversion rate", "conversiones vs"])
    click_conv_parts = []
    if ctr_f: click_conv_parts.append(f"CTR: {len(ctr_f)} variación(es)")
    if cvr_f: click_conv_parts.append(f"Tasa conv: {len(cvr_f)} variación(es)")
    sections.append(
        f"**6. CLICS VS CONV**: {'; '.join(click_conv_parts) if click_conv_parts else 'CTR y tasa conv en rangos normales'}"
    )

    # 7. CPA ALTO
    cpa_f = find_insights(["cpa alto", "cpa elevad", "costo por resultado", "sobre benchmark"])
    sections.append(
        f"**7. CPA ALTO**: {extract_msg(cpa_f) if cpa_f else 'CPAs en rangos normales'}"
    )

    # 8. DATOS INSUFICIENTES
    insuff = find_insights(["insuficiente", "esperar", "pocos datos"])
    sections.append(
        f"**8. DATOS INSUFICIENTES**: {extract_msg(insuff) if insuff else 'Todas con datos suficientes'}"
    )

    # 9. TOP HALLAZGOS
    if scored_findings:
        findings_text = []
        for i, f in enumerate(scored_findings[:5], 1):
            outlier = " ⚡" if getattr(f, "is_outlier", False) else ""
            findings_text.append(
                f"{i}. {f.rule_name} ({f.campaign}){outlier}: {f.message[:120]}"
            )
        sections.append(
            "**9. TOP 5 HALLAZGOS**:\n" + "\n".join(findings_text)
        )
    else:
        top_h = find_insights(["top ", "hallazg", "relevant"])
        sections.append(
            f"**9. TOP HALLAZGOS**: {extract_msg(top_h) if top_h else 'Ver lista completa'}"
        )

    return "\n\n".join(sections)


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
    api_key: str | None = None,
) -> tuple[list[CampaignInsight], Optional[str]]:
    """
    Construye reporte completo + narrativa ejecutiva opcional con LLM (Groq).
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
        llm_narrative = generate_llm_narrative(
            insights, df_campaign, 
            scored_findings=scored_findings,
            api_key=api_key,
        )
        if llm_narrative:
            # Insertar como insight 0 (resumen ejecutivo narrativo)
            insights.insert(0, CampaignInsight(
                question_number=0,
                question="📋 Resumen Ejecutivo (IA)",
                title="Resumen ejecutivo generado con IA",
                status="info",
                answer=llm_narrative,
                supporting_data={"generated_by": "llm-groq"},
                chart_type=None,
            ))

    return insights, llm_narrative