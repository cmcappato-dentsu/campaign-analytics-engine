"""Compatibilidad para el cargador histórico de Google Ads."""

from .sources.google_ads import DEFAULT_HEADER_SKIPROWS, load_report


def load_google_ads_report(file_path: str, skiprows: int = DEFAULT_HEADER_SKIPROWS):
    """Carga un reporte de Google Ads mediante su adaptador."""

    return load_report(file_path, skiprows=skiprows)
