"""Prueba optativa de WebView2 y análisis completo sobre una entrega aislada."""

import argparse
import json
import sys
import threading
import time
from pathlib import Path


def main():
    for salida in (sys.stdout, sys.stderr):
        if hasattr(salida, "reconfigure"):
            salida.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entrega", type=Path)
    args = parser.parse_args()
    entrega = args.entrega.resolve()
    sys.path.insert(0, str(entrega))

    import numpy as np
    import pandas as pd
    import config
    import io_era5
    import motor_web
    import webview
    from api_web import Api, ruta_ui

    config._RUTA = entrega / "salidas" / "config_prueba.json"
    config._RUTA.parent.mkdir(parents=True, exist_ok=True)
    # El humo de escritorio no necesita consultar la cuenta personal de CDS.
    io_era5.estado_credenciales_cds = lambda: {"configurado": False}
    tiempo = pd.date_range("2024-01-01", periods=240, freq="3h")
    fase = np.linspace(0, 8 * np.pi, len(tiempo))
    datos = pd.DataFrame({
        "anio": tiempo.year, "mes": tiempo.month, "dia": tiempo.day,
        "hora": tiempo.hour, "Hs": 2 + 0.5 * np.sin(fase),
        "Tp": 9 + np.cos(fase), "Dir": (280 + 20 * np.sin(fase)) % 360,
    })
    ruta = entrega / "salidas" / "DEMO_SINTETICA_AUDITORIA.csv"
    datos.to_csv(ruta, index=False)
    api = Api()
    ventana = webview.create_window("Tablero de Oleaje · prueba aislada", ruta_ui().as_uri(),
                                   js_api=api, width=960, height=700)
    api.set_window(ventana)
    resultado = {"ok": False, "entrega": str(entrega)}
    terminado = threading.Event()

    def esperar(expresion, segundos=30):
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            valor = ventana.evaluate_js(expresion)
            if valor:
                return valor
            time.sleep(0.1)
        raise TimeoutError(f"La interfaz no completó: {expresion}")

    def comprobar():
        try:
            esperar("document.querySelectorAll('.card').length === 4")
            ventana.evaluate_js("window.humoApi = null; pywebview.api.info_aplicacion().then(r => window.humoApi = r)")
            resultado["puente"] = esperar("window.humoApi")
            assert resultado["puente"]["ok"]
            revision = motor_web.revision_datos(ruta)
            assert revision["ok"], revision
            resultado["pasos"] = revision["n_pasos"]
            contexto = json.dumps({"ruta_datos": str(ruta), "revision_ok": True})
            ventana.evaluate_js(f"Tablero.startWizard('analizar', {contexto}, 2)")
            ventana.evaluate_js("document.getElementById('gen-tablero').click()")
            # Abrir la imagen asociada es una acción de UI; se evita abrir otra app durante el humo.
            esperar("Tablero.state.tableroGenerado", segundos=90)
            resultado["preview"] = bool(ventana.evaluate_js("Boolean(document.querySelector('#preview-box img')?.src.startsWith('data:image/'))"))
            assert resultado["preview"]
            resultado["ok"] = True
        except Exception as exc:
            resultado["error"] = repr(exc)
        finally:
            terminado.set()
            ventana.destroy()

    api.abrir_archivo = lambda ruta: {"ok": True}
    def vigilar():
        if not terminado.wait(120):
            resultado["error"] = "Tiempo máximo de la prueba de escritorio agotado."
            ventana.destroy()

    threading.Thread(target=vigilar, daemon=True).start()
    webview.start(comprobar, gui="edgechromium")
    destino = entrega / "salidas" / "verificacion_escritorio.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
