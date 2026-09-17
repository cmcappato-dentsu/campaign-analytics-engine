"""Punto de entrada agnóstico para cargar reportes."""

from .sources import default_source, get_source


def load_report(file_path: str, source: str | None = None, skiprows=None):
    """Carga un reporte mediante el adaptador de la fuente indicada."""

    adapter = default_source() if source is None else get_source(source)
    if skiprows is None:
        return adapter.load(file_path)
    return adapter.load(file_path, skiprows=skiprows)


__all__ = ["load_report"]
