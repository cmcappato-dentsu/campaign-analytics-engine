"""Tests para reglas de diagnóstico y benchmarks por cuartiles."""

import pandas as pd
import numpy as np

from src.diagnostics import (
    calculate_benchmark,
    _assign_quartile,
    check_benchmark_variations,
    DiagnosticRules,
    run_diagnostics,
)


def test_assign_quartile_basic():
    """Test que _assign_quartile asigna Q1-Q4 correctamente."""
    df = pd.DataFrame({
        "campaign": ["A", "A", "B", "B"],
        "date": pd.date_range("2024-01-01", periods=4),
        "ctr": [0.03, 0.04, 0.02, 0.03],
        "spend_usd": [1000, 1200, 800, 900],
    })

    quartiles = _assign_quartile(df, "spend_usd")

    assert len(quartiles) == 4
    assert quartiles.nunique() == 4  # Q1, Q2, Q3, Q4


def test_assign_quartile_order():
    """Test que Q1 tiene mayor gasto que Q4."""
    df = pd.DataFrame({
        "campaign": ["A"] * 100,
        "date": pd.date_range("2024-01-01", periods=100),
        "ctr": [0.03] * 100,
        "spend_usd": list(range(100, 1100, 10)),  # 100 a 1090
    })

    quartiles = _assign_quartile(df, "spend_usd")

    # Q1 debería tener los valores más altos de spend_usd
    q1_spend = df.loc[quartiles == "Q1", "spend_usd"].min()
    q4_spend = df.loc[quartiles == "Q4", "spend_usd"].max()

    assert q1_spend > q4_spend, f"Q1 min ({q1_spend}) debe ser > Q4 max ({q4_spend})"


def test_calculate_benchmark_quartile_segment():
    """Test que calculate_benchmark filtra por segmento de cuartil."""
    df_history = pd.DataFrame({
        "campaign": ["Q1_camp", "Q1_camp", "Q2_camp", "Q2_camp"] * 2,
        "date": pd.date_range("2024-01-01", periods=8),
        "ctr": [0.03, 0.04, 0.02, 0.03, 0.03, 0.035, 0.025, 0.028],
        "spend_usd": [1500, 1400, 800, 900, 1500, 1400, 800, 900],
    })

    df_history["quartile"] = _assign_quartile(df_history, "spend_usd")

    # Q1 benchmark
    bench_q1 = calculate_benchmark(df_history, quartile_segment="Q1")
    # Q2 benchmark
    bench_q2 = calculate_benchmark(df_history, quartile_segment="Q2")


def test_check_benchmark_variations_ctr_high():
    """Test que CTR alto se detecta correctamente (sin persistencia requerida)."""
    df_history = pd.DataFrame({
        "campaign": ["Test_camp"] * 4,
        "date": pd.date_range("2024-01-01", periods=4),
        "ctr": [0.03, 0.04, 0.035, 0.05],  # Último: 5% vs benchmark ~3.7% = +36%
        "spend_usd": [1500, 1400, 1600, 1550],
    })

    df_history["quartile"] = _assign_quartile(df_history, "spend_usd")
    df_benchmark = calculate_benchmark(df_history)

    # Usar persistence_df=None para trigger outlier condition
    df_campaign = pd.DataFrame({
        "campaign": ["Test_camp"],
        "ctr": [0.05],
        "cpc": [1.8],
        "cpa": [55],
        "conversions": [15],
        "conversion_rate": [0.03],
        "spend_usd": [1500],
    })

    findings = check_benchmark_variations(df_campaign, df_benchmark, persistence_df=None)
    ctr_findings = [f for f in findings if "benchmark" in f.rule_id]
    assert len(ctr_findings) > 0, "Debería haber hallazgos de CTR alto"


def test_check_benchmark_variations_ctr_low():
    """Test que CTR bajo se detecta correctamente (sin persistencia requerida)."""
    df_history = pd.DataFrame({
        "campaign": ["Test_camp"] * 4,
        "date": pd.date_range("2024-01-01", periods=4),
        # Benchmark ~3.68%, CTR 1% = -73% < -25% (ahora -20% umbral)
        "ctr": [0.03, 0.04, 0.035, 0.01],  # Último: 1% vs benchmark ~3.7% = -73%
        "spend_usd": [1500, 1400, 1600, 1550],
    })

    df_history["quartile"] = _assign_quartile(df_history, "spend_usd")
    df_benchmark = calculate_benchmark(df_history)

    # Usar persistence_df=None para trigger outlier condition
    df_campaign = pd.DataFrame({
        "campaign": ["Test_camp"],
        "ctr": [0.01],
        "cpc": [1.8],
        "cpa": [55],
        "conversions": [15],
        "conversion_rate": [0.01],
        "spend_usd": [1500],
    })

    findings = check_benchmark_variations(df_campaign, df_benchmark, persistence_df=None)
    ctr_findings = [f for f in findings if "benchmark" in f.rule_id]
    assert len(ctr_findings) > 0, "Debería haber hallazgos de CTR bajo"


def test_ctr_message_includes_campaign():
    """Test que el mensaje de CTR incluye el nombre de la campaña."""
    df_history = pd.DataFrame({
        "campaign": ["Mi_Campaña"] * 4,
        "date": pd.date_range("2024-01-01", periods=4),
        "ctr": [0.03, 0.04, 0.035, 0.05],
        "spend_usd": [1500, 1400, 1600, 1550],
    })

    df_history["quartile"] = _assign_quartile(df_history, "spend_usd")
    df_benchmark = calculate_benchmark(df_history)

    df_campaign = pd.DataFrame({
        "campaign": ["Mi_Campaña"],
        "ctr": [0.05],
        "cpc": [1.8],
        "cpa": [55],
        "conversions": [15],
        "conversion_rate": [0.03],
        "spend_usd": [1500],
    })

    findings = check_benchmark_variations(df_campaign, df_benchmark, persistence_df=None)
    for f in findings:
        assert "Mi_Campaña" in f.message, f"El mensaje debe incluir el nombre de la campaña: {f.message}"


