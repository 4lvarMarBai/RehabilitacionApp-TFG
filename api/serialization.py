"""Conversión de fechas y números para conservar sus tipos al enviarlos por JSON."""

from datetime import date, datetime, time
from decimal import Decimal


def encode(value):
    """Conserva los tipos de fecha que el calendario de Streamlit necesita."""
    if isinstance(value, datetime):
        return {"__api_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__api_type__": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"__api_type__": "time", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    return value


def table(result):
    columns, rows = result
    return encode({"columns": columns, "rows": rows})
