import streamlit as st
import altair as alt
import os
import pandas as pd
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

from src.analysis import (
    build_campaign_pareto,
    build_daily_performance,
    top_campaigns_by_spend,
)
from src.sources import available_sources
from src.pipeline import run_ingestion_pipeline
from src.presentation import (
    format_currency,
    format_integer,
    format_percentage,
    to_display_frame,
)
from src.elegibility import evaluate_eligibility, get_eligible_campaigns, get_eligibility_summary
from src.diagnostics import run_diagnostics, calculate_benchmark, build_persistence_tracker
from src.outliers import run_outlier_detection
from src.pareto import analyze_pareto_concentration
from src.scoring import prioritize_findings
from src.reporting import build_full_report, format_report_markdown, build_enhanced_report


st.set_page_config(
    page_title="Miau",
    layout="wide"
)


# --- SELECCIÓN DE PLATAFORMA Y UPLOAD EN SIDEBAR (colapsible nativo ☰) ---
with st.sidebar:
    sources = available_sources()
    source_id = st.selectbox(
        "Plataforma",
        options=list(sources),
        format_func=lambda value: sources[value].label,
    )
    source = sources[source_id]

    uploaded_file = st.file_uploader(
        "Cargá un reporte",
        type=[extension.lstrip(".") for extension in source.extensions],
        help="El formato y las columnas se interpretan según la fuente seleccionada.",
    )

    if uploaded_file is None:
        st.divider()
        st.caption("Los objetivos y opciones avanzadas se habilitan cuando cargues un archivo.")
    else:
        st.divider()
        st.subheader("🎯 Objetivos de performance")
        st.caption(
            "✍️ Poné acá las metas que te pasó tu supervisor o las que definiste "
            "con el cliente. La app las usa para avisarte cuando algo se sale del "
            "plan. Los valores precargados son **un ejemplo básico**: editalos con tus "
            "metas reales. Si una métrica no tiene objetivo, ponela en 0."
        )
        target_ctr = st.number_input("CTR objetivo (%)", min_value=0.0, value=2.0, step=0.1, format="%.2f", help="Porcentaje de clics sobre impresiones que querés lograr. Ejemplo: 2%.") / 100
        target_cpc = st.number_input("CPC objetivo (USD)", min_value=0.0, value=0.50, step=0.01, format="%.2f", help="Cuánto querés pagar como máximo por cada clic. Ejemplo: USD 0,50.")
        target_cpa = st.number_input("CPA objetivo (USD)", min_value=0.0, value=10.0, step=0.01, format="%.2f", help="Cuánto querés pagar como máximo por cada conversión. Ejemplo: USD 10.")
        target_cvr = st.number_input("Tasa de conversión objetivo (%)", min_value=0.0, value=5.0, step=0.1, format="%.2f", help="Porcentaje de clics que querés que terminen en conversión. Ejemplo: 5%.") / 100
        targets = {
            "ctr": target_ctr or None,
            "cpc": target_cpc or None,
            "cpa": target_cpa or None,
            "conversion_rate": target_cvr or None,
        }

        st.info(
            "ℹ️ **¿Para qué sirve esto?**\n\n"
            "- Los objetivos que cargás son tu **norte**: la app compara lo real contra lo que te propusiste.\n"
            "- Si el CPC o el CPA se pasan de tu objetivo, te va a saltar una alerta. Si el CTR o la tasa de conversión caen, también.\n"
            "- En la pestaña **Insights** vas a ver una tablita que resume: cuánto venís, cuánto querés y cuánto te falta (o te sobra).\n\n"
            "💡 **Tip:** si no tenés un objetivo para alguna métrica, dejala en 0 y la app la ignora. "
            "Cambiá los números y todo se actualiza solo, no hace falta recargar."
        )

suffix = None
if uploaded_file is not None:
    suffix = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()

st.title("Miau")

st.caption("**M**arketing **I**ntelligence & **A**utomated **U**nderstanding")

if uploaded_file is None:
    st.write(
        "Motor de análisis automatizado de campañas que orienta y alinea al equipo de paid media."
    )
    st.info(
        "👋 **¿Qué vas a encontrar acá?** Subí el reporte de tus campañas y la app te muestra de un vistazo: KPIs generales, performance por campaña, evolución diaria, gráficos de inversión y eficiencia, y alertas automáticas contra tus objetivos.\n\n"
        "🧭 **¿Para qué sirve?** Miau es una **guía**: te orienta, prioriza los hallazgos y alinea a todo el equipo sobre dónde poner foco. No toma decisiones por vos — los cambios finales y la implementación en las plataformas los hacés vos con tu criterio y contexto de negocio."
    )
    st.info("Subí un archivo CSV o Excel para comenzar el análisis.")
    st.stop()

