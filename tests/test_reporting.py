import types

import pandas as pd
import pytest

from src.reporting import (
    analyze_waste_signals,
    generate_scale_opportunities,
    generate_wasted_budget_insight,
)


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


def test_scale_opportunities_renders_budget_limited_table():
    opportunities = [{
        "campaign": "A",
        "lost_share": 0.35,
        "spend": 1000.0,
        "conversions": 50.0,
        "cpa": 20.0,
        "efficient": True,
        "estimated_upside": 538.4615,
    }]

    text = generate_scale_opportunities(opportunities, 20.0)

    assert "| Campaña | Cuota perdida por presupuesto | CPA | Inversión actual | Techo estimado | Prioridad |" in text
    assert "| **A** | 35,0% | USD 20,00 | USD 1.000,00 | USD 538,46 | 🟢 Alta |" in text
    assert "CPA mediano de la cuenta" in text


def test_scale_opportunities_explains_missing_budget_column():
    text = generate_scale_opportunities([], None, budget_data_available=False)

    assert "no incluye" in text
    assert "lost_is_budget" in text


def test_scale_opportunities_without_budget_limited_campaigns():
    text = generate_scale_opportunities([], 20.0, budget_data_available=True)

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
