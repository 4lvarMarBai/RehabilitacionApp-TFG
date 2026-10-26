import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://127.0.0.1:11434/api/chat",
)
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b-instruct",
)
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))


class OllamaError(RuntimeError):
    """Error al comunicarse con Ollama o procesar su respuesta."""


SYSTEM_PROMPT = """
Eres una herramienta de apoyo para profesionales de rehabilitación.
Analiza únicamente los informes e indicadores proporcionados.

Redacta el resultado en español y con estas secciones:

1. Resumen de la evolución clínica
2. Valoración orientativa del estado actual
3. Valoración global del proceso de rehabilitación
4. Aspectos que el profesional podría revisar, solo si los datos lo justifican

Reglas:
- No inventes datos ni completes información que no aparezca en la entrada.
- Si faltan datos, indica que la información es insuficiente.
- Basa la valoración global en la evolución registrada, las sesiones y los indicadores disponibles.
- Las sugerencias deben ser prudentes y presentarse como aspectos para valorar por el profesional.
- No diagnostiques ni indiques cambios de tratamiento, ejercicios, dosis o sesiones como instrucciones.
- No sustituyas el criterio del médico o del rehabilitador.
"""


def resumir_informes(informes, indicadores):
    """Genera un borrador de seguimiento a partir de los datos proporcionados."""
    entrada = {
        "informes_de_sesion": informes,
        "indicadores_del_seguimiento": indicadores,
    }

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Elabora el informe usando exclusivamente estos datos:\n"
                    + json.dumps(entrada, ensure_ascii=False, default=str)
                ),
            },
        ],
    }

    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
            resultado = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise OllamaError(
            "No se pudo generar el informe con Ollama. Comprueba que Ollama "
            "está abierto y que el modelo está instalado."
        ) from exc

    texto = resultado.get("message", {}).get("content", "").strip()
    if not texto:
        raise OllamaError("Ollama no devolvió un informe.")

    return texto, OLLAMA_MODEL