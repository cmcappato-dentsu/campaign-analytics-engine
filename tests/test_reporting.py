import types

import pandas as pd
import pytest

from src.reporting import (
    analyze_clicks_vs_conversions,
    analyze_waste_signals,
    generate_budget_visibility_insight,
    generate_clicks_vs_conversions_insight,
    generate_insufficient_data_insight,
    generate_top_campaigns_summary,
    generate_top_findings_summary,
    generate_wasted_budget_insight,
)
from src.scoring import is_positive_finding, prioritize_findings


def _eligibility(campaigns):
    return pd.DataFrame({
        "campaign": campaigns,
        "eligibility_status": ["eligible"] * len(campaigns),
        "eligibility_reason": ["ok"] * len(campaigns),
        "is_eligible": [True] * len(campaigns),
    })


def _campaign_frame(rows):
    frame = pd.DataFrame(rows)
    frame["cpa"] = frame["spend_usd"] / frame["conversions"].replace(0, pd.NA)
    return frame


def test_budget_limited_campaign_is_reported_as_opportunity():
    campaigns = ["A", "B", "C"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 50.0, "clicks": 500, "impressions": 10000},
        {"campaign": "B", "spend_usd": 500.0, "conversions": 25.0, "clicks": 250, "impressions": 5000},
        {"campaign": "C", "spend_usd": 400.0, "conversions": 20.0, "clicks": 200, "impressions": 4000},
    ])
    df_daily = pd.DataFrame({
        "campaign": ["A", "B", "C"],
        "network": ["Búsqueda", "Búsqueda", "Búsqueda"],
        "lost_is_budget": [0.35, 0.0, 0.0],
        "impressions": [10000, 5000, 4000],
        "spend_usd": [1000.0, 500.0, 400.0],
        "conversions": [50.0, 25.0, 20.0],
    })

    analysis = analyze_waste_signals(
        df_campaign, _eligibility(campaigns), [], [], df_daily=df_daily
    )
    text = generate_wasted_budget_insight(
        df_campaign, _eligibility(campaigns), [], [], df_daily=df_daily,
        analysis=analysis,
    )

    assert len(analysis["budget_opportunities"]) == 1
    assert analysis["budget_opportunities"][0]["campaign"] == "A"
    assert analysis["budget_opportunities"][0]["estimated_upside"] == pytest.approx(
        1000 * 0.35 / 0.65
    )
    assert "Oportunidad no capturada" in text
    assert "no es desperdicio" in text
    assert "punto 4" in text
    assert "Potencial estimado" not in text
    assert "Ineficiencia" not in text


def test_budget_visibility_renders_lost_share_table():
    opportunities = [{
        "campaign": "A",
        "lost_share": 0.35,
        "spend": 1000.0,
        "conversions": 50.0,
        "cpa": 20.0,
        "efficient": True,
        "estimated_upside": 538.4615,
    }]

    text = generate_budget_visibility_insight(opportunities)

    assert (
        "| Campaña | Cuota de impresiones perdida por presupuesto | "
        "Inversión actual | Inversión adicional estimada |"
    ) in text
    assert "| **A** | 35,0% | USD 1.000,00 | USD 538,46 |" in text
    assert "CPA" not in text
    assert "Total invertido por estas campañas" in text
    assert "Inversión adicional estimada en conjunto" in text


def test_budget_visibility_explains_lost_share_and_extra_investment():
    opportunities = [{
        "campaign": "A",
        "lost_share": 0.35,
        "spend": 1000.0,
        "cpa": 20.0,
        "efficient": True,
        "estimated_upside": 538.4615,
    }]

    text = generate_budget_visibility_insight(opportunities)

    assert "**Qué es la cuota perdida**" in text
    assert "no sobre el dinero" in text
    assert "**Qué es la inversión adicional estimada**" in text
    assert "cuánto falta invertir" in text
    assert "no a \"cuánto se invirtió de más\"" in text
    assert "no es plata perdida" in text
    assert "**Cómo se calcula**" in text
    assert (
        "inversión adicional = inversión actual × cuota perdida / "
        "(1 − cuota perdida)"
    ) in text
    assert "USD 1.000** adicionales" in text
    assert "limita a **90%**" in text