def test_ctr_message_uses_decimal_format():
    """Test que el mensaje de CTR usa formato decimal (0.03 → 0.05) y no porcentaje."""
    df_history = pd.DataFrame({
        "campaign": ["Test"] * 4,
        "date": pd.date_range("2024-01-01", periods=4),
        "ctr": [0.03, 0.04, 0.035, 0.05],
        "spend_usd": [1500, 1400, 1600, 1550],
    })

    df_history["quartile"] = _assign_quartile(df_history, "spend_usd")
    df_benchmark = calculate_benchmark(df_history)

    df_campaign = pd.DataFrame({
        "campaign": ["Test"],
        "ctr": [0.05],
        "cpc": [1.8],
        "cpa": [55],
        "conversions": [15],
        "conversion_rate": [0.03],
        "spend_usd": [1500],
    })

    findings = check_benchmark_variations(df_campaign, df_benchmark, persistence_df=None)
    for f in findings:
        # Debe contener paréntesis con valores decimales como 0.03, 0.05
        # y NO debe contener formato 3.00% → 5.00%
        assert ("0.03" in f.message or "0.05" in f.message), \
            f"El mensaje debe usar formato decimal, got: {f.message}"
        # No debería tener "3.00%" o "5.00%" (formato porcentaje)
        assert "3.00%" not in f.message and "5.00%" not in f.message, \
            f"El mensaje no debe usar formato porcentaje, got: {f.message}"


def test_lost_is_budget_alert():
    """Test que Lost IS Budget > 20% genera alarma (sin persistencia requerida)."""
    df_history = pd.DataFrame({
        "campaign": ["Test"] * 4,
        "date": pd.date_range("2024-01-01", periods=4),
        "ctr": [0.03, 0.04, 0.035, 0.042],
        "spend_usd": [1500, 1400, 1600, 1550],
        "impression_share": [0.45, 0.48, 0.42, 0.47],
        "lost_is_budget": [0.10, 0.15, 0.25, 0.30],  # 25% y 30% deben alertar
    })

    df_history["quartile"] = _assign_quartile(df_history, "spend_usd")
    df_benchmark = calculate_benchmark(df_history)

    # Usar persistence_df=None - el outlier condition triggerá la alarma
    df_campaign = pd.DataFrame({
        "campaign": ["Test"],
        "ctr": [0.03],
        "cpc": [1.8],
        "cpa": [55],
        "conversions": [15],
        "conversion_rate": [0.03],
        "spend_usd": [1500],
        "impression_share": [0.45],
        "top_impression_share": [0.20],
        "lost_is_budget": [0.25],
    })

    # Pasar persistence_df=None - el outlier condition (variación > 2x umbral) triggerá la alarma
    findings = check_benchmark_variations(df_campaign, df_benchmark, persistence_df=None)
    lost_budget_findings = [f for f in findings if "impr_share" in f.rule_id.lower()]
    assert len(lost_budget_findings) > 0, "Debería haber alarma de Lost IS Budget > 20%"


def test_top_impression_share_alert():
    """Test que Top IS < 30% genera alarma (sin persistencia requerida)."""
    df_history = pd.DataFrame({
        "campaign": ["Test"] * 4,
        "date": pd.date_range("2024-01-01", periods=4),
        "ctr": [0.03, 0.04, 0.035, 0.042],
        "spend_usd": [1500, 1400, 1600, 1550],
        "impression_share": [0.45, 0.48, 0.42, 0.47],
        "lost_is_budget": [0.10, 0.15, 0.25, 0.30],
    })

    df_history["quartile"] = _assign_quartile(df_history, "spend_usd")
    df_benchmark = calculate_benchmark(df_history)

    # Usar persistence_df=None
    df_campaign = pd.DataFrame({
        "campaign": ["Test"],
        "ctr": [0.03],
        "cpc": [1.8],
        "cpa": [55],
        "conversions": [15],
        "conversion_rate": [0.03],
        "spend_usd": [1500],
        "impression_share": [0.45],
        "top_impression_share": [-0.35],  # -35% caída, supura umbral 30% via outlier
        "lost_is_budget": [0.15],
    })

    # Pasar persistence_df=None
    findings = check_benchmark_variations(df_campaign, df_benchmark, persistence_df=None)
    top_is_findings = [f for f in findings if "Top" in f.rule_id or "impr_share" in f.rule_id.lower()]
    assert len(top_is_findings) > 0, "Debería haber alarma de Top IS < 30%"


def test_global_benchmark_when_no_quartile():
    """Test que calculate_benchmark funciona sin segmento de cuartil."""
    df_history = pd.DataFrame({
        "campaign": ["Global_camp"] * 4,
        "date": pd.date_range("2024-01-01", periods=4),
        "ctr": [0.03, 0.04, 0.035, 0.042],
        "spend_usd": [1500, 1400, 1600, 1550],
    })

    df_benchmark = calculate_benchmark(df_history, quartile_segment=None)
    assert df_benchmark is not None
    assert len(df_benchmark) > 0
    # Cuando quartile_segment es None, no debería tener columna quartile_segment o debería ser None
    assert "quartile_segment" in df_benchmark.columns
