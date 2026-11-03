"""Límites de la demostración y trazabilidad de los informes generados."""

import hashlib
import json
import os
import re
from urllib.parse import urlsplit

PROMPT_VERSION = "tfg-demo-2026-11-02-v1"
MAX_INPUT_CHARS = 24000


def require_demo(synthetic_data_confirmed):
    """La confirmación del operador no convierte datos reales en ficticios."""
    if os.getenv("AI_USE_MODE", "demo").strip().lower() != "demo":
        raise PermissionError(
            "La IA de esta versión solo está habilitada para demostraciones con datos ficticios. No está autorizada para uso clínico."
        )
    if synthetic_data_confirmed is not True:
        raise PermissionError(
            "Confirma que los informes son ficticios y que no se utilizarán para atender pacientes reales."
        )


def validate_local_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/api/chat"
    ):
        raise ValueError(
            "Ollama debe ejecutarse en el propio servidor mediante una dirección local /api/chat."
        )


def redact_text(value, patient_id=None):
    """Oculta algunos identificadores habituales; no garantiza anonimización."""
    text = str(value or "")
    if patient_id:
        text = re.sub(
            r"(?<!\w)" + re.escape(str(patient_id)) + r"(?!\w)", "[NHC omitido]", text
        )
    text = re.sub(r"\b[0-9]{8}[A-Za-z]\b", "[DNI omitido]", text)
    text = re.sub(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[correo omitido]", text
    )
    return text


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def minimize_payload(value, patient_id=None):
    """Reduce identificadores en textos sin modificar medidas numéricas."""
    if isinstance(value, dict):
        return {key: minimize_payload(item, patient_id) for key, item in value.items()}
    if isinstance(value, list):
        return [minimize_payload(item, patient_id) for item in value]
    return redact_text(value, patient_id) if isinstance(value, str) else value
