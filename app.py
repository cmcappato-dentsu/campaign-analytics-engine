import streamlit as st
import altair as alt
import os
from tempfile import NamedTemporaryFile

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


st.set_page_config(
    page_title="Miau",
    layout="wide"
)


st.title("Miau")

st.write(
    "Motor de análisis automatizado de campañas."
)

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
    st.info("Subí un archivo CSV o Excel para comenzar el análisis.")
    st.stop()

suffix = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()

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

daily = result["daily"]
campaign = result["campaign"]

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

top_row = st.columns(3)
top_row[0].metric("Inversión en USD", format_currency(total_spend))
top_row[1].metric("Impresiones", format_integer(total_impressions))
top_row[2].metric("Clics", format_integer(total_clicks))

bottom_row = st.columns(2)
bottom_row[0].metric("CTR", format_percentage(ctr))
bottom_row[1].metric("CPA en USD", format_currency(cpa))

tab_charts, tab_campaigns, tab_daily = st.tabs(
    ["Gráficos", "Por campaña", "Detalle diario"]
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

    st.subheader("Concentración de inversión y conversiones")
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
                "ctr:Q",
                title="CTR",
                axis=alt.Axis(format=".1%"),
            ),
            y=alt.Y(
                "cpa:Q",
                title="CPA en USD",
                axis=alt.Axis(format=",.2f"),
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
