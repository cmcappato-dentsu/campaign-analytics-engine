"""Generación de reportes e insights textuales (70% visual, 30% texto)."""

import os
import pandas as pd
from typing import Optional
from dataclasses import dataclass, field

from config.thresholds import (
    WASTE_CPA_MEDIAN_MULTIPLIER,
    WASTE_LOST_IS_BUDGET_THRESHOLD,
    WASTE_MIN_CAMPAIGNS_FOR_MEDIAN,
    WASTE_NETWORK_CPA_MULTIPLIER,
    WASTE_NETWORK_MIN_SPEND_SHARE,
)

INEFFICIENCY_TABLE_LIMIT = 10

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


def _spend_column(df: pd.DataFrame) -> str:
    """Devuelve la columna de inversión disponible en el dataset."""

    return "spend_usd" if "spend_usd" in df.columns else "spend"


def _normalize_ratio(values: pd.Series) -> pd.Series:
    """Lleva porcentajes exportados como 35 o 0,35 a una fracción entre 0 y 1."""

    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.where(numeric <= 1, numeric / 100)


def _eligible_campaign_names(eligibility_df: pd.DataFrame | None) -> set[str] | None:
    """Devuelve el conjunto de campañas elegibles, o None si no hay datos."""

    if eligibility_df is None or "is_eligible" not in eligibility_df.columns:
        return None

    eligible = eligibility_df["is_eligible"].eq(True) & eligibility_df["campaign"].notna()
    return set(eligibility_df.loc[eligible, "campaign"].astype(str))


def _median_eligible_cpa(
    df_campaign: pd.DataFrame,
    eligibility_df: pd.DataFrame | None,
) -> float | None:
    """Calcula el CPA mediano de las campañas elegibles con conversiones."""

    if df_campaign is None or "cpa" not in df_campaign.columns:
        return None

    frame = df_campaign
    eligible = _eligible_campaign_names(eligibility_df)
    if eligible is not None:
        frame = frame[frame["campaign"].astype(str).isin(eligible)]

    valid = frame[(frame["conversions"] > 0) & frame["cpa"].notna()]
    if len(valid) < WASTE_MIN_CAMPAIGNS_FOR_MEDIAN:
        return None

    return float(valid["cpa"].median())


def _is_display_network(network: str) -> bool:
    """Indica si una etiqueta de red corresponde a Display/Content."""

    normalized = str(network).strip().lower()
    return any(token in normalized for token in ("display", "content", "contenido"))


def _network_performance_signals(
    df_daily: pd.DataFrame | None,
    total_spend: float,
    display_findings: list,
) -> tuple[list, list]:
    """Detecta redes con gasto sin conversiones o con CPA muy superior."""

    if df_daily is None or "network" not in df_daily.columns or total_spend <= 0:
        return [], []

    frame = df_daily[df_daily["network"].notna()].copy()
    if frame.empty:
        return [], []

    spend_column = _spend_column(frame)
    frame["_spend"] = pd.to_numeric(frame[spend_column], errors="coerce").fillna(0)
    if "conversions" in frame.columns:
        frame["_conversions"] = pd.to_numeric(frame["conversions"], errors="coerce").fillna(0)
    else:
        frame["_conversions"] = 0.0

    grouped = frame.groupby(
        ["campaign", "network"], dropna=False, as_index=False
    ).agg(
        spend=("_spend", "sum"),
        conversions=("_conversions", "sum"),
    )

    campaign_totals = grouped.groupby("campaign").agg(
        spend=("spend", "sum"),
        conversions=("conversions", "sum"),
    )
    campaign_cpa = {
        campaign: (row["spend"] / row["conversions"])
        for campaign, row in campaign_totals.iterrows()
        if row["conversions"] > 0 and row["spend"] > 0
    }

    display_campaigns = {finding.campaign for finding in display_findings}
    zero_conversion = []
    inefficient = []

    for _, row in grouped.iterrows():
        campaign = row["campaign"]
        network = str(row["network"]).strip()
        spend = float(row["spend"])
        conversions = float(row["conversions"])

        if not network or spend <= 0:
            continue

        share = spend / total_spend
        if share < WASTE_NETWORK_MIN_SPEND_SHARE:
            continue

        # La Red de Display en Búsqueda ya se reporta como error de configuración.
        if campaign in display_campaigns and _is_display_network(network):
            continue

        if conversions <= 0:
            zero_conversion.append({
                "campaign": campaign,
                "network": network,
                "spend": spend,
                "share": share,
            })
            continue

        reference_cpa = campaign_cpa.get(campaign)
        if not reference_cpa:
            continue

        network_cpa = spend / conversions
        if network_cpa > reference_cpa * WASTE_NETWORK_CPA_MULTIPLIER:
            inefficient.append({
                "campaign": campaign,
                "network": network,
                "spend": spend,
                "conversions": conversions,
                "cpa": network_cpa,
                "campaign_cpa": reference_cpa,
                "ratio": network_cpa / reference_cpa,
            })

    zero_conversion.sort(key=lambda row: row["spend"], reverse=True)
    inefficient.sort(key=lambda row: row["spend"], reverse=True)
    return zero_conversion, inefficient


