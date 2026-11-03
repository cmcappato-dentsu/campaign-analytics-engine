import pandas as pd

from config.column_mapping import (
    rename_columns_to_canonical
)
from src.loader import load_report
from src.sources import available_sources


def test_spanish_columns_are_mapped():

    df = pd.DataFrame({
        "Campaña": ["Campaign A"],
        "Clics": [100],
        "Impr.": [1000],
        "Conversiones": [5],
        "Costo": [200],
    })

    result = rename_columns_to_canonical(df)

    assert "campaign" in result.columns
    assert "clicks" in result.columns
    assert "impressions" in result.columns
    assert "conversions" in result.columns
    assert "spend" in result.columns


def test_english_columns_are_mapped():

    df = pd.DataFrame({
        "Campaign": ["Campaign A"],
        "Clicks": [100],
        "Impressions": [1000],
        "Conversions": [5],
        "Cost": [200],
    })

    result = rename_columns_to_canonical(df)

    assert "campaign" in result.columns
    assert "clicks" in result.columns
    assert "impressions" in result.columns
    assert "conversions" in result.columns
    assert "spend" in result.columns


def test_sources_are_exposed_through_registry():
    sources = available_sources()

    assert "google_ads" in sources
    assert sources["google_ads"].label == "Google Ads"


def test_loader_maps_spanish_search_lost_share_aliases(tmp_path):
    report = tmp_path / "spanish_search.csv"
    report.write_text(
        "Día,Campaña,Red (con asociados de búsqueda),Impr.,Clics,Conversiones,"
        "Valor de conv.,Código de moneda,Costo,"
        "% impr. perdidas de la Búsqueda (presupuesto),"
        "% impr. perdidas de la Búsqueda (ranking),"
        "%\xa0impr. perdidas parte\xa0sup. búsqueda (presupuesto)\n"
        '2026-08-01,Campaign A,Búsqueda de Google,"2,877",430,165.44,'
        '"181,709.52",ARS,107276.05,0.00%,70.97%,0.00%\n',
        encoding="utf-8",
    )

    result = load_report(str(report), source="google_ads")

    assert "lost_is_budget" in result.columns
    assert "lost_is_rank" in result.columns
    assert "network" in result.columns
    assert result.loc[0, "lost_is_budget"] == "0.00%"
    assert result.loc[0, "lost_is_rank"] == "70.97%"


def test_generic_loader_can_use_registered_source(tmp_path):
    report = tmp_path / "report.csv"
    report.write_text(
        "Día,Campaña,Impr.,Clics,Conversiones,Código de moneda,Costo\n"
        '2026-08-01,Campaign A,"1,000",100,5,ARS,200\n',
        encoding="utf-8",
    )

    result = load_report(str(report), source="google_ads")

    assert len(result) > 0
    assert {"date", "campaign", "spend"}.issubset(result.columns)


def test_loader_detects_header_without_preamble(tmp_path):
    report = tmp_path / "no_preamble.csv"
    report.write_text(
        "Día,Campaña,Impr.,Clics,Conversiones,Código de moneda,Costo\n"
        '2026-08-01,Campaign A,"1,000",100,5,ARS,200\n',
        encoding="utf-8",
    )

    result = load_report(str(report), source="google_ads")

    assert list(result.columns)[0] == "date"
    assert len(result) == 1


def test_loader_skips_title_and_date_range_preamble(tmp_path):
    report = tmp_path / "with_preamble.csv"
    report.write_text(
        "Test - BI (Search)\n"
        "1 de agosto de 2026 - 31 de agosto de 2026\n"
        "Día,Campaña,Impr.,Clics,Conversiones,Código de moneda,Costo\n"
        '2026-08-01,Campaign A,"2,877",430,165.00,ARS,107276.05\n',
        encoding="utf-8",
    )

    result = load_report(str(report), source="google_ads")

    assert list(result.columns)[0] == "date"
    assert len(result) == 1
    assert result.loc[0, "impressions"] == "2,877"


def test_loader_unwraps_rows_quoted_as_a_single_field(tmp_path):
    report = tmp_path / "nested_quotes.csv"
    quoted_row = (
        '2026-08-01,Campaign A,Búsqueda,Búsqueda de Google,"18,285",78.95%,2.88%,'
        '"7,963",239.99,"30,476,711.44",ARS,997888.49'
    )
    report.write_text(
        "Día,Campaña,Tipo de campaña,Red,Impr.,%impr.,"
        "% perdidas,Clics,Conversiones,Valor de conv.,"
        "Código de moneda,Costo\n"
        + '"'
        + quoted_row.replace('"', '""')
        + '"\n'
        + "2026-08-01,Campaign B,Búsqueda,Red de Display,40, --, --,3,0.00,0.00,ARS,160.89\n",
        encoding="utf-8",
    )

    result = load_report(str(report), source="google_ads")

    assert len(result) == 2
    assert result.loc[0, "campaign"] == "Campaign A"
    assert result.loc[0, "clicks"] == "7,963"
    assert result.loc[1, "campaign"] == "Campaign B"


def test_loader_reports_when_header_cannot_be_found(tmp_path):
    report = tmp_path / "unknown.csv"
    report.write_text("foo,bar\n1,2\n", encoding="utf-8")

    try:
        load_report(str(report), source="google_ads")
    except ValueError as error:
        assert "encabezados" in str(error)
    else:
        raise AssertionError("Se esperaba un ValueError por encabezados ausentes")
