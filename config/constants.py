# Columnas obligatorias para analizar un reporte
REQUIRED_COLUMNS = [
    "date",
    "campaign",
    "clicks",
    "impressions",
    "conversions",
    "spend",
]


# Columnas opcionales
OPTIONAL_COLUMNS = [
    "campaign_status",
    "budget",
    "budget_name",
    "budget_type",
    "currency",
    "status",
    "status_reasons",
    "conversion_value",
    "network",
    "bid_strategy",
    "impression_share",
    "lost_is_rank",
    "lost_is_budget",
]


# Filas iniciales del reporte de ejemplo
DEFAULT_HEADER_SKIPROWS = 2