def test_budget_visibility_orders_by_lost_share():
    opportunities = [
        {
            "campaign": "Chica",
            "lost_share": 0.60,
            "spend": 100.0,
            "cpa": 30.0,
            "efficient": False,
            "estimated_upside": 150.0,
        },
        {
            "campaign": "Grande",
            "lost_share": 0.25,
            "spend": 4000.0,
            "cpa": 10.0,
            "efficient": True,
            "estimated_upside": 1333.33,
        },
    ]

    text = generate_budget_visibility_insight(opportunities)

    assert text.index("**Chica**") < text.index("**Grande**")
    assert "| **Chica** | 60,0% | USD 100,00 | USD 150,00 |" in text
    assert "| **Grande** | 25,0% | USD 4.000,00 | USD 1.333,33 |" in text


def test_budget_visibility_explains_missing_budget_column():
    text = generate_budget_visibility_insight([], budget_data_available=False)

    assert "no incluye" in text
    assert "lost_is_budget" in text


def test_budget_visibility_without_budget_limited_campaigns():
    text = generate_budget_visibility_insight([], budget_data_available=True)

    assert "No se identificaron campañas limitadas por presupuesto" in text


def test_lost_is_budget_exported_as_percentage_is_normalized():
    campaigns = ["A", "B", "C"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 50.0, "clicks": 500, "impressions": 10000},
        {"campaign": "B", "spend_usd": 500.0, "conversions": 25.0, "clicks": 250, "impressions": 5000},
        {"campaign": "C", "spend_usd": 400.0, "conversions": 20.0, "clicks": 200, "impressions": 4000},
    ])
    df_daily = pd.DataFrame({
        "campaign": ["A", "B", "C"],
        "network": ["Búsqueda", "Búsqueda", "Búsqueda"],
        "lost_is_budget": [35, 0, 0],
        "impressions": [10000, 5000, 4000],
        "spend_usd": [1000.0, 500.0, 400.0],
        "conversions": [50.0, 25.0, 20.0],
    })

    analysis = analyze_waste_signals(
        df_campaign, _eligibility(campaigns), [], [], df_daily=df_daily
    )

    assert analysis["budget_opportunities"][0]["lost_share"] == pytest.approx(0.35)


def test_network_with_spend_and_zero_conversions_is_flagged():
    campaigns = ["A"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 10.0, "clicks": 100, "impressions": 1000},
    ])
    df_daily = pd.DataFrame({
        "campaign": ["A", "A"],
        "network": ["Búsqueda", "Red de Display"],
        "impressions": [700, 300],
        "spend_usd": [700.0, 300.0],
        "conversions": [10.0, 0.0],
    })

    analysis = analyze_waste_signals(
        df_campaign, _eligibility(campaigns), [], [], df_daily=df_daily
    )
    text = generate_wasted_budget_insight(
        df_campaign, _eligibility(campaigns), [], [], df_daily=df_daily,
        analysis=analysis,
    )

    assert len(analysis["network_zero_conversion"]) == 1
    assert analysis["network_zero_conversion"][0]["network"] == "Red de Display"
    assert "Redes con gasto y 0 conversiones" in text
    assert "Red de Display" in text


def test_campaign_with_cpa_far_above_median_is_flagged_as_inefficiency():
    campaigns = ["A", "B", "C", "D"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 5.0, "clicks": 100, "impressions": 1000},
        {"campaign": "B", "spend_usd": 500.0, "conversions": 25.0, "clicks": 250, "impressions": 2500},
        {"campaign": "C", "spend_usd": 400.0, "conversions": 20.0, "clicks": 200, "impressions": 2000},
        {"campaign": "D", "spend_usd": 300.0, "conversions": 15.0, "clicks": 150, "impressions": 1500},
    ])

    analysis = analyze_waste_signals(
        df_campaign, _eligibility(campaigns), [], [], df_daily=None
    )
    text = generate_wasted_budget_insight(
        df_campaign, _eligibility(campaigns), [], [], df_daily=None,
        analysis=analysis,
    )

    assert analysis["median_cpa"] == pytest.approx(20.0)
    assert len(analysis["cpa_inefficient"]) == 1
    assert analysis["cpa_inefficient"][0]["campaign"] == "A"
    assert analysis["cpa_inefficient"][0]["excess_cost"] == pytest.approx(900.0)
    assert "Ineficiencia: exceso de costo estimado" in text
    assert "| Campaña | CPA | vs. mediana | Conversiones | Exceso estimado |" in text
    assert "| **A** | USD 200,00 | 10.0× | 5 | USD 900,00 |" in text


