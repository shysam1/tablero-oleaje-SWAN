"""
Tablero de Oleaje — interfaz web (pywebview).

Arranca la UI estilo macOS en ui/ y expone el motor Python vía api_web.Api.
"""

import os
import sys
import threading
import time
from pathlib import Path

_MODO_GUI = "--gui" in sys.argv
if _MODO_GUI:
    sys.argv = [a for a in sys.argv if a != "--gui"]
    _log_dir = Path(__file__).resolve().parent / "salidas"
    _log_dir.mkdir(exist_ok=True)
    _log_fh = open(_log_dir / "app_web.log", "a", encoding="utf-8")
    sys.stdout = _log_fh
    sys.stderr = _log_fh


def _ocultar_consola(forzado=False):
    if sys.platform != "win32":
        return
    if not forzado:
        try:
            if sys.stdin is not None and sys.stdin.isatty():
                return
        except Exception:
            pass
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def _liberar_consola():
    """Cierra la ventana negra (no solo minimizar): desacopla el proceso de la consola."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass


def _vigilar_consola_oculta():
    for _ in range(80):
        _ocultar_consola(forzado=True)
        time.sleep(0.025)


if _MODO_GUI:
    _ocultar_consola(forzado=True)
    threading.Thread(target=_vigilar_consola_oculta, daemon=True).start()

# Blindaje pythonw / sin consola (mismo criterio que app_tablero).
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

try:
    import webview
except ImportError:
    print("Falta pywebview. Instala con: pip install pywebview")
    sys.exit(1)

from api_web import Api, ruta_ui


def _backend_webview():
    """Backend nativo de pywebview según plataforma."""
    if sys.platform == "darwin":
        return "cocoa"
    if sys.platform == "win32":
        return "edgechromium"
    return None


def _iniciar_webview():
    backend = _backend_webview()
    if backend:
        try:
            webview.start(gui=backend)
            return
        except Exception:
            pass
    webview.start()


def main():
    html = ruta_ui()
    if not html.is_file():
        print(f"No se encontró la interfaz: {html}")
        sys.exit(1)

    api = Api()
    window = webview.create_window(
        "Tablero de Oleaje",
        url=html.as_uri(),
        js_api=api,
        width=960,
        height=700,
        min_size=(520, 580),
        background_color="#f5f5f7",
    )
    api.set_window(window)
    if _MODO_GUI:
        def _liberar_consola_diferida():
            time.sleep(1.5)
            _liberar_consola()

        threading.Thread(target=_liberar_consola_diferida, daemon=True).start()
    else:
        _ocultar_consola(forzado=False)
    _iniciar_webview()


if __name__ == "__main__":
    main()
