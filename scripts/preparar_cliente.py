"""Prepara el acceso por navegador sin código del servidor ni secretos."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "dist" / "RehabilitacionApp"
FILES = (
    "recursos/Rehabilitacion - Usuario.url",
    "recursos/certificado_https_local.crt",
    "licencia",
)


def main():
    if DEST.exists():
        raise SystemExit("La carpeta de destino ya existe. Utiliza una carpeta nueva para no mezclar instalaciones.")
    for name in FILES:
        if not (ROOT / name).is_file():
            raise SystemExit(f"Falta {name}. Crea los accesos y exporta el certificado público antes de preparar el paquete.")
    DEST.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(ROOT / name, DEST / Path(name).name)
    print(f"Acceso preparado en {DEST}. Instala el certificado público en el puesto del usuario y abre el enlace HTTPS. No se necesita Python en ese equipo.")


if __name__ == "__main__":
    main()