def test_inefficiency_table_shows_top_10_and_mentions_remaining():
    rows = [
        {
            "campaign": f"Campaign {index:02d}",
            "spend": 1000.0,
            "conversions": 5.0,
            "cpa": 200.0,
            "median_cpa": 20.0,
            "ratio": 10.0,
            "excess_cost": 900.0,
        }
        for index in range(1, 13)
    ]
    analysis = {
        "total_spend": 12000.0,
        "median_cpa": 20.0,
        "network_zero_conversion": [],
        "network_inefficient": [],
        "cpa_inefficient": rows,
        "budget_opportunities": [],
    }
    campaigns = ["A"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 5.0, "clicks": 100, "impressions": 1000},
    ])

    text = generate_wasted_budget_insight(
        df_campaign, _eligibility(campaigns), [], [], df_daily=None,
        analysis=analysis,
    )

    assert text.count("| **Campaign ") == 10
    assert "Ver las 2 restantes" in text


def test_budget_opportunities_only_include_eligible_campaigns():
    campaigns = ["A", "B"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 50.0, "clicks": 500, "impressions": 10000},
        {"campaign": "B", "spend_usd": 500.0, "conversions": 10.0, "clicks": 100, "impressions": 5000},
    ])
    eligibility = pd.DataFrame({
        "campaign": ["A", "B"],
        "eligibility_status": ["eligible", "insufficient_volume"],
        "eligibility_reason": ["ok", "poco volumen"],
        "is_eligible": [True, False],
    })
    df_daily = pd.DataFrame({
        "campaign": ["A", "B"],
        "network": ["Búsqueda", "Búsqueda"],
        "lost_is_budget": [0.40, 0.60],
        "impressions": [10000, 5000],
        "spend_usd": [1000.0, 500.0],
        "conversions": [50.0, 10.0],
    })

    analysis = analyze_waste_signals(
        df_campaign, eligibility, [], [], df_daily=df_daily
    )

    assert [row["campaign"] for row in analysis["budget_opportunities"]] == ["A"]


def test_display_in_search_renders_as_compact_table():
    campaigns = ["ARG_OTT_PERF"]
    df_campaign = _campaign_frame([
        {"campaign": "ARG_OTT_PERF", "spend_usd": 512.26, "conversions": 10.0, "clicks": 100, "impressions": 1000},
    ])
    df_daily = pd.DataFrame({
        "campaign": ["ARG_OTT_PERF", "ARG_OTT_PERF"],
        "network": ["Red de Display de Google", "Búsqueda"],
        "impressions": [300, 700],
        "spend_usd": [412.26, 100.0],
        "conversions": [0.0, 10.0],
    })
    display_findings = [types.SimpleNamespace(campaign="ARG_OTT_PERF")]

    analysis = analyze_waste_signals(
        df_campaign, _eligibility(campaigns), display_findings, [], df_daily=df_daily
    )
    text = generate_wasted_budget_insight(
        df_campaign, _eligibility(campaigns), display_findings, [], df_daily=df_daily,
        analysis=analysis,
    )

    assert "Red de Display activada en campañas de Búsqueda" in text
    assert "| Campaña | Red observada | Gasto en Display | Resultado |" in text
    assert "| **ARG_OTT_PERF** | Red de Display de Google | USD 412,26 | 0 conversiones |" in text
    assert "Conviene revisar la configuración de estas campañas" in text


