"""Generación de reportes e insights textuales (70% visual, 30% texto)."""

import os
import pandas as pd
from typing import Optional
from dataclasses import dataclass, field

from config.thresholds import (
    MIN_CLICKS_FOR_ANALYSIS,
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

    spend_total = df_campaign["spend_usd"].sum()
    conv_total = df_campaign["conversions"].sum()

    spend_pct = top_spend["spend_usd"].sum() / spend_total * 100 if spend_total > 0 else 0
    conv_pct = top_conv["conversions"].sum() / conv_total * 100 if conv_total > 0 else 0

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

    # Tabla única con la unión de las campañas top por inversión y por conversiones.
    ordered_campaigns = list(dict.fromkeys([
        *top_spend["campaign"].tolist(),
        *top_conv["campaign"].tolist(),
    ]))
    indexed = df_campaign.set_index("campaign")

    lines.append(
        "| Campaña | Inversión | % de la inversión | Conversiones | "
        "% de las conversiones |"
    )
    lines.append("| --- | --- | --- | --- | --- |")
    for campaign in ordered_campaigns:
        row = indexed.loc[campaign]
        spend = row["spend_usd"]
        conversions = row["conversions"]
        spend_share = spend / spend_total if spend_total > 0 else 0
        conv_share = conversions / conv_total if conv_total > 0 else 0
        lines.append(
            f"| **{campaign}** | {format_currency(spend)} | "
            f"{format_percentage(spend_share)} | {format_number(conversions)} | "
            f"{format_percentage(conv_share)} |"
        )

    lines.extend([
        f"",
        f"Las **{effective_n} campañas con más conversiones** concentran el "
        f"**{conv_pct:.0f}%** de los resultados.",
    ])

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
    cpa_findings: list | None = None,
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
        display_rows = []
        for finding in display_findings:
            labels = _display_network_labels(df_daily, finding.campaign)
            metrics = display_metrics.get(finding.campaign)

            network_text = ", ".join(labels) if labels else "—"

            if metrics is None:
                spend_value = -1.0
                spend_text = "—"
                result_text = "—"
            else:
                spend_value = float(metrics["spend"])
                spend_text = format_currency(metrics["spend"])
                if "conversions" not in metrics.index or pd.isna(metrics["conversions"]):
                    result_text = "—"
                elif metrics["conversions"] == 0:
                    result_text = "0 conversiones"
                else:
                    result_text = f"{format_number(metrics['conversions'])} conversiones"

            row_text = (
                f"| **{finding.campaign}** | {network_text} | {spend_text} | {result_text} |"
            )
            display_rows.append((spend_value, row_text))

        for _, row_text in sorted(display_rows, key=lambda item: item[0], reverse=True):
            lines.append(row_text)

        lines.append("")
        lines.append(
            "Conviene revisar la configuración de estas campañas y desactivar la "
            "Red de Display, salvo que sea una decisión intencional."
        )
        lines.append(f"")

    # Gasto sin resultados
    if spend_no_results_findings:
        lines.append(f"🔴 **Gasto sin resultados (clics/conversiones = 0)**:")
        ordered_spend_no_results = sorted(
            spend_no_results_findings,
            key=lambda finding: finding.metric_value or 0,
            reverse=True,
        )
        for f in ordered_spend_no_results:
            lines.append(f"   - {f.message}")
        lines.append(f"")

    # Redes con gasto y sin conversiones
    if analysis["network_zero_conversion"]:
        lines.append("🔴 **Redes con gasto y 0 conversiones**:")
        ordered_network_zero = sorted(
            analysis["network_zero_conversion"],
            key=lambda row: row["spend"],
            reverse=True,
        )
        for row in ordered_network_zero:
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
        low_volume_names = set(low_volume_spend["campaign"])
        total_wasted = df_campaign[
            df_campaign["campaign"].isin(low_volume_names)
        ]["spend_usd"].sum()
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
            ordered_network_inefficient = sorted(
                network_inefficient,
                key=lambda row: row["spend"],
                reverse=True,
            )
            for row in ordered_network_inefficient[:INEFFICIENCY_TABLE_LIMIT]:
                lines.append(
                    f"| **{row['campaign']}** | {row['network']} | "
                    f"{format_currency(row['cpa'])} | {format_currency(row['campaign_cpa'])} | "
                    f"{format_currency(row['spend'])} |"
                )
            lines.append("")

    # CPA vs objetivo/benchmark (contenido único del antiguo punto 7)
    if cpa_findings:
        lines.extend(_cpa_vs_reference_lines(df_campaign, cpa_findings))

    if (
        network_available
        and not display_findings
        and not spend_no_results_findings
        and not analysis["network_zero_conversion"]
        and not cpa_inefficient
        and not network_inefficient
        and not cpa_findings
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
            f"El detalle y la inversión adicional estimada están en el **punto 4**."
        )
        lines.append(f"")

    return "\n".join(lines)



def generate_budget_visibility_insight(
    opportunities: list[dict],
    budget_data_available: bool = True,
) -> str:
    """Pregunta 4: ¿Qué campañas pierden visibilidad por límite de presupuesto?

    Solo usa la cuota de impresiones perdida por presupuesto (`lost_is_budget`) y
    estima la inversión adicional necesaria para recuperar esas impresiones. No
    considera pérdida por ranking ni cuota de la parte superior.
    """

    lines = [
        "**Cuota de impresiones perdida por presupuesto**",
        "",
    ]

    if not budget_data_available:
        lines.append(
            "⚠️ **No se puede medir la cuota perdida:** el reporte no incluye la "
            "columna de cuota de impresiones perdida por presupuesto "
            "(`lost_is_budget`). Pedile al proveedor que la incluya."
        )
        return "\n".join(lines)

    if not opportunities:
        lines.append(
            "✅ No se identificaron campañas limitadas por presupuesto "
            f"(cuota perdida ≥ {format_percentage(WASTE_LOST_IS_BUDGET_THRESHOLD)})."
        )
        return "\n".join(lines)

    ordered = sorted(
        opportunities,
        key=lambda row: row["lost_share"],
        reverse=True,
    )
    total_spend = sum(row["spend"] for row in ordered)
    total_upside = sum(row["estimated_upside"] for row in ordered)
    count = len(ordered)
    noun = "campaña" if count == 1 else "campañas"
    verb = "pierde" if count == 1 else "pierden"

    lines.append(
        f"Se detectaron **{count} {noun}** que {verb} impresiones por límite de "
        f"presupuesto (cuota perdida ≥ "
        f"{format_percentage(WASTE_LOST_IS_BUDGET_THRESHOLD)})."
    )
    lines.append("")
    lines.append(
        "| Campaña | Cuota de impresiones perdida por presupuesto | "
        "Inversión actual | Inversión adicional estimada |"
    )
    lines.append("| --- | --- | --- | --- |")
    for row in ordered:
        lines.append(
            f"| **{row['campaign']}** | {format_percentage(row['lost_share'])} | "
            f"{format_currency(row['spend'])} | "
            f"{format_currency(row['estimated_upside'])} |"
        )
    lines.append("")
    lines.append(
        f"Total invertido por estas campañas: **{format_currency(total_spend)}**. "
        f"Inversión adicional estimada en conjunto: **{format_currency(total_upside)}**."
    )
    lines.append("")
    lines.append("**Qué es la cuota perdida**")
    lines.append("")
    lines.append(
        "Es el porcentaje de impresiones que la campaña podría haber recibido y no "
        "recibió porque se quedó sin presupuesto. Se mide sobre las impresiones, "
        "no sobre el dinero: no es un porcentaje de la inversión ni plata ya gastada."
    )
    lines.append("")
    lines.append("**Qué es la inversión adicional estimada**")
    lines.append("")
    lines.append(
        "Es cuánto habría que invertir de más para capturar esas impresiones "
        "perdidas, suponiendo que el costo por impresión se mantiene igual. "
        "Responde a \"cuánto falta invertir\", no a \"cuánto se invirtió de más\": "
        "no es plata perdida, no es plata ya gastada y tampoco es una orden de "
        "inversión. Antes de ejecutarla hay que validar capacidad, objetivos y "
        "eficiencia."
    )
    lines.append("")
    lines.append("**Cómo se calcula**")
    lines.append("")
    lines.append("```text")
    lines.append("inversión adicional = inversión actual × cuota perdida / (1 − cuota perdida)")
    lines.append("```")
    lines.append("")
    lines.append(
        "La lógica: si la campaña ya invierte lo suficiente para cubrir "
        "`1 − cuota perdida` de las impresiones posibles, para cubrir el 100% "
        "hace falta multiplicar la inversión por `1 / (1 − cuota perdida)`. "
        "La diferencia contra la inversión actual es la inversión adicional."
    )
    lines.append("")
    lines.append(
        "**Ejemplo:** una campaña con **USD 1.000** de inversión y **50%** de "
        "cuota perdida necesita `1.000 × 0,50 / (1 − 0,50)` = **USD 1.000** "
        "adicionales para duplicar sus impresiones."
    )
    lines.append("")
    lines.append(
        "La cuota perdida se toma como promedio ponderado por impresiones y se "
        "limita a **90%**, porque al 100% la fórmula no tendría tope. El cálculo "
        "asume que el costo por impresión no cambia al invertir más."
    )

    return "\n".join(lines)


def _signed_percentage(value: float) -> str:
    """Formatea una fracción como porcentaje con signo explícito."""

    if value is None or pd.isna(value):
        return "—"
    pct = float(value) * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%".replace(".", ",")


def _rate_text(value) -> str:
    """Formatea una tasa. Usa dos decimales cuando el valor es menor a 1%."""

    if value is None or pd.isna(value):
        return "—"
    pct = float(value) * 100 if abs(value) <= 1 else float(value)
    decimals = 2 if abs(pct) < 1 else 1
    return f"{pct:.{decimals}f}%".replace(".", ",")


P5_MAX_ROWS = 3


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _conversions_text(value: float) -> str:
    """Formatea conversiones: sin decimales si son enteras."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    decimals = 0 if number.is_integer() else 1
    return format_number(number, decimals=decimals)


def _campaign_row_text(row: dict) -> str:
    """Fila de la tabla de clics vs conversiones."""

    return (
        f"| **{row['campaign']}** | {format_number(row['clicks'])} | "
        f"{_conversions_text(row['conversions'])} | {_rate_text(row['cvr'])} |"
    )


def _remaining_campaigns_text(rows: list[dict]) -> str:
    """Nota con las campañas que no entraron en la tabla."""

    shown = rows[:P5_MAX_ROWS]
    detail = ", ".join(
        f"{row['campaign']} ({_rate_text(row['cvr'])})" for row in shown
    )
    extra = len(rows) - len(shown)
    more = f" y {extra} más" if extra > 0 else ""
    return (
        f"*{len(rows)} {_plural(len(rows), 'campaña', 'campañas')} más "
        f"con el mismo patrón: {detail}{more}.*"
    )


def analyze_clicks_vs_conversions(
    df_campaign: pd.DataFrame | None,
    eligibility_df: pd.DataFrame | None = None,
) -> dict:
    """Compara la tasa de conversión de cada campaña contra el promedio de la cuenta.

    La pregunta 5 no usa un benchmark externo: el promedio de la cuenta es la
    referencia. Una campaña por debajo atrae clics que no se convierten; una
    campaña por encima convierte más de lo que su tráfico haría esperar.
    """

    empty = {
        "total_clicks": 0.0,
        "total_conversions": 0.0,
        "account_cvr": None,
        "click_sinks": [],
        "efficient_low_traffic": [],
        "excluded": 0,
        "campaigns": 0,
    }

    if df_campaign is None or df_campaign.empty:
        return empty
    if "campaign" not in df_campaign.columns or "clicks" not in df_campaign.columns:
        return empty

    df = df_campaign.copy()
    df["clicks"] = pd.to_numeric(df["clicks"], errors="coerce").fillna(0.0)
    if "conversions" in df.columns:
        df["conversions"] = pd.to_numeric(
            df["conversions"], errors="coerce"
        ).fillna(0.0)
    else:
        df["conversions"] = 0.0

    mask = df["clicks"] >= MIN_CLICKS_FOR_ANALYSIS
    if eligibility_df is not None and "is_eligible" in eligibility_df.columns:
        eligible = set(
            eligibility_df.loc[
                eligibility_df["is_eligible"].astype(bool), "campaign"
            ]
        )
        mask = mask & df["campaign"].isin(eligible)

    analyzed = df[mask]
    excluded = int(len(df) - len(analyzed))
    if analyzed.empty:
        empty["excluded"] = excluded
        return empty

    total_clicks = float(analyzed["clicks"].sum())
    total_conversions = float(analyzed["conversions"].sum())
    if total_clicks <= 0:
        empty["excluded"] = excluded
        return empty

    account_cvr = total_conversions / total_clicks

    campaigns = []
    for _, row in analyzed.iterrows():
        clicks = float(row["clicks"])
        conversions = float(row["conversions"])
        campaigns.append({
            "campaign": row["campaign"],
            "clicks": clicks,
            "conversions": conversions,
            "cvr": conversions / clicks if clicks > 0 else 0.0,
        })

    click_sinks = sorted(
        [c for c in campaigns if c["cvr"] < account_cvr],
        key=lambda campaign: campaign["clicks"],
        reverse=True,
    )
    efficient = sorted(
        [c for c in campaigns if c["cvr"] > account_cvr],
        key=lambda campaign: campaign["cvr"],
        reverse=True,
    )

    return {
        "total_clicks": total_clicks,
        "total_conversions": total_conversions,
        "account_cvr": account_cvr,
        "click_sinks": click_sinks,
        "efficient_low_traffic": efficient,
        "excluded": excluded,
        "campaigns": len(campaigns),
    }


def _omitted_campaigns_text(excluded: int) -> str:
    return (
        f"Se omitieron **{excluded}** "
        f"{_plural(excluded, 'campaña', 'campañas')} con menos de "
        f"{MIN_CLICKS_FOR_ANALYSIS} clics o datos insuficientes (ver punto 6)."
    )


def generate_clicks_vs_conversions_insight(
    df_campaign: pd.DataFrame | None = None,
    eligibility_df: pd.DataFrame | None = None,
    analysis: dict | None = None,
) -> str:
    """Pregunta 5: ¿Qué campañas atraen clics pero no logran conversiones (o al revés)?

    La referencia es el promedio de la cuenta, no un benchmark. Se muestran como
    máximo tres campañas por lado; el resto se resume en una nota.
    """

    if analysis is None:
        analysis = analyze_clicks_vs_conversions(df_campaign, eligibility_df)

    lines = ["**Clics vs conversiones**", ""]
    total_clicks = analysis["total_clicks"]
    total_conversions = analysis["total_conversions"]
    account_cvr = analysis["account_cvr"]
    excluded = analysis["excluded"]

    if not analysis["campaigns"]:
        lines.append(
            f"No hay campañas con al menos **{MIN_CLICKS_FOR_ANALYSIS} clics** "
            "y datos suficientes para comparar."
        )
        if excluded:
            lines.append("")
            lines.append(_omitted_campaigns_text(excluded))
        return "\n".join(lines)

    if not account_cvr:
        lines.append(
            f"Se registraron **{format_number(total_clicks)} clics** pero "
            "**ninguna conversión** en el período, así que no hay una tasa "
            "promedio con la cual comparar."
        )
        lines.append("")
        lines.append(
            "Antes de cambiar campañas, revisar que el registro de conversiones "
            "esté funcionando."
        )
        return "\n".join(lines)

    lines.append(
        f"La cuenta completa convierte **{_rate_text(account_cvr)}** de los "
        f"clics: **{_conversions_text(total_conversions)} "
        f"{_plural(int(total_conversions), 'conversión', 'conversiones')}** "
        f"sobre **{format_number(total_clicks)} clics**. Ese es el promedio "
        "contra el que se mide cada campaña."
    )
    lines.append("")

    click_sinks = analysis["click_sinks"]
    efficient = analysis["efficient_low_traffic"]

    if not click_sinks and not efficient:
        lines.append(
            "✅ Todas las campañas con volumen suficiente convierten en línea "
            "con el promedio de la cuenta."
        )
        if excluded:
            lines.append("")
            lines.append(_omitted_campaigns_text(excluded))
        return "\n".join(lines)

    if click_sinks:
        lines.append(
            "🔴 **Atraen clics, pero convierten por debajo del promedio** "
            "(candidatas a revisar segmentación, oferta o landing)"
        )
        lines.append("")
        lines.append("| Campaña | Clics | Conversiones | Tasa de conversión |")
        lines.append("| --- | --- | --- | --- |")
        for row in click_sinks[:P5_MAX_ROWS]:
            lines.append(_campaign_row_text(row))
        lines.append("")
        if len(click_sinks) > P5_MAX_ROWS:
            lines.append(_remaining_campaigns_text(click_sinks[P5_MAX_ROWS:]))
            lines.append("")

    if efficient:
        lines.append(
            "🟢 **Convierten por encima del promedio** "
            "(candidatas a recibir más presupuesto)"
        )
        lines.append("")
        lines.append("| Campaña | Clics | Conversiones | Tasa de conversión |")
        lines.append("| --- | --- | --- | --- |")
        for row in efficient[:P5_MAX_ROWS]:
            lines.append(_campaign_row_text(row))
        lines.append("")
        if len(efficient) > P5_MAX_ROWS:
            lines.append(_remaining_campaigns_text(efficient[P5_MAX_ROWS:]))
            lines.append("")

    if excluded:
        lines.append(_omitted_campaigns_text(excluded))
        lines.append("")

    lines.append(
        "**Tasa de conversión** = conversiones ÷ clics. El promedio de la "
        f"cuenta es **{_rate_text(account_cvr)}**: por debajo, la campaña "
        "recibe clics que no se convierten; por encima, convierte mejor de lo "
        "esperado para el tráfico que recibe."
    )

    return "\n".join(lines)


def _cpa_vs_reference_rows(
    df_campaign: pd.DataFrame,
    cpa_findings: list,
) -> list[dict]:
    """Arma filas de CPA actual vs la referencia usada por el diagnóstico."""

    benchmark_by_campaign = {f.campaign: f for f in cpa_findings}
    rows = []

    for campaign, finding in benchmark_by_campaign.items():
        campaign_rows = df_campaign[df_campaign["campaign"] == campaign]
        row = campaign_rows.iloc[0] if not campaign_rows.empty else None

        actual_cpa = None
        if row is not None and "cpa" in row.index and pd.notna(row["cpa"]):
            actual_cpa = float(row["cpa"])
        if actual_cpa is None and finding.metric_value is not None:
            actual_cpa = float(finding.metric_value)

        reference = finding.benchmark_value
        variation = finding.variation_pct
        if variation is None and actual_cpa is not None and reference:
            variation = (actual_cpa - reference) / reference

        conversions = None
        spend = None
        if row is not None:
            if "conversions" in row.index and pd.notna(row["conversions"]):
                conversions = float(row["conversions"])
            if "spend_usd" in row.index and pd.notna(row["spend_usd"]):
                spend = float(row["spend_usd"])

        rows.append({
            "campaign": campaign,
            "cpa": actual_cpa,
            "reference": reference,
            "variation": variation,
            "conversions": conversions,
            "spend": spend,
        })

    rows.sort(
        key=lambda item: item["cpa"] if item["cpa"] is not None else -1,
        reverse=True,
    )
    return rows


def _cpa_vs_reference_lines(
    df_campaign: pd.DataFrame,
    cpa_findings: list,
) -> list[str]:
    """Tabla de CPA vs objetivo/benchmark para el punto 3."""

    rows = _cpa_vs_reference_rows(df_campaign, cpa_findings)
    if not rows:
        return []

    lines = [
        "🟡 **CPA vs objetivo/benchmark**",
        "",
        "| Campaña | CPA actual | Referencia | Variación | Conversiones | Inversión |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        lines.append(
            f"| **{item['campaign']}** | {format_currency(item['cpa'])} | "
            f"{format_currency(item['reference'])} | "
            f"{_signed_percentage(item['variation'])} | "
            f"{format_number(item['conversions'])} | "
            f"{format_currency(item['spend'])} |"
        )
    lines.append("")
    return lines


def generate_insufficient_data_insight(
    eligibility_df: pd.DataFrame,
) -> str:
    """Pregunta 6: ¿Qué campañas tienen tan pocos datos que conviene esperar?"""

    lines = [
        "**Campañas con datos insuficientes**",
        "",
    ]

    status_labels = {
        "insufficient_history": "Historial insuficiente",
        "insufficient_volume": "Volumen insuficiente",
    }
    pending = eligibility_df[
        eligibility_df["eligibility_status"].isin(list(status_labels))
    ].copy()

    if pending.empty:
        lines.append(
            "✅ Todas las campañas tienen historial y volumen suficiente para análisis."
        )
        return "\n".join(lines)

    if "spend_usd" in pending.columns:
        pending = pending.sort_values("spend_usd", ascending=False)

    lines.append("| Campaña | Estado | Días activos | Clics | Inversión |")
    lines.append("| --- | --- | --- | --- | --- |")
    for _, row in pending.iterrows():
        status = status_labels.get(row["eligibility_status"], row["eligibility_status"])
        active_days = row.get("active_days", "—")
        if pd.isna(active_days):
            active_days = "—"
        clicks = row.get("clicks", None)
        spend = row.get("spend_usd", None)
        lines.append(
            f"| **{row['campaign']}** | {status} | {active_days} | "
            f"{format_number(clicks)} | {format_currency(spend)} |"
        )

    return "\n".join(lines)


def _finding_text(finding) -> str:
    """Texto del hallazgo sin el nombre de la campaña (evita falsos positivos)."""

    text = " ".join(
        str(getattr(finding, attribute, "") or "")
        for attribute in ("rule_id", "rule_name", "message")
    ).lower()

    campaign = str(getattr(finding, "campaign", "") or "").lower()
    if campaign:
        # El mensaje suele citar el nombre entre comillas; se quita solo esa
        # mención para no alterar el resto del texto.
        text = text.replace(f"'{campaign}'", " ")
        text = text.replace(f"\"{campaign}\"", " ")

    return text


def _action_for_finding(finding) -> str:
    """Sugiere una acción concreta según el tipo de hallazgo."""

    text = _finding_text(finding)

    if "display" in text or "red de display" in text:
        return "Desactivar Red de Display"
    if (
        "sin clic" in text
        or "ni un solo clic" in text
        or "sin convers" in text
        or "0 conversiones" in text
        or "spend_no" in text
    ):
        return "Pausar y revisar configuración/tracking"
    if "cpa" in text:
        return "Revisar pujas y segmentación"
    if "cpc" in text:
        return "Revisar competencia y pujas"
    if "ctr" in text:
        return "Revisar anuncios y palabras clave"
    if "conversion" in text or "tasa" in text:
        return "Revisar landing page y tracking"
    if (
        "impression" in text
        or "impres" in text
        or "visibilidad" in text
        or "presupuesto" in text
    ):
        return "Revisar presupuesto y ranking"
    if "pareto" in text or "concentra" in text:
        return "Revisar distribución de presupuesto"
    return "Revisar campaña"


_FINDING_RATE_METRICS = {"ctr", "conversion_rate", "impression_share"}
_FINDING_MONEY_METRICS = {"cpc", "cpa", "spend"}


def _finding_metric_key(finding) -> str:
    """Identifica la métrica del hallazgo a partir de su texto."""

    text = _finding_text(finding)

    if "display" in text:
        return "config"
    if "spend_no" in text or "gastó" in text or "spend_usd" in text:
        return "spend"
    if (
        "conversion_rate" in text
        or "conv_rate" in text
        or "tasa de conversión" in text
    ):
        return "conversion_rate"
    if "conversions" in text or "conversión" in text or "conversiones" in text:
        return "conversions"
    if (
        "impression_share" in text
        or "impr_share" in text
        or "lost_is" in text
        or "cuota de impresiones" in text
        or "visibilidad" in text
        or "presupuesto insuficiente" in text
    ):
        return "impression_share"
    if "ctr" in text:
        return "ctr"
    if "cpc" in text:
        return "cpc"
    if "cpa" in text:
        return "cpa"
    return "unknown"


def _finding_label(finding, metric_key: str) -> str:
    """Etiqueta corta y accionable para la columna Hallazgo."""

    text = _finding_text(finding)

    if metric_key == "config":
        return "Display activo"
    if metric_key == "spend":
        if "convers" in text:
            return "Gasto sin conversiones"
        if "clic" in text:
            return "Gasto sin clics"
        return "Inversión atípica"
    if metric_key == "ctr":
        if "low" in text or "bajó" in text or "por debajo" in text:
            return "CTR bajo"
        return "CTR alto"
    if metric_key == "cpc":
        return "CPC alto"
    if metric_key == "cpa":
        return "CPA alto"
    if metric_key == "conversion_rate":
        return "Tasa de conversión baja"
    if metric_key == "conversions":
        return "Menos conversiones"
    if metric_key == "impression_share":
        if "presupuesto" in text:
            return "Presupuesto insuficiente"
        return "Menos visibilidad"
    return "Hallazgo"


def _finding_metric_values(finding) -> dict:
    values = getattr(finding, "metric_values", None)
    return values if isinstance(values, dict) else {}


def _format_finding_value(value, metric_key: str) -> str:
    """Formatea el valor de una métrica según su tipo."""

    if value is None or pd.isna(value):
        return "—"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "—"

    if metric_key in _FINDING_RATE_METRICS:
        return format_percentage(numeric)
    if metric_key in _FINDING_MONEY_METRICS:
        return format_currency(numeric)
    if metric_key == "conversions":
        return _conversions_text(numeric)
    return format_number(numeric, decimals=2)


def generate_top_findings_summary(
    scored_findings: list,
) -> str:
    """Pregunta 7: plan de acción con los hallazgos priorizados."""

    lines = [
        "**🎯 Plan de acción priorizado**",
        "",
    ]

    if not scored_findings:
        lines.append("✅ No se generaron hallazgos prioritarios en esta corrida.")
        return "\n".join(lines)

    severity_icons = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }

    lines.append(
        "Estas son las acciones con mayor impacto, ordenadas por prioridad. "
        "El nombre de la campaña aparece una sola vez y el detalle se separa "
        "en valor real, referencia y variación."
    )
    lines.append("")
    lines.append("**Cómo se asigna la severidad**")
    lines.append("")
    lines.append(
        "- 🔴 **Crítico:** gasto sin clics o sin conversiones (desperdicio confirmado)."
    )
    lines.append(
        "- 🟠 **Alto:** desvío negativo extremo contra la referencia "
        "(más del doble del umbral)."
    )
    lines.append(
        "- 🟡 **Medio:** desvío negativo persistente por encima del umbral."
    )
    lines.append(
        "- 🟢 **Bajo:** comportamiento atípico contra el promedio de la cuenta "
        "(informativo)."
    )
    lines.append("")
    lines.append(
        "Los hallazgos que describen una mejora (CTR o tasa de conversión por "
        "encima de la referencia, CPA o CPC por debajo) no se incluyen: no "
        "requieren acción."
    )
    lines.append("")
    lines.append(
        "| # | Severidad | Campaña | Hallazgo | Real | Referencia | "
        "Variación | Acción |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")

    ordered = sorted(
        scored_findings,
        key=lambda finding: finding.total_score,
        reverse=True,
    )
    for index, finding in enumerate(ordered, 1):
        severity = finding.severity
        severity_key = getattr(severity, "value", severity)
        icon = severity_icons.get(str(severity_key), "⚪")

        metric_key = _finding_metric_key(finding)
        values = _finding_metric_values(finding)
        current = values.get("current_value")
        benchmark = values.get("benchmark_value")
        variation = values.get("variation_pct")

        if metric_key == "config":
            real_text = "—"
            reference_text = "—"
        else:
            real_text = _format_finding_value(current, metric_key)
            reference_text = _format_finding_value(benchmark, metric_key)

        variation_text = (
            _signed_percentage(variation)
            if benchmark is not None and variation is not None
            else "—"
        )

        lines.append(
            f"| {index} | {icon} | **{finding.campaign}** | "
            f"{_finding_label(finding, metric_key)} | {real_text} | "
            f"{reference_text} | {variation_text} | "
            f"{_action_for_finding(finding)} |"
        )

    lines.append("")
    lines.append(
        "**Cómo leer:** *Real* es el valor actual de la campaña; *Referencia* "
        "es el benchmark u objetivo; *Variación* es el desvío porcentual de Real "
        "contra Referencia. Si no hay referencia disponible, se muestra —."
    )

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
    benchmark_source: str | None = None,
    benchmark_targets: dict | None = None,
) -> list[CampaignInsight]:
    """
    Construye el reporte completo respondiendo las 7 preguntas del roadmap.
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
    cpa_findings = [f for f in benchmark_findings if "cpa" in f.rule_id.lower()]
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
    elif inefficiency or cpa_findings or not low_volume_flagged.empty:
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
            cpa_findings=cpa_findings,
        ),
        supporting_data={
            "display_findings": display_findings,
            "spend_no_results": spend_no_results,
            "network_zero_conversion": waste_analysis["network_zero_conversion"],
            "cpa_inefficient": waste_analysis["cpa_inefficient"],
            "network_inefficient": waste_analysis["network_inefficient"],
            "cpa_findings": cpa_findings,
            "budget_opportunities": waste_analysis["budget_opportunities"],
            "median_cpa": waste_analysis["median_cpa"],
        },
        chart_type="network_breakdown",
    ))

    # Pregunta 4: presupuesto y visibilidad (fusión de los antiguos puntos 4 y 5)
    budget_opportunities = waste_analysis["budget_opportunities"]
    insights.append(CampaignInsight(
        question_number=4,
        question="¿Qué campañas pierden visibilidad por límite de presupuesto?",
        title="Cuota de impresiones perdida por presupuesto",
        status="ok" if budget_opportunities else "info",
        answer=generate_budget_visibility_insight(
            budget_opportunities,
            budget_data_available=waste_analysis["budget_data_available"],
        ),
        supporting_data={
            "budget_opportunities": budget_opportunities,
        },
        chart_type=None,
    ))

    # Pregunta 5
    clicks_analysis = analyze_clicks_vs_conversions(df_campaign, eligibility_df)
    click_sinks = clicks_analysis["click_sinks"]
    efficient_campaigns = clicks_analysis["efficient_low_traffic"]
    insights.append(CampaignInsight(
        question_number=5,
        question="¿Qué campañas atraen clics pero no logran conversiones (o al revés)?",
        title="Clics que no se convierten (y viceversa)",
        status=(
            "warning"
            if click_sinks
            else ("info" if efficient_campaigns else "ok")
        ),
        answer=generate_clicks_vs_conversions_insight(analysis=clicks_analysis),
        supporting_data={
            "account_cvr": clicks_analysis["account_cvr"],
            "click_sinks": click_sinks,
            "efficient_low_traffic": efficient_campaigns,
        },
        chart_type="ctr_vs_cvr_matrix",
    ))

    # Pregunta 6 (antes 7)
    insufficient_count = len(
        eligibility_df[eligibility_df["eligibility_status"].isin(["insufficient_volume", "insufficient_history"])]
    )
    insights.append(CampaignInsight(
        question_number=6,
        question="¿Qué campañas tienen tan pocos datos que conviene esperar antes de sacar conclusiones?",
        title="Campañas con pocos datos: esperar antes de decidir",
        status="warning" if insufficient_count else "ok",
        answer=generate_insufficient_data_insight(eligibility_df),
        supporting_data={"eligibility_summary": eligibility_df["eligibility_status"].value_counts().to_dict()},
        chart_type=None,
    ))

    # Pregunta 7 (antes 8)
    insights.append(CampaignInsight(
        question_number=7,
        question="¿Qué acciones conviene priorizar esta semana?",
        title="Plan de acción priorizado",
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
    Estructura obligatoria siguiendo las 7 preguntas del roadmap.
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

    def insight_by_number(number):
        for ins in insights:
            if getattr(ins, "question_number", None) == number:
                return ins
        return None

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

    # 4. PRESUPUESTO Y VISIBILIDAD (fusión de los antiguos 4 y 5)
    budget_vis = insight_by_number(4)
    sections.append(
        f"**4. PRESUPUESTO Y VISIBILIDAD**: "
        f"{extract_msg([budget_vis]) if budget_vis else 'Sin campañas limitadas por presupuesto'}"
    )

    # 5. CLICS VS CONVERSIONES
    clicks_conv = insight_by_number(5)
    if clicks_conv:
        data = getattr(clicks_conv, "supporting_data", {}) or {}
        sinks = len(data.get("click_sinks") or [])
        efficient = len(data.get("efficient_low_traffic") or [])
        account_cvr = data.get("account_cvr")
        parts = []
        if account_cvr is not None:
            parts.append(f"promedio de la cuenta {_rate_text(account_cvr)}")
        if sinks:
            parts.append(
                f"{sinks} {'campaña' if sinks == 1 else 'campañas'} "
                "por debajo del promedio"
            )
        if efficient:
            parts.append(
                f"{efficient} {'campaña' if efficient == 1 else 'campañas'} "
                "por encima del promedio"
            )
        detail = "; ".join(parts) or "sin desbalances claros"
        sections.append(f"**5. CLICS VS CONV**: {detail}")
    else:
        sections.append("**5. CLICS VS CONV**: sin datos suficientes")

    # 6. DATOS INSUFICIENTES
    insuff = insight_by_number(6)
    sections.append(
        f"**6. DATOS INSUFICIENTES**: {extract_msg([insuff]) if insuff else 'Todas con datos suficientes'}"
    )

    # 7. PLAN DE ACCIÓN
    if scored_findings:
        findings_text = []
        for i, f in enumerate(scored_findings[:5], 1):
            outlier = " ⚡" if getattr(f, "is_outlier", False) else ""
            findings_text.append(
                f"{i}. {f.rule_name} ({f.campaign}){outlier}: {f.message[:120]}"
            )
        sections.append(
            "**7. PLAN DE ACCIÓN**:\n" + "\n".join(findings_text)
        )
    else:
        top_h = find_insights(["plan de acción", "hallazg", "relevant"])
        sections.append(
            f"**7. PLAN DE ACCIÓN**: {extract_msg(top_h) if top_h else 'Ver lista completa'}"
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
    benchmark_source: str | None = None,
    benchmark_targets: dict | None = None,
) -> tuple[list[CampaignInsight], Optional[str]]:
    """
    Construye reporte completo + narrativa ejecutiva opcional con LLM (Groq).
    Retorna (insights, llm_narrative_or_none).
    """
    # 1. Reporte base (7 preguntas)
    insights = build_full_report(
        df_campaign, df_daily, eligibility_df,
        diagnostics_findings, outlier_findings,
        pareto_analysis, scored_findings, currency_info,
        benchmark_source=benchmark_source,
        benchmark_targets=benchmark_targets,
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