try:
    with NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        temporary_file.write(uploaded_file.getbuffer())
        temporary_path = temporary_file.name

    result = run_ingestion_pipeline(temporary_path, source=source_id)
except (ValueError, FileNotFoundError) as error:
    st.error(str(error))
    st.stop()
finally:
    if "temporary_path" in locals() and os.path.exists(temporary_path):
        os.unlink(temporary_path)

# 🤖 Resumen Ejecutivo con IA (después de carga, antes de KPIs)
st.subheader("🤖 Resumen Ejecutivo con IA")
use_llm = st.checkbox(
    "Generar resumen ejecutivo con IA (Groq)",
    value=False,
    help="Usa Groq (cloud, gratis, rápido). Requiere GROQ_API_KEY en .env o Secrets."
)
api_key = None
if use_llm:
    # Prioridad: 1) Streamlit Secrets (producción) 2) .env (local)
    secrets_key = ""
    try:
        secrets_key = st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        pass
    env_key = os.getenv("GROQ_API_KEY", "")
    
    if secrets_key:
        api_key = secrets_key
        st.success("✅ API key configurada (Secrets)")
    elif env_key:
        api_key = env_key
        st.success("✅ API key configurada (.env)")
    else:
        st.error("❌ Falta GROQ_API_KEY. Agregala a .env local o Secrets en producción.")
        use_llm = False

st.divider()

daily = result["daily"]
campaign = result["campaign"]

# --- DIAGNOSTIC PIPELINE ---
# 1. Elegibilidad
eligibility_df = evaluate_eligibility(campaign, daily)
eligible_campaigns = get_eligible_campaigns(campaign, daily)["campaign"].tolist()

# 2. Benchmark: los objetivos editados reemplazan al benchmark histórico.
df_benchmark = None
active_targets = {metric: value for metric, value in targets.items() if value is not None}
if active_targets:
    df_benchmark = pd.DataFrame(
        [
            {"campaign": camp, "metric": metric, "benchmark_value": value}
            for camp in campaign["campaign"].unique()
            for metric, value in active_targets.items()
        ]
    )
elif len(daily) > 1:
    df_benchmark = calculate_benchmark(daily)
persistence_df = build_persistence_tracker(daily, df_benchmark) if df_benchmark is not None else None

# 3. Diagnósticos
diagnostics_findings = run_diagnostics(
    campaign, daily, daily, df_benchmark, persistence_df
)

# 4. Outliers
outlier_findings = run_outlier_detection(
    campaign, daily, df_benchmark, eligible_campaigns=eligible_campaigns
)

# 5. Pareto
pareto_analysis = analyze_pareto_concentration(campaign)

# 6. Scoring y priorización
all_findings = diagnostics_findings + outlier_findings
scored_findings = prioritize_findings(all_findings, campaign, max_findings=5)

# 7. Reporte completo (con LLM opcional)
insights, llm_narrative = build_enhanced_report(
    campaign, daily, eligibility_df,
    diagnostics_findings, outlier_findings,
    pareto_analysis, scored_findings, result["currency"],
    use_llm=use_llm,
    api_key=api_key,
)

# --- KPIs GENERALES ---
total_spend = daily["spend_usd"].sum()
total_clicks = daily["clicks"].sum()
total_impressions = daily["impressions"].sum()
total_conversions = daily["conversions"].sum()

ctr = total_clicks / total_impressions if total_impressions else 0
cpa = total_spend / total_conversions if total_conversions else None
currency_info = result["currency"]

st.caption(
    f"{source.label} · {uploaded_file.name} · {format_integer(len(daily))} filas diarias · "
    f"{format_integer(len(campaign))} campañas · Valores unificados a USD"
)
st.caption(
    f"Cotización de referencia: {currency_info['provider']} · "
    f"actualizada {currency_info['updated_at'] or 'sin fecha disponible'} · "
    "las cotizaciones se consultan en cada análisis."
)

def _kpi_card(label: str, value: str, emoji: str = "") -> str:
    return f"""
    <div style="
        background-color: #ffffff;
        border: 1px solid #f1f3f5;
        border-left: 3px solid #a5d8ff;
        border-radius: 8px;
        padding: 12px 14px;
        margin-bottom: 8px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    ">
        <div style="font-size: 0.8rem; color: #adb5bd; text-transform: uppercase; letter-spacing: 0.5px;">{emoji} {label}</div>
        <div style="font-size: 1.6rem; font-weight: 600; color: #495057;">{value}</div>
    </div>
    """

kpi_columns = st.columns(5)
kpi_data = [
    ("Inversión", format_currency(total_spend), "💰"),
    ("Impresiones", format_integer(total_impressions), "👁️"),
    ("Clics", format_integer(total_clicks), "👆"),
    ("CTR", format_percentage(ctr), "📈"),
    ("CPA", format_currency(cpa), "🎯"),
]
for column, (label, value, emoji) in zip(kpi_columns, kpi_data):
    column.markdown(_kpi_card(label, value, emoji), unsafe_allow_html=True)