def test_clean_account_reports_no_confirmed_waste():
    campaigns = ["A"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 10.0, "clicks": 100, "impressions": 1000},
    ])
    df_daily = pd.DataFrame({
        "campaign": ["A"],
        "network": ["Búsqueda"],
        "lost_is_budget": [0.05],
        "impressions": [1000],
        "spend_usd": [1000.0],
        "conversions": [10.0],
    })

    analysis = analyze_waste_signals(
        df_campaign, _eligibility(campaigns), [], [], df_daily=df_daily
    )
    text = generate_wasted_budget_insight(
        df_campaign, _eligibility(campaigns), [], [], df_daily=df_daily,
        analysis=analysis,
    )

    assert "✅ No se detectó desperdicio confirmado ni ineficiencia" in text
    assert "Oportunidad no capturada" not in text


def test_clicks_vs_conversions_separates_sinks_and_efficient():
    df_campaign = pd.DataFrame([
        {"campaign": "Clics sin ventas", "clicks": 8000, "conversions": 40},
        {"campaign": "Buena", "clicks": 1000, "conversions": 80},
        {"campaign": "Media", "clicks": 1000, "conversions": 40},
    ])

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    assert "La cuenta completa convierte **1,6%** de los clics" in text
    assert "**160 conversiones** sobre **10.000 clics**" in text
    assert "🔴 **Atraen clics, pero convierten por debajo del promedio**" in text
    assert "| **Clics sin ventas** | 8.000 | 40 | 0,50% |" in text
    assert "🟢 **Convierten por encima del promedio**" in text
    assert "| **Buena** | 1.000 | 80 | 8,0% |" in text
    assert "| **Media** | 1.000 | 40 | 4,0% |" in text
    assert text.index("**Buena**") < text.index("**Media**")
    # La campaña mala va primero: es lo accionable
    assert text.index("🔴") < text.index("🟢")


def test_clicks_vs_conversions_uses_account_average_not_external_target():
    # A convierte 3% y B 1%: el promedio de la cuenta es 2%.
    # Con un objetivo externo de 5%, A estaría "mal"; contra la cuenta, está bien.
    df_campaign = pd.DataFrame([
        {"campaign": "A", "clicks": 1000, "conversions": 30},
        {"campaign": "B", "clicks": 1000, "conversions": 10},
    ])

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    green = text.index("🟢 **Convierten por encima del promedio**")
    red = text.index("🔴 **Atraen clics")
    assert red < text.index("**B**") < green
    assert green < text.index("**A**")
    assert "objetivo" not in text.lower()
    assert "benchmark" not in text.lower()


def test_clicks_vs_conversions_keeps_full_campaign_name():
    long_name = "ARG_OTT_PERF_GOOGLE ADS_AlwaysOn-CONV_BRAND_Search Ads"
    df_campaign = pd.DataFrame([
        {"campaign": long_name, "clicks": 5000, "conversions": 10},
        {"campaign": "Buena", "clicks": 1000, "conversions": 100},
    ])

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    assert f"| **{long_name}** | 5.000 | 10 | 0,20% |" in text


def test_clicks_vs_conversions_limits_rows_and_mentions_rest():
    rows = [
        {"campaign": "C900", "clicks": 900, "conversions": 0},
        {"campaign": "C800", "clicks": 800, "conversions": 0},
        {"campaign": "C700", "clicks": 700, "conversions": 0},
        {"campaign": "C600", "clicks": 600, "conversions": 0},
        {"campaign": "C500", "clicks": 500, "conversions": 0},
        {"campaign": "Eficiente", "clicks": 10000, "conversions": 1000},
    ]
    df_campaign = pd.DataFrame(rows)

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    assert "| **C900** |" in text
    assert "| **C800** |" in text
    assert "| **C700** |" in text
    assert "| **C600** |" not in text
    assert "| **C500** |" not in text
    assert (
        "*2 campañas más con el mismo patrón: C600 (0,00%), C500 (0,00%).*"
        in text
    )


def test_clicks_vs_conversions_sinks_are_sorted_by_clicks():
    df_campaign = pd.DataFrame([
        {"campaign": "Muchos clics", "clicks": 6000, "conversions": 10},
        {"campaign": "Menos clics", "clicks": 2000, "conversions": 2},
        {"campaign": "Eficiente", "clicks": 2000, "conversions": 200},
    ])

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    assert text.index("**Muchos clics**") < text.index("**Menos clics**")


