"""Identifica los procesos de esta instalación sin depender de paquetes externos."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "logs" / "procesos_servidor.json"


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    return kernel


def _identity(kernel, handle):
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    size = wintypes.DWORD(32768)
    image = ctypes.create_unicode_buffer(size.value)
    if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    return {"created": created, "executable": os.path.normcase(image.value)}


def read_records():
    if not REGISTRY.is_file():
        return []
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if data.get("root") != str(ROOT.resolve()):
        raise ValueError("El registro pertenece a otra instalación.")
    return data["processes"]


def save_records(records):
    REGISTRY.parent.mkdir(exist_ok=True)
    temporary = REGISTRY.with_suffix(".tmp")
    temporary.write_text(json.dumps({"root": str(ROOT.resolve()), "processes": records}), encoding="utf-8")
    temporary.replace(REGISTRY)


def record_process(name, pid):
    kernel = _kernel()
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        record = {"name": name, "pid": pid, **_identity(kernel, handle)}
    finally:
        kernel.CloseHandle(handle)
    records = [item for item in read_records() if item["name"] != name]
    save_records(records + [record])


def stop_record(record):
    """Valida la identidad y cierra su árbol, incluido el intérprete hijo del venv."""
    kernel = _kernel()
    handle = kernel.OpenProcess(0x1000 | 0x0001, False, record["pid"])
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # El proceso ya no existe.
            return False
        raise ctypes.WinError(error)
    try:
        identity = _identity(kernel, handle)
        if any(record[key] != identity[key] for key in ("created", "executable")):
            return False
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if exit_code.value != 259:
            return False
        # Mantener el handle abierto protege la identidad durante la parada.
        command = str(Path(os.environ["WINDIR"]) / "System32" / "taskkill.exe")
        result = subprocess.run(
            [command, "/PID", str(record["pid"]), "/T", "/F"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=20, check=False,
        )
        if result.returncode != 0:
            if kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value != 259:
                return False
            raise OSError("No se pudo detener el servicio registrado.")
        return True
    finally:
        kernel.CloseHandle(handle)


def stop_registered():
    """Detiene entrada HTTPS, interfaz y API, sin cerrar Ollama ni otros programas."""
    records = read_records()
    stopped, pending = [], []
    for name in ("caddy", "streamlit", "api"):
        for record in records:
            if record["name"] != name:
                continue
            try:
                if stop_record(record):
                    stopped.append(name)
            except (OSError, subprocess.TimeoutExpired):
                pending.append(record)
    save_records(pending)
    return stopped, pending