def _cpa_inefficiency_signals(
    df_campaign: pd.DataFrame,
    eligibility_df: pd.DataFrame | None,
    median_cpa: float | None,
) -> list[dict]:
    """Campañas elegibles cuyo CPA supera ampliamente la mediana de la cuenta."""

    if median_cpa is None or median_cpa <= 0 or df_campaign is None:
        return []

    frame = df_campaign
    eligible = _eligible_campaign_names(eligibility_df)
    if eligible is not None:
        frame = frame[frame["campaign"].astype(str).isin(eligible)]

    if "cpa" not in frame.columns:
        return []

    spend_column = _spend_column(frame)
    valid = frame[
        (frame["conversions"] > 0)
        & (frame[spend_column] > 0)
        & frame["cpa"].notna()
    ]

    threshold = median_cpa * WASTE_CPA_MEDIAN_MULTIPLIER
    rows = []
    for _, row in valid[valid["cpa"] > threshold].iterrows():
        spend = float(row[spend_column])
        conversions = float(row["conversions"])
        cpa = float(row["cpa"])
        rows.append({
            "campaign": row["campaign"],
            "spend": spend,
            "conversions": conversions,
            "cpa": cpa,
            "median_cpa": median_cpa,
            "ratio": cpa / median_cpa,
            "excess_cost": max(0.0, spend - conversions * median_cpa),
        })

    rows.sort(key=lambda row: row["excess_cost"], reverse=True)
    return rows


def _budget_opportunity_signals(
    df_daily: pd.DataFrame | None,
    df_campaign: pd.DataFrame,
    median_cpa: float | None,
    eligibility_df: pd.DataFrame | None = None,
) -> list[dict]:
    """Campañas elegibles que pierden impresiones por presupuesto (oportunidad, no desperdicio)."""

    if df_daily is None or "lost_is_budget" not in df_daily.columns:
        return []

    frame = df_daily.copy()
    frame["_lost"] = _normalize_ratio(frame["lost_is_budget"])
    frame = frame[frame["_lost"].notna()]
    if frame.empty:
        return []

    if "impressions" in frame.columns:
        frame["_weight"] = pd.to_numeric(frame["impressions"], errors="coerce").fillna(0)
    else:
        frame["_weight"] = 0.0

    rows = []
    for campaign, group in frame.groupby("campaign"):
        weight = group["_weight"].sum()
        if weight > 0:
            lost = (group["_lost"] * group["_weight"]).sum() / weight
        else:
            lost = group["_lost"].mean()

        if pd.notna(lost):
            rows.append({"campaign": campaign, "lost_share": float(lost)})

    if not rows:
        return []

    lost_df = pd.DataFrame(rows)

    # Solo campañas elegibles: con volumen suficiente para sostener la conclusión.
    eligible = _eligible_campaign_names(eligibility_df)
    if eligible is not None:
        lost_df = lost_df[lost_df["campaign"].astype(str).isin(eligible)]

    spend_column = _spend_column(df_campaign)
    metric_columns = ["campaign", spend_column, "conversions"]
    if "cpa" in df_campaign.columns:
        metric_columns.append("cpa")

    merged = lost_df.merge(
        df_campaign[metric_columns], on="campaign", how="inner"
    )
    merged = merged[
        (merged["lost_share"] >= WASTE_LOST_IS_BUDGET_THRESHOLD)
        & (merged[spend_column] > 0)
    ]

    opportunities = []
    for _, row in merged.sort_values("lost_share", ascending=False).iterrows():
        lost = min(float(row["lost_share"]), 0.90)
        spend = float(row[spend_column])
        cpa = row.get("cpa")
        cpa = float(cpa) if pd.notna(cpa) else None

        if median_cpa is None or cpa is None:
            efficient = None
        else:
            efficient = cpa <= median_cpa

        opportunities.append({
            "campaign": row["campaign"],
            "lost_share": lost,
            "spend": spend,
            "conversions": float(row["conversions"]),
            "cpa": cpa,
            "efficient": efficient,
            "estimated_upside": spend * lost / (1 - lost) if lost > 0 else 0.0,
        })

    return opportunities