def test_clicks_vs_conversions_small_rates_use_two_decimals():
    df_campaign = pd.DataFrame([
        {"campaign": "A", "clicks": 200000, "conversions": 60},
        {"campaign": "Buena", "clicks": 1000, "conversions": 100},
    ])

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    assert "| **A** | 200.000 | 60 | 0,03% |" in text


def test_clicks_vs_conversions_skips_ineligible_and_low_volume():
    df_campaign = pd.DataFrame([
        {"campaign": "Elegible", "clicks": 1000, "conversions": 10},
        {"campaign": "PocosDatos", "clicks": 50, "conversions": 0},
        {"campaign": "NoElegible", "clicks": 1000, "conversions": 0},
    ])
    eligibility_df = pd.DataFrame({
        "campaign": ["Elegible", "PocosDatos", "NoElegible"],
        "is_eligible": [True, True, False],
    })

    text = generate_clicks_vs_conversions_insight(
        df_campaign=df_campaign,
        eligibility_df=eligibility_df,
    )

    assert "PocosDatos" not in text
    assert "NoElegible" not in text
    assert "✅ Todas las campañas con volumen suficiente" in text
    assert "Se omitieron **2** campañas con menos de 100 clics" in text


def test_clicks_vs_conversions_without_enough_data():
    df_campaign = pd.DataFrame([
        {"campaign": "A", "clicks": 10, "conversions": 1},
        {"campaign": "B", "clicks": 20, "conversions": 2},
    ])

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    assert "No hay campañas con al menos **100 clics**" in text
    assert "Se omitieron **2** campañas con menos de 100 clics" in text


def test_clicks_vs_conversions_without_conversions():
    df_campaign = pd.DataFrame([
        {"campaign": "A", "clicks": 1000, "conversions": 0},
    ])

    text = generate_clicks_vs_conversions_insight(df_campaign=df_campaign)

    assert "**ninguna conversión**" in text
    assert "registro de conversiones" in text


def test_analyze_clicks_vs_conversions_returns_totals_and_groups():
    df_campaign = pd.DataFrame([
        {"campaign": "A", "clicks": 8000, "conversions": 40},
        {"campaign": "B", "clicks": 1000, "conversions": 80},
        {"campaign": "C", "clicks": 1000, "conversions": 40},
        {"campaign": "D", "clicks": 50, "conversions": 5},
    ])
    eligibility_df = pd.DataFrame({
        "campaign": ["A", "B", "C", "D"],
        "is_eligible": [True, True, True, False],
    })

    analysis = analyze_clicks_vs_conversions(df_campaign, eligibility_df)

    assert analysis["total_clicks"] == 10000
    assert analysis["total_conversions"] == 160
    assert analysis["account_cvr"] == pytest.approx(0.016)
    assert analysis["campaigns"] == 3
    assert analysis["excluded"] == 1
    assert [row["campaign"] for row in analysis["click_sinks"]] == ["A"]
    assert [row["campaign"] for row in analysis["efficient_low_traffic"]] == [
        "B",
        "C",
    ]


def test_analyze_clicks_vs_conversions_handles_missing_data():
    analysis = analyze_clicks_vs_conversions(None)

    assert analysis["campaigns"] == 0
    assert analysis["account_cvr"] is None
    assert analysis["click_sinks"] == []
    assert analysis["efficient_low_traffic"] == []

def test_cpa_vs_reference_is_merged_into_waste_insight():
    campaigns = ["A"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 5.0, "clicks": 100, "impressions": 1000},
    ])
    cpa_findings = [
        types.SimpleNamespace(
            campaign="A",
            rule_id="benchmark_cpa_high",
            rule_name="CPA sobre el benchmark",
            metric_value=200.0,
            benchmark_value=100.0,
            variation_pct=1.0,
        ),
    ]
    analysis = {
        "total_spend": 1000.0,
        "median_cpa": 20.0,
        "budget_data_available": False,
        "network_zero_conversion": [],
        "network_inefficient": [],
        "cpa_inefficient": [],
        "budget_opportunities": [],
    }

    text = generate_wasted_budget_insight(
        df_campaign,
        _eligibility(campaigns),
        [],
        [],
        df_daily=None,
        analysis=analysis,
        cpa_findings=cpa_findings,
    )

    assert "CPA vs objetivo/benchmark" in text
    assert "| Campaña | CPA actual | Referencia | Variación | Conversiones | Inversión |" in text
    assert "| **A** | USD 200,00 | USD 100,00 | +100,0% | 5 | USD 1.000,00 |" in text


