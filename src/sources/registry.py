"""Registro central de adaptadores de fuentes."""

from dataclasses import dataclass
from typing import Callable

from . import google_ads


@dataclass(frozen=True)
class SourceAdapter:
    """Metadatos y cargador de una fuente de reportes."""

    source_id: str
    label: str
    extensions: tuple[str, ...]
    load: Callable


SOURCE_ADAPTERS = {
    google_ads.SOURCE_ID: SourceAdapter(
        source_id=google_ads.SOURCE_ID,
        label=google_ads.DISPLAY_NAME,
        extensions=google_ads.SUPPORTED_EXTENSIONS,
        load=google_ads.load_report,
    ),
}


def available_sources() -> dict[str, SourceAdapter]:
    """Devuelve las fuentes habilitadas para la aplicación."""

    return SOURCE_ADAPTERS.copy()


def default_source() -> SourceAdapter:
    """Devuelve la primera fuente habilitada como fallback de compatibilidad."""

    try:
        return next(iter(SOURCE_ADAPTERS.values()))
    except StopIteration as error:
        raise ValueError("No hay fuentes de reportes registradas.") from error


def get_source(source_id: str) -> SourceAdapter:
    """Obtiene una fuente o informa que todavía no está registrada."""

    try:
        return SOURCE_ADAPTERS[source_id]
    except KeyError as error:
        available = ", ".join(SOURCE_ADAPTERS) or "ninguna"
        raise ValueError(
            f"Fuente no soportada: {source_id}. Disponibles: {available}."
        ) from error
