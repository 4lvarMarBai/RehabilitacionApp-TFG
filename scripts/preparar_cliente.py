"""Distribuye solo el cliente; nunca copia secretos, servidor ni datos."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "dist" / "RehabilitacionApp"
FILES = (
    "cliente/__init__.py",
    "cliente/app.py",
    "cliente/api_client.py",
    "cliente/ui_helpers.py",
    "comun/__init__.py",
    "comun/config.py",
    "comun/validators.py",
    "requirements.txt",
    "Ruta.bat",
    "OcultaTerminal.vbs",
    "recursos/Rehabilitacion - Usuario.url",
    "recursos/RehabilitacionIcon.ico",
    "README.md",
)


def main():
    if DEST.exists():
        raise SystemExit(
            "El destino ya existe; utiliza una carpeta nueva para no mezclar versiones."
        )
    for name in FILES:
        if not (ROOT / name).is_file():
            raise SystemExit(f"Falta el archivo: {name}")
    for name in FILES:
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    print(
        f"Cliente preparado en {DEST}. Configura API_BASE_URL en .streamlit/secrets.toml del cliente."
    )


if __name__ == "__main__":
    main()