def test_cpa_vs_reference_is_not_rendered_without_findings():
    campaigns = ["A"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 5.0, "clicks": 100, "impressions": 1000},
    ])
    analysis = {
        "total_spend": 1000.0,
        "median_cpa": 20.0,
        "budget_data_available": False,
        "network_zero_conversion": [],
        "network_inefficient": [],
        "cpa_inefficient": [],
        "budget_opportunities": [],
    }

    text = generate_wasted_budget_insight(
        df_campaign,
        _eligibility(campaigns),
        [],
        [],
        df_daily=None,
        analysis=analysis,
        cpa_findings=[],
    )

    assert "CPA vs objetivo/benchmark" not in text


def test_insufficient_data_renders_table():
    eligibility = pd.DataFrame({
        "campaign": ["A", "B", "C"],
        "eligibility_status": [
            "insufficient_history",
            "insufficient_volume",
            "eligible",
        ],
        "active_days": [3, 10, 30],
        "clicks": [20, 40, 500],
        "spend_usd": [100.0, 200.0, 1000.0],
    })

    text = generate_insufficient_data_insight(eligibility)

    assert "| Campaña | Estado | Días activos | Clics | Inversión |" in text
    assert "| **B** | Volumen insuficiente | 10 | 40 | USD 200,00 |" in text
    assert "| **A** | Historial insuficiente | 3 | 20 | USD 100,00 |" in text
    assert "**C**" not in text


def test_insufficient_data_without_pending_campaigns():
    eligibility = pd.DataFrame({
        "campaign": ["A"],
        "eligibility_status": ["eligible"],
        "active_days": [30],
        "clicks": [500],
        "spend_usd": [1000.0],
    })

    text = generate_insufficient_data_insight(eligibility)

    assert "✅ Todas las campañas tienen historial y volumen suficiente" in text


def test_top_findings_renders_prioritized_action_plan():
    findings = [
        types.SimpleNamespace(
            rule_id="benchmark_cpa_high",
            rule_name="CPA sobre el benchmark",
            message="El CPA subió 287% sobre el benchmark (8.50 → 32.86).",
            campaign="A",
            severity="critical",
            total_score=311.0,
            metric_values={
                "variation_pct": 2.866,
                "benchmark_value": 8.5,
                "current_value": 32.86,
            },
        ),
        types.SimpleNamespace(
            rule_id="config_display_in_search",
            rule_name="Red de Display en campaña de Búsqueda",
            message="La campaña 'B' tiene Red de Display activada.",
            campaign="B",
            severity="high",
            total_score=95.0,
            metric_values={},
        ),
    ]

    text = generate_top_findings_summary(findings)

    assert (
        "| # | Severidad | Campaña | Hallazgo | Real | Referencia | "
        "Variación | Acción |"
    ) in text
    assert "**Cómo se asigna la severidad**" in text
    assert "no se incluyen: no requieren acción" in text
    assert (
        "| 1 | 🔴 | **A** | CPA alto | USD 32,86 | USD 8,50 | +286,6% | "
        "Revisar pujas y segmentación |"
    ) in text
    assert (
        "| 2 | 🟠 | **B** | Display activo | — | — | — | "
        "Desactivar Red de Display |"
    ) in text
    # El nombre de la campaña aparece una sola vez por fila.
    assert text.count("**A**") == 1
    assert "La campaña 'A'" not in text


def test_top_findings_formats_spend_without_conversions_outlier():
    finding = types.SimpleNamespace(
        rule_id="",
        rule_name="",
        message=(
            "La campaña 'A' gastó $1,438.12 con 12 clics pero 0 conversiones."
        ),
        campaign="A",
        severity="critical",
        total_score=500.0,
        metric_values={
            "variation_pct": None,
            "benchmark_value": None,
            "current_value": 1438.12,
        },
    )

    text = generate_top_findings_summary([finding])

    assert (
        "| 1 | 🔴 | **A** | Gasto sin conversiones | USD 1.438,12 | — | — | "
        "Pausar y revisar configuración/tracking |"
    ) in text


