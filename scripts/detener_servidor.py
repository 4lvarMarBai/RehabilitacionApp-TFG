"""Permite al administrador detener los servicios iniciados por el acceso directo."""
import ctypes
from scripts.procesos_servidor import stop_registered


def main():
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, "Local\\RehabilitacionServerStartup")
    try:
        if kernel.GetLastError() == 183:
            raise RuntimeError("Hay un arranque o una parada en curso. Espera a que termine.")
        answer = ctypes.windll.user32.MessageBoxW(
            0, "Se detendrán API, aplicación y HTTPS de esta instalación.\n"
            "Los usuarios conectados perderán el acceso. ¿Quieres continuar?",
            "Detener Rehabilitación", 0x24,
        )
        if answer != 6:
            return
        stopped, pending = stop_registered()
        if pending:
            raise RuntimeError("No se pudieron detener todos los servicios. Revisa las terminales o los permisos.")
        message = ("Servidor detenido: " + ", ".join(stopped) + ".") if stopped else (
            "No hay servicios registrados que detener. Este acceso solo controla los servicios "
            "iniciados con la versión actual del acceso Servidor; los arrancados en una terminal se cierran desde ella."
        )
        ctypes.windll.user32.MessageBoxW(0, message, "Rehabilitación", 64)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        ctypes.windll.user32.MessageBoxW(0, str(exc), "No se pudo detener Rehabilitación", 16)
    finally:
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
