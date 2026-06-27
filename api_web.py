"""
API Python expuesta a la interfaz web vía pywebview.
"""

import json
import os
import sys
import threading
import traceback
from pathlib import Path

import webview

import motor_web


class Api:
    """Puente JS ↔ motor del tablero."""

    def __init__(self):
        self._window = None
        self._busy = False
        self._lock = threading.Lock()

    def set_window(self, window):
        self._window = window

    # ------------------------------------------------------------------ eventos
    def _emit(self, event, data):
        if not self._window:
            return
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        try:
            self._window.evaluate_js(f"window.dispatchPyEvent({payload})")
        except Exception:
            pass

    def _run_task(self, task_id, func):
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "Ya hay una tarea en curso."}
            self._busy = True

        def worker():
            try:
                result = func()
                self._emit("task_done", {"id": task_id, "ok": True, "result": result})
            except Exception:
                self._emit("task_done", {
                    "id": task_id, "ok": False,
                    "error": traceback.format_exc(),
                })
            finally:
                with self._lock:
                    self._busy = False

        self._emit("task_start", {"id": task_id})
        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def _ventana(self):
        return self._window or webview.active_window()

    # ------------------------------------------------------------------ diálogos
    def elegir_archivo(self, tipo="oleaje"):
        win = self._ventana()
        if not win:
            return None
        mapa = {
            "oleaje": ("Datos de oleaje (*.mat;*.csv;*.nc)",),
            "bot": ("Batimetría (*.bot)",),
            "serie": ("Serie (*.nc;*.mat;*.csv)",),
        }
        tipos = mapa.get(tipo, mapa["oleaje"]) + ("Todos (*.*)",)
        r = win.create_file_dialog(webview.OPEN_DIALOG, file_types=tipos)
        if r:
            motor_web.guardar_config_carpeta("ultima_carpeta_datos", Path(r[0]).parent)
            return r[0]
        return None

    def elegir_carpeta(self, tipo="swan"):
        win = self._ventana()
        if not win:
            return None
        clave = "ultima_carpeta_swan" if tipo == "swan" else "ultima_carpeta_datos"
        inicial = motor_web.obtener_config_carpeta(clave)
        r = win.create_file_dialog(webview.FOLDER_DIALOG, directory=inicial or None)
        if r:
            motor_web.guardar_config_carpeta(clave, r[0])
            return r[0]
        return None

    def abrir_en_explorador(self, ruta):
        if ruta and Path(ruta).exists():
            try:
                os.startfile(str(Path(ruta).parent if Path(ruta).is_file() else ruta))
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": True}

    # ------------------------------------------------------------------ analizar
    def revision_datos(self, ruta):
        return motor_web.revision_datos(ruta)

    def calcular_malla(self, lat, lon, ancho, alto, celda):
        try:
            return {"ok": True, **motor_web.calcular_malla(lat, lon, ancho, alto, celda)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def descargar_era5(self, lat, lon, inicio, fin, viento=True, espectro=False):
        return self._run_task("era5", lambda: motor_web.descargar_era5(
            lat, lon, inicio, fin, con_viento=bool(viento), con_espectro=bool(espectro)))

    def generar_tablero_oleaje(self, ruta):
        return self._run_task("tablero_oleaje",
                              lambda: {"ruta": motor_web.generar_tablero_oleaje(ruta)})

    # ------------------------------------------------------------------ modelar
    def generar_batimetria(self, malla_json, zona_utm, destino, nombre=None):
        malla = json.loads(malla_json) if isinstance(malla_json, str) else malla_json
        return self._run_task("batimetria", lambda: motor_web.generar_batimetria(
            malla, zona_utm, destino, nombre=nombre))

    def derivar_borde(self, ruta_serie, modo, tr=100):
        try:
            return {"ok": True, **motor_web.derivar_borde(ruta_serie, modo, int(tr))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def validar_nido(self, malla_grande_json, malla_nido_json):
        g = json.loads(malla_grande_json)
        n = json.loads(malla_nido_json)
        return motor_web.validar_nido(g, n)

    def validar_correr_swan(self, ctx_json):
        ctx = json.loads(ctx_json) if isinstance(ctx_json, str) else ctx_json
        return motor_web.validar_correr_swan(ctx)

    def escribir_y_correr_swan(self, ctx_json, nombre):
        ctx = json.loads(ctx_json) if isinstance(ctx_json, str) else ctx_json

        def trabajo():
            log_lines = [motor_web.escribir_caso_swan(ctx, nombre or "MiCaso")]

            def log_fn(msg):
                self._emit("log", {"msg": msg})

            def prog_fn(i, n):
                self._emit("progress", {"i": i, "n": n})

            ok = motor_web.correr_swan_carpeta(
                ctx["carpeta_caso"], log_fn=log_fn, progreso_fn=prog_fn)
            log_lines.append(
                "SWAN terminó normalmente." if ok else
                "SWAN terminó CON ERRORES. Revisa .prt/.erf.")
            return {"ok": ok, "log": "\n".join(log_lines),
                    "carpeta": ctx["carpeta_caso"]}

        return self._run_task("swan", trabajo)

    def generar_mapas_swan(self, carpeta):
        return self._run_task("mapas_swan",
                              lambda: {"ruta": motor_web.generar_tablero_swan_mapas(carpeta)})

    def punto_espectral(self, lat, lon, zona_utm):
        try:
            return {"ok": True, "punto": motor_web.punto_espectral_desde_latlon(
                lat, lon, zona_utm)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------ ver
    def info_carpeta_swan(self, carpeta):
        return motor_web.info_carpeta_swan(carpeta)

    def generar_producto_ver(self, ctx_json):
        ctx = json.loads(ctx_json) if isinstance(ctx_json, str) else ctx_json
        carpeta = ctx["carpeta"]
        utm = ctx.get("utm_large")
        nonst = ctx.get("nonst")

        def trabajo():
            if nonst:
                def prog(i, n):
                    self._emit("progress", {"i": i, "n": n})
                ruta = motor_web.generar_video_swan(carpeta, utm_large=utm, progreso_fn=prog)
            else:
                ruta = motor_web.generar_tablero_swan_mapas(carpeta, utm_large=utm)
            return {"ruta": ruta}

        return self._run_task("ver_producto", trabajo)

    # ------------------------------------------------------------------ avanzado
    def despachar_avanzado(self, ruta, utm_x=None, utm_y=None):
        utm = None
        try:
            if utm_x not in (None, "") and utm_y not in (None, ""):
                utm = (float(utm_x), float(utm_y))
        except ValueError:
            utm = None

        def trabajo():
            def prog(i, n):
                self._emit("progress", {"i": i, "n": n})
            buffer = []
            import io as _io
            from contextlib import redirect_stdout
            with redirect_stdout(_io.StringIO()) as _:
                out = motor_web.despachar_avanzado(ruta, utm_large=utm, progreso_fn=prog)
            return {"ruta": out}

        return self._run_task("avanzado", trabajo)

    def abrir_procesar_swan_legacy(self):
        """Abre la ventana tkinter SWAN en un hilo aparte (herramienta legacy)."""
        def run_tk():
            import tkinter as tk
            import estilo
            import gui_swan
            root = tk.Tk()
            estilo.aplicar_tema(root)
            root.withdraw()
            win = gui_swan.VentanaSwan(root)
            win.protocol("WM_DELETE_WINDOW", root.quit)
            root.mainloop()
        threading.Thread(target=run_tk, daemon=True).start()
        return {"ok": True}


def ruta_ui():
    return Path(__file__).resolve().parent / "ui" / "index.html"