def analyze_waste_signals(
    df_campaign: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    display_findings: list,
    spend_no_results_findings: list,
    network_available: bool = True,
    df_daily: pd.DataFrame | None = None,
) -> dict:
    """Reúne las señales del punto 3 separando desperdicio, ineficiencia y oportunidad."""

    total_spend = (
        float(pd.to_numeric(df_daily[_spend_column(df_daily)], errors="coerce").fillna(0).sum())
        if df_daily is not None and _spend_column(df_daily) in df_daily.columns
        else float(df_campaign["spend_usd"].sum())
    )
    median_cpa = _median_eligible_cpa(df_campaign, eligibility_df)
    network_zero, network_inefficient = _network_performance_signals(
        df_daily, total_spend, display_findings
    )

    return {
        "total_spend": total_spend,
        "median_cpa": median_cpa,
        "budget_data_available": df_daily is not None and "lost_is_budget" in df_daily.columns,
        "network_zero_conversion": network_zero,
        "network_inefficient": network_inefficient,
        "cpa_inefficient": _cpa_inefficiency_signals(
            df_campaign, eligibility_df, median_cpa
        ),
        "budget_opportunities": _budget_opportunity_signals(
            df_daily, df_campaign, median_cpa, eligibility_df
        ),
    }


def generate_wasted_budget_insight(
    df_campaign: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    display_findings: list,
    spend_no_results_findings: list,
    network_available: bool = True,
    df_daily: pd.DataFrame | None = None,
    analysis: dict | None = None,
) -> str:
    """Pregunta 3: ¿Hay presupuesto que se está desperdiciando (ej. Display en Búsqueda)?"""

    analysis = analysis or analyze_waste_signals(
        df_campaign,
        eligibility_df,
        display_findings,
        spend_no_results_findings,
        network_available=network_available,
        df_daily=df_daily,
    )

    lines = [
        "El análisis separa **desperdicio confirmado** (plata sin retorno), "
        "**ineficiencia** (plata que rinde peor que la referencia) y "
        "**oportunidad no capturada** (inversión que se podría sumar; no es plata perdida).",
        f"",
    ]

    if not network_available:
        lines.append("⚠️ **No se pudo evaluar la red (Network):** el reporte no incluye la columna de Red/Network, por lo que no es posible detectar gasto de Display en campañas de Búsqueda ni comparar el rendimiento entre redes. Pedile al cliente/proveedor que exporte el reporte con la columna de Red incluida.")
        lines.append(f"")

    # Display en búsqueda: título del problema + tabla compacta por campaña
    if display_findings:
        lines.append("🔴 **Red de Display activada en campañas de Búsqueda**")
        lines.append("*Error de configuración que desperdicia presupuesto.*")
        lines.append("")
        lines.append("| Campaña | Red observada | Gasto en Display | Resultado |")
        lines.append("| --- | --- | --- | --- |")

        display_metrics = _display_network_metrics_by_campaign(df_daily)
        for finding in display_findings:
            labels = _display_network_labels(df_daily, finding.campaign)
            metrics = display_metrics.get(finding.campaign)

            network_text = ", ".join(labels) if labels else "—"

            if metrics is None:
                spend_text = "—"
                result_text = "—"
            else:
                spend_text = format_currency(metrics["spend"])
                if "conversions" not in metrics.index or pd.isna(metrics["conversions"]):
                    result_text = "—"
                elif metrics["conversions"] == 0:
                    result_text = "0 conversiones"
                else:
                    result_text = f"{format_number(metrics['conversions'])} conversiones"

            lines.append(
                f"| **{finding.campaign}** | {network_text} | {spend_text} | {result_text} |"
            )

        lines.append("")
        lines.append(
            "Conviene revisar la configuración de estas campañas y desactivar la "
            "Red de Display, salvo que sea una decisión intencional."
        )
        lines.append(f"")

    # Gasto sin resultados
    if spend_no_results_findings:
        lines.append(f"🔴 **Gasto sin resultados (clics/conversiones = 0)**:")
        for f in spend_no_results_findings:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    # Redes con gasto y sin conversiones
    if analysis["network_zero_conversion"]:
        lines.append("🔴 **Redes con gasto y 0 conversiones**:")
        for row in analysis["network_zero_conversion"]:
            lines.append(
                f"   - **{row['campaign']}** en la red \"{row['network']}\": "
                f"{format_currency(row['spend'])} "
                f"({format_percentage(row['share'])} del gasto total) sin conversiones."
            )
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
        lines.append(f"⚪ **Riesgo: campañas con volumen insuficiente para análisis pero con gasto**: {format_currency(total_wasted)} en {len(low_volume_spend)} campañas.")
        lines.append("   Estas campañas no generan señal estadística confiable. Revisar si mantener activas.")

    # Ineficiencia: campañas y redes con CPA muy superior a la referencia
    cpa_inefficient = analysis["cpa_inefficient"]
    network_inefficient = analysis["network_inefficient"]
    if cpa_inefficient or network_inefficient:
        header = "🟡 **Ineficiencia: exceso de costo estimado**"
        if analysis["median_cpa"]:
            header += f" (CPA mediano de la cuenta: {format_currency(analysis['median_cpa'])})"
        lines.append(header)
        lines.append("")

        if cpa_inefficient:
            lines.append("| Campaña | CPA | vs. mediana | Conversiones | Exceso estimado |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in cpa_inefficient[:INEFFICIENCY_TABLE_LIMIT]:
                lines.append(
                    f"| **{row['campaign']}** | {format_currency(row['cpa'])} | "
                    f"{row['ratio']:.1f}× | {format_number(row['conversions'])} | "
                    f"{format_currency(row['excess_cost'])} |"
                )
            lines.append("")

            remaining = len(cpa_inefficient) - INEFFICIENCY_TABLE_LIMIT
            if remaining > 0:
                lines.append(
                    f"Mostrando las {INEFFICIENCY_TABLE_LIMIT} campañas con mayor "
                    f"exceso de costo de {len(cpa_inefficient)}. "
                    f"Usá el botón **Ver las {remaining} restantes** para el detalle completo."
                )
                lines.append("")

        if network_inefficient:
            lines.append("**Ineficiencia por red**")
            lines.append("")
            lines.append("| Campaña | Red | CPA red | CPA campaña | Gasto |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in network_inefficient[:INEFFICIENCY_TABLE_LIMIT]:
                lines.append(
                    f"| **{row['campaign']}** | {row['network']} | "
                    f"{format_currency(row['cpa'])} | {format_currency(row['campaign_cpa'])} | "
                    f"{format_currency(row['spend'])} |"
                )
            lines.append("")

    if (
        network_available
        and not display_findings
        and not spend_no_results_findings
        and not analysis["network_zero_conversion"]
        and not cpa_inefficient
        and not network_inefficient
    ):
        lines.append(f"✅ No se detectó desperdicio confirmado ni ineficiencia en esta corrida.")

    # Oportunidad no capturada: el detalle completo vive en el punto 4
    opportunities = analysis["budget_opportunities"]
    if opportunities:
        count = len(opportunities)
        noun = "campaña" if count == 1 else "campañas"
        adjective = "limitada" if count == 1 else "limitadas"
        lines.append(f"")
        lines.append(
            f"🟠 **Oportunidad no capturada (no es desperdicio):** "
            f"{count} {noun} {adjective} por presupuesto. "
            f"El detalle y el techo estimado están en el **punto 4**."
        )
        lines.append(f"")

    return "\n".join(lines)



def generate_scale_opportunities(
    opportunities: list[dict],
    median_cpa: float | None,
    budget_data_available: bool = True,
) -> str:
    """Pregunta 4: ¿Qué campañas podrían recibir más presupuesto?

    Solo considera campañas limitadas por presupuesto (cuota de impresiones
    perdida por presupuesto), no campañas eficientes por CPA sin esa señal.
    """

    lines = [
        f"**Oportunidades de escalar inversión**",
        f"",
    ]

    if not budget_data_available:
        lines.append(
            "⚠️ **No se puede medir el techo de inversión:** el reporte no incluye "
            "la columna de cuota de impresiones perdida por presupuesto "
            "(`lost_is_budget`). Pedile al proveedor que la incluya para detectar "
            "campañas limitadas por presupuesto."
        )
        return "\n".join(lines)

    if not opportunities:
        lines.append(
            "✅ No se identificaron campañas limitadas por presupuesto "
            f"(cuota perdida por presupuesto ≥ {format_percentage(WASTE_LOST_IS_BUDGET_THRESHOLD)})."
        )
        return "\n".join(lines)

    total_spend = sum(row["spend"] for row in opportunities)
    total_upside = sum(row["estimated_upside"] for row in opportunities)
    count = len(opportunities)
    noun = "campaña" if count == 1 else "campañas"
    verb = "pierde" if count == 1 else "pierden"

    lines.append(
        f"Se detectaron **{count} {noun}** que {verb} impresiones "
        f"por límite de presupuesto (cuota perdida ≥ "
        f"{format_percentage(WASTE_LOST_IS_BUDGET_THRESHOLD)})."
    )
    if median_cpa is not None:
        lines.append(
            f"CPA mediano de la cuenta: **{format_currency(median_cpa)}**."
        )
    lines.append(
        f"Inversión actual: **{format_currency(total_spend)}**. "
        f"Techo adicional estimado: **{format_currency(total_upside)}**."
    )
    lines.append("")

    lines.append(
        "| Campaña | Cuota perdida por presupuesto | CPA | Inversión actual | Techo estimado | Prioridad |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")

    for row in opportunities:
        cpa_text = (
            format_currency(row["cpa"]) if row["cpa"] is not None else "—"
        )
        if row["efficient"] is True:
            priority = "🟢 Alta"
        elif row["efficient"] is False:
            priority = "🟡 Revisar eficiencia"
        else:
            priority = "⚪ Sin referencia"

        lines.append(
            f"| **{row['campaign']}** | {format_percentage(row['lost_share'])} | "
            f"{cpa_text} | {format_currency(row['spend'])} | "
            f"{format_currency(row['estimated_upside'])} | {priority} |"
        )

    lines.append("")
    lines.append(
        "El techo estimado es una referencia de cuánto más se podría invertir para "
        "capturar las impresiones perdidas por presupuesto. No es una recomendación "
        "automática: validar capacidad, objetivos y eficiencia antes de escalar."
    )

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
    waste_analysis = analyze_waste_signals(
        df_campaign,
        eligibility_df,
        display_findings,
        spend_no_results,
        network_available=network_available,
        df_daily=df_daily,
    )
    confirmed_waste = (
        bool(display_findings)
        or bool(spend_no_results)
        or bool(waste_analysis["network_zero_conversion"])
    )
    inefficiency = (
        bool(waste_analysis["cpa_inefficient"])
        or bool(waste_analysis["network_inefficient"])
    )
    if confirmed_waste:
        waste_status = "critical"
    elif inefficiency or not low_volume_flagged.empty:
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
            analysis=waste_analysis,
        ),
        supporting_data={
            "display_findings": display_findings,
            "spend_no_results": spend_no_results,
            "network_zero_conversion": waste_analysis["network_zero_conversion"],
            "cpa_inefficient": waste_analysis["cpa_inefficient"],
            "network_inefficient": waste_analysis["network_inefficient"],
            "budget_opportunities": waste_analysis["budget_opportunities"],
            "median_cpa": waste_analysis["median_cpa"],
        },
        chart_type="network_breakdown",
    ))

    # Pregunta 4
    scale_opportunities = waste_analysis["budget_opportunities"]
    insights.append(CampaignInsight(
        question_number=4,
        question="¿Qué campañas tienen buen resultado y podrían recibir más presupuesto?",
        title="Campañas a las que conviene darles más presupuesto",
        status="ok" if scale_opportunities else "info",
        answer=generate_scale_opportunities(
            scale_opportunities,
            waste_analysis["median_cpa"],
            budget_data_available=waste_analysis["budget_data_available"],
        ),
        supporting_data={"budget_opportunities": scale_opportunities},
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
    ineff = find_insights(["ineficiencia", "exceso de costo"])
    opp = find_insights(["oportunidad no capturada"])
    waste_parts = []
    if disp: waste_parts.append(f"Display en Search: {len(disp)} campaña(s)")
    if spend_nr: waste_parts.append(f"Gasto sin resultados: {len(spend_nr)} campaña(s)")
    if ineff: waste_parts.append("Ineficiencia detectada")
    if opp: waste_parts.append("Oportunidad no capturada (no es desperdicio)")
    sections.append(
        f"**3. DESPERDICIO**: {'; '.join(waste_parts) if waste_parts else 'Sin desperdicios detectados'}"
    )

    # 4. ESCALA
    scale = find_insights(["escalar inversión", "limitadas por presupuesto"])
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