# --- TABS ---
tab_insights, tab_charts, tab_campaigns, tab_daily = st.tabs(
    ["🎯 Insights", "📊 Gráficos", "📋 Por campaña", "📅 Detalle diario"]
)

with tab_insights:
    st.subheader("Análisis automático - 9 preguntas clave")
    
    # Resumen de elegibilidad
    elig_summary = get_eligibility_summary(eligibility_df)
    with st.expander("📋 Elegibilidad de campañas para análisis", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total campañas", elig_summary["total_campaigns"])
        col2.metric("✅ Elegibles", elig_summary["eligible"])
        col3.metric("🟡 Volumen insuficiente", elig_summary["insufficient_volume"])
        col4.metric("🔴 Gasto sin resultados", elig_summary["spend_no_results"])
        
        st.dataframe(
            eligibility_df[["campaign", "eligibility_status", "eligibility_reason", "is_eligible"]],
            use_container_width=True,
            hide_index=True,
        )

    # Tabla Objetivos vs performance actual
    if active_targets:
        total_spend = daily["spend_usd"].sum()
        total_clicks = daily["clicks"].sum()
        total_impressions = daily["impressions"].sum()
        total_conversions = daily["conversions"].sum()
        actuals = {
            "ctr": total_clicks / total_impressions if total_impressions else None,
            "cpc": total_spend / total_clicks if total_clicks else None,
            "cpa": total_spend / total_conversions if total_conversions else None,
            "conversion_rate": total_conversions / total_clicks if total_clicks else None,
        }
        labels = {
            "ctr": "CTR",
            "cpc": "CPC (USD)",
            "cpa": "CPA (USD)",
            "conversion_rate": "Tasa de conversión",
        }
        rows = []
        for metric, target in active_targets.items():
            actual = actuals.get(metric)
            deviation = (actual - target) / target if actual is not None and target else None
            is_rate = metric in ("ctr", "conversion_rate")
            rows.append({
                "Métrica": labels[metric],
                "Real": f"{actual:.2%}" if is_rate and actual is not None else (f"{actual:,.2f}" if actual is not None else "—"),
                "Objetivo": f"{target:.2%}" if is_rate else f"{target:,.2f}",
                "Desvío vs objetivo": f"{deviation:+.1%}" if deviation is not None else "—",
            })
        comparison = pd.DataFrame(rows)
        st.subheader("🎯 Objetivos vs performance")
        st.dataframe(comparison, use_container_width=True, hide_index=True)
        st.caption("El desvío indica cuánto te alejaste de tu objetivo: positivo = por encima, negativo = por debajo.")

    # Renderizar insights (9 preguntas)
    for insight in insights:
        with st.container():
            st.markdown(f"### {insight.question_number}. {insight.question}")
            st.markdown(insight.answer)
            st.divider()

    # Botón descargar reporte completo
    markdown_report = format_report_markdown(insights)
    st.download_button(
        "📥 Descargar reporte completo (Markdown)",
        markdown_report.encode("utf-8"),
        file_name="reporte_miau.md",
        mime="text/markdown",
    )

with tab_charts:
    st.subheader("Evolución de performance")
    daily_trend = build_daily_performance(daily)

    chart_options = {
        "Inversión en USD": ("spend_usd", ",.2f"),
        "Clics": ("clicks", ",.0f"),
        "Conversiones": ("conversions", ",.2f"),
        "CTR": ("ctr", ".1%"),
        "CPA en USD": ("cpa", ",.2f"),
    }
    selected_chart = st.selectbox(
        "Métrica temporal",
        options=list(chart_options),
        key="daily_chart_metric",
    )
    metric_column, number_format = chart_options[selected_chart]

    trend_chart = (
        alt.Chart(daily_trend)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="Fecha"),
            y=alt.Y(
                f"{metric_column}:Q",
                title=selected_chart,
                axis=alt.Axis(format=number_format),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Fecha", format="%d/%m/%Y"),
                alt.Tooltip(
                    f"{metric_column}:Q",
                    title=selected_chart,
                    format=number_format,
                ),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(trend_chart, use_container_width=True)

    ranking_column, scatter_column = st.columns(2)
    with ranking_column:
        st.subheader("Top 10 campañas por inversión")
        top_campaigns = top_campaigns_by_spend(campaign)
        ranking_chart = (
            alt.Chart(top_campaigns)
            .mark_bar()
            .encode(
                x=alt.X(
                    "spend_usd:Q",
                    title="Inversión en USD",
                    axis=alt.Axis(format=",.2f"),
                ),
                y=alt.Y(
                    "campaign:N",
                    title=None,
                    sort="-x",
                ),
                tooltip=[
                    alt.Tooltip("campaign:N", title="Campaña"),
                    alt.Tooltip(
                        "spend_usd:Q",
                        title="Inversión en USD",
                        format=",.2f",
                    ),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(ranking_chart, use_container_width=True)

    with scatter_column:
        st.subheader("CPA vs. conversiones")
        scatter_chart = (
            alt.Chart(campaign)
            .mark_circle(opacity=0.75)
            .encode(
                x=alt.X(
                    "cpa:Q",
                    title="CPA en USD",
                    axis=alt.Axis(format=",.2f"),
                ),
                y=alt.Y("conversions:Q", title="Conversiones"),
                size=alt.Size("spend_usd:Q", title="Inversión en USD"),
                tooltip=[
                    alt.Tooltip("campaign:N", title="Campaña"),
                    alt.Tooltip("cpa:Q", title="CPA en USD", format=",.2f"),
                    alt.Tooltip("conversions:Q", title="Conversiones", format=",.2f"),
                    alt.Tooltip(
                        "spend_usd:Q",
                        title="Inversión en USD",
                        format=",.2f",
                    ),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(scatter_chart, use_container_width=True)

    st.subheader("Concentración de inversión y conversiones (Pareto)")
    pareto = build_campaign_pareto(campaign)
    pareto_lines = pareto.melt(
        id_vars=["campaign_rank", "campaign"],
        value_vars=[
            "cumulative_investment_share",
            "cumulative_conversion_share",
        ],
        var_name="metric",
        value_name="cumulative_share",
    ).replace({
        "metric": {
            "cumulative_investment_share": "Inversión acumulada",
            "cumulative_conversion_share": "Conversiones acumuladas",
        }
    })
    pareto_bars = (
        alt.Chart(pareto)
        .mark_bar(opacity=0.35)
        .encode(
            x=alt.X(
                "campaign_rank:O",
                title="Campañas ordenadas por inversión en USD",
            ),
            y=alt.Y(
                "investment_share:Q",
                title="Participación de inversión",
                axis=alt.Axis(format=".0%"),
            ),
            tooltip=[
                alt.Tooltip("campaign_rank:O", title="Posición"),
                alt.Tooltip("campaign:N", title="Campaña"),
                alt.Tooltip(
                    "investment_share:Q",
                    title="Participación de inversión",
                    format=".1%",
                ),
            ],
        )
    )
    pareto_chart = pareto_bars + (
        alt.Chart(pareto_lines)
        .mark_line(point=True)
        .encode(
            x="campaign_rank:O",
            y=alt.Y(
                "cumulative_share:Q",
                title="Participación acumulada",
                axis=alt.Axis(format=".0%"),
            ),
            color=alt.Color("metric:N", title="Acumulado"),
            tooltip=[
                alt.Tooltip("campaign_rank:O", title="Posición"),
                alt.Tooltip("campaign:N", title="Campaña"),
                alt.Tooltip("metric:N", title="Métrica"),
                alt.Tooltip(
                    "cumulative_share:Q",
                    title="Participación acumulada",
                    format=".1%",
                ),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(pareto_chart, use_container_width=True)

    st.subheader("Eficiencia: CTR vs. CPA")
    efficiency_chart = (
        alt.Chart(campaign)
        .mark_circle(opacity=0.75)
        .encode(
            x=alt.X(
                "cpa:Q",
                title="CPA en USD",
                axis=alt.Axis(format=",.2f"),
            ),
            y=alt.Y(
                "ctr:Q",
                title="CTR",
                axis=alt.Axis(format=".1%"),
            ),
            size=alt.Size("spend_usd:Q", title="Inversión en USD"),
            tooltip=[
                alt.Tooltip("campaign:N", title="Campaña"),
                alt.Tooltip("ctr:Q", title="CTR", format=".1%"),
                alt.Tooltip("cpa:Q", title="CPA en USD", format=",.2f"),
                alt.Tooltip(
                    "spend_usd:Q",
                    title="Inversión en USD",
                    format=",.2f",
                ),
            ],
        )
        .properties(height=420)
    )
    st.altair_chart(efficiency_chart, use_container_width=True)

with tab_campaigns:
    st.subheader("Performance por campaña")
    campaign_display = to_display_frame(
        campaign.sort_values("spend_usd", ascending=False)
    )
    st.dataframe(
        campaign_display,
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Descargar campañas CSV",
        campaign_display.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="campaign_performance.csv",
        mime="text/csv",
    )

with tab_daily:
    st.subheader("Detalle diario")
    daily_display = to_display_frame(daily)
    st.dataframe(daily_display, use_container_width=True, hide_index=True)
    st.download_button(
        "Descargar detalle CSV",
        daily_display.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="daily_performance.csv",
        mime="text/csv",
    )