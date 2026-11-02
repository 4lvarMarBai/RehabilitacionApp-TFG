"""Arranca los servicios del equipo servidor y abre la aplicación por HTTPS."""

import ctypes
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CADDY = ROOT / "herramientas" / "caddy.exe"


def port_open(port):
    """Comprueba si el puerto ya tiene un servicio en ejecución."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def responds(url, secure=False):
    """Verifica la respuesta y, en HTTPS, el certificado de nuestro servidor."""
    try:
        context = None
        if secure:
            ca = ROOT / "datos/https/caddy/pki/authorities/local/root.crt"
            if not ca.is_file():
                return False
            context = ssl.create_default_context(cafile=str(ca))
        with urlopen(url, timeout=2, context=context) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def start_service(name, port, url, command, owned, env=None, secure=False):
    """Reutiliza servicios activos; solo detiene los propios si falla el arranque."""
    if port_open(port):
        if not responds(url, secure):
            raise RuntimeError(
                f"El puerto {port} está ocupado, pero {name} no responde. Revisa su terminal o el registro."
            )
        return
    with (LOGS / f"{name}.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    owned.append(process)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"No se pudo iniciar {name}. Consulta logs/{name}.log.")
        if responds(url, secure):
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"{name} no responde tras dos minutos. Consulta logs/{name}.log."
    )


def main():
    LOGS.mkdir(exist_ok=True)
    # El bloqueo evita duplicar el arranque si se pulsa dos veces el acceso.
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, "Local\\RehabilitacionServerStartup")
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(
            0,
            "El servidor ya se está iniciando. Espera unos instantes.",
            "Rehabilitación",
            64,
        )
        return
    owned = []
    try:
        for path in [
            PYTHON,
            CADDY,
            ROOT / "configuracion/.env.api",
            ROOT / "configuracion/Caddyfile",
        ]:
            if not path.is_file():
                raise RuntimeError(
                    f"Falta un archivo necesario: {path.relative_to(ROOT)}"
                )
        start_service(
            "api",
            8000,
            "http://127.0.0.1:8000/health",
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "api.main:app",
                "--env-file",
                "configuracion/.env.api",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ],
            owned,
        )
        start_service(
            "streamlit",
            8501,
            "http://127.0.0.1:8501/_stcore/health",
            [
                str(PYTHON),
                "-m",
                "streamlit",
                "run",
                "cliente/app.py",
                "--server.address=127.0.0.1",
                "--server.port=8501",
                "--server.headless=true",
            ],
            owned,
        )
        env = os.environ.copy()
        env["XDG_DATA_HOME"] = str(ROOT / "datos/https")
        env["XDG_CONFIG_HOME"] = str(ROOT / "datos/https-config")
        start_service(
            "caddy",
            443,
            "https://localhost/_stcore/health",
            [
                str(CADDY),
                "run",
                "--config",
                "configuracion/Caddyfile",
                "--adapter",
                "caddyfile",
            ],
            owned,
            env=env,
            secure=True,
        )
        # Solo se anotan los procesos creados en este arranque, nunca contraseñas.
        if owned:
            (LOGS / "servicios_iniciados.json").write_text(
                json.dumps([p.pid for p in owned]), encoding="utf-8"
            )
        webbrowser.open("https://localhost")
    except Exception as exc:
        for process in reversed(owned):
            if process.poll() is None:
                process.terminate()
        ctypes.windll.user32.MessageBoxW(
            0, str(exc), "No se pudo iniciar Rehabilitación", 16
        )
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