def test_positive_findings_are_excluded_from_action_plan():
    df_campaign = pd.DataFrame({
        "campaign": ["A", "B"],
        "spend_usd": [1000.0, 1000.0],
    })
    findings = [
        types.SimpleNamespace(
            rule_id="benchmark_ctr_high",
            rule_name="CTR sobre el benchmark",
            message="El CTR subió 60% en A.",
            campaign="A",
            severity="high",
            variation_pct=0.60,
            metric_value=0.05,
            benchmark_value=0.03,
            persistence_count=2,
        ),
        types.SimpleNamespace(
            rule_id="benchmark_cpa_high",
            rule_name="CPA sobre el benchmark",
            message="El CPA subió 150% en B.",
            campaign="B",
            severity="high",
            variation_pct=1.50,
            metric_value=25.0,
            benchmark_value=10.0,
            persistence_count=2,
        ),
    ]

    scored = prioritize_findings(findings, df_campaign, max_findings=5)

    assert [finding.campaign for finding in scored] == ["B"]


def test_positive_finding_detection():
    positive = types.SimpleNamespace(
        rule_id="benchmark_ctr_high",
        rule_name="CTR sobre el benchmark",
        message="El CTR subió 60% en A.",
        campaign="A",
    )
    negative = types.SimpleNamespace(
        rule_id="benchmark_cpa_high",
        rule_name="CPA sobre el benchmark",
        message="El CPA subió 150% en B.",
        campaign="B",
    )

    assert is_positive_finding(positive)
    assert not is_positive_finding(negative)


def test_top_findings_orders_by_score():
    findings = [
        types.SimpleNamespace(
            rule_id="benchmark_ctr_low",
            rule_name="CTR bajo",
            message="CTR bajo",
            campaign="Bajo",
            severity="high",
            total_score=10.0,
        ),
        types.SimpleNamespace(
            rule_id="config_display_in_search",
            rule_name="Display",
            message="Display en Búsqueda",
            campaign="Alto",
            severity="critical",
            total_score=300.0,
        ),
    ]

    text = generate_top_findings_summary(findings)

    assert text.index("**Alto**") < text.index("**Bajo**")


def test_top_findings_without_scored_findings():
    text = generate_top_findings_summary([])

    assert "✅ No se generaron hallazgos prioritarios" in text


def test_low_volume_spend_with_spend_column_in_eligibility_does_not_break():
    campaigns = ["A", "B"]
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 1000.0, "conversions": 10.0, "clicks": 100, "impressions": 1000},
        {"campaign": "B", "spend_usd": 200.0, "conversions": 1.0, "clicks": 5, "impressions": 50},
    ])
    eligibility = pd.DataFrame({
        "campaign": ["A", "B"],
        "eligibility_status": ["eligible", "insufficient_volume"],
        "eligibility_reason": ["ok", "poco volumen"],
        "is_eligible": [True, False],
        "spend_usd": [1000.0, 200.0],
    })

    analysis = analyze_waste_signals(
        df_campaign, eligibility, [], [], df_daily=None
    )
    text = generate_wasted_budget_insight(
        df_campaign, eligibility, [], [], df_daily=None, analysis=analysis,
    )

    assert "Riesgo: campañas con volumen insuficiente" in text
    assert "USD 200,00" in text


def test_top_campaigns_renders_combined_table():
    df_campaign = _campaign_frame([
        {"campaign": "A", "spend_usd": 600.0, "conversions": 30.0},
        {"campaign": "B", "spend_usd": 300.0, "conversions": 60.0},
        {"campaign": "C", "spend_usd": 100.0, "conversions": 10.0},
    ])

    text = generate_top_campaigns_summary(df_campaign, top_n=2)

    assert (
        "| Campaña | Inversión | % de la inversión | Conversiones | "
        "% de las conversiones |"
    ) in text
    assert "| **A** | USD 600,00 | 60,0% | 30 | 30,0% |" in text
    assert "| **B** | USD 300,00 | 30,0% | 60 | 60,0% |" in text
