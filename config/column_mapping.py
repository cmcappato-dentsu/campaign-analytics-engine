import unicodedata


COLUMN_ALIASES = {
    "date": [
        "Día",
        "Day",
        "Date",
    ],
    "campaign": [
        "Campaña",
        "Campaign",
    ],
    "campaign_status": [
        "Estado de la campaña",
        "Campaign status",
    ],
    "budget": [
        "Presupuesto",
        "Budget",
    ],
    "budget_name": [
        "Nombre del presupuesto",
        "Budget name",
    ],
    "budget_type": [
        "Tipo de presupuesto",
        "Budget type",
    ],
    "currency": [
        "Código de moneda",
        "Currency code",
    ],
    "status": [
        "Estado",
        "Status",
    ],
    "status_reasons": [
        "Motivos del estado",
        "Status reasons",
    ],
    "clicks": [
        "Clics",
        "Clicks",
    ],
    "impressions": [
        "Impr.",
        "Impr",
        "Impressions",
    ],
    "conversions": [
        "Conversiones",
        "Conversions",
    ],
    "conversion_value": [
        "Valor de conv.",
        "Conv. value",
        "Conversion value",
    ],
    "spend": [
        "Costo",
        "Cost",
    ],
    "network": [
        "Red",
        "Network",
    ],
    "bid_strategy": [
        "Estrategia de puja",
        "Bid strategy",
    ],
    "impression_share": [
        "Cuota de impresiones de búsqueda",
        "Search impression share",
    ],
    "lost_is_rank": [
        "Cuota de impresiones perdida por ranking",
        "Search lost IS (rank)",
    ],
    "lost_is_budget": [
        "Cuota de impresiones perdida por presupuesto",
        "Search lost IS (budget)",
    ],
}


def normalize_column_name(column_name: str) -> str:
    """Normaliza un nombre de columna para comparaciones."""

    text = str(column_name).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text
    ).encode(
        "ascii",
        "ignore"
    ).decode(
        "ascii"
    )

    return text


def build_alias_lookup() -> dict:
    """Construye el diccionario alias → nombre canónico."""

    alias_lookup = {}

    for canonical_name, aliases in COLUMN_ALIASES.items():

        for alias in aliases:

            alias_lookup[
                normalize_column_name(alias)
            ] = canonical_name

    return alias_lookup


def rename_columns_to_canonical(df):
    """Renombra columnas ES / EN a nombres canónicos."""

    df = df.copy()

    alias_lookup = build_alias_lookup()

    rename_map = {}

    for original_column in df.columns:

        normalized_column = normalize_column_name(
            original_column
        )

        if normalized_column in alias_lookup:

            rename_map[original_column] = alias_lookup[
                normalized_column
            ]

    return df.rename(columns=rename_map)