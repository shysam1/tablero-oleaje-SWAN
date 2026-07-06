"""
API Python expuesta a la interfaz web vía pywebview.
"""

import json
import queue
import sys
import threading
from pathlib import Path

import webview

import io_era5
import motor_web
import sistema


class Api:
    """Puente JS ↔ motor del tablero."""

    def __init__(self):
        self._window = None
        self._busy = False
        self._lock = threading.Lock()
        self._eventos = queue.Queue()
        self._swan_cancel = threading.Event()
        self._swan_proc = None
        self._swan_lock = threading.Lock()

    def set_window(self, window):
        self._window = window

    # ------------------------------------------------------------------ eventos
    def _emit(self, event, data):
        """Encola evento para el hilo GUI (poll_eventos desde JS)."""
        self._eventos.put({"event": event, "data": data})

    def poll_eventos(self):
        """Drena la cola de eventos hacia la UI (llamar periódicamente desde JS)."""
        enviados = 0
        while self._window:
            try:
                item = self._eventos.get_nowait()
            except queue.Empty:
                break
            payload = json.dumps(item, ensure_ascii=False)
            try:
                self._window.evaluate_js(f"window.dispatchPyEvent({payload})")
                enviados += 1
            except Exception:
                self._eventos.put(item)
                break
        return {"ok": True, "n": enviados}

    def _parse_json(self, val, etiqueta="payload"):
        if isinstance(val, dict):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"{etiqueta} JSON inválido.") from exc

    def _error_tarea(self, exc):
        """Mensaje seguro para la UI (sin rutas ni trazas internas)."""
        if isinstance(exc, (ValueError, RuntimeError)):
            return str(exc)
        return exc.__class__.__name__

    def _run_task(self, task_id, func):
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "Ya hay una tarea en curso."}
            self._busy = True

        def worker():
            try:
                result = func()
                self._emit("task_done", {"id": task_id, "ok": True, "result": result})
            except Exception as exc:
                self._emit("task_done", {
                    "id": task_id, "ok": False,
                    "error": self._error_tarea(exc),
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
            "raster": ("Raster batimetría (*.nc)",),
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
        try:
            p = motor_web._ruta_usuario(ruta, "Ruta", debe_existir=True)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        try:
            if p.is_file():
                sistema.abrir_carpeta(p.parent)
            else:
                sistema.abrir_carpeta(p)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def abrir_url_externa(self, url):
        """Abre un enlace HTTPS en el navegador del sistema."""
        url = (url or "").strip()
        if not url.startswith("https://"):
            return {"ok": False, "error": "Solo se permiten URLs https."}
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def cancelar_swan(self):
        """Solicita abortar la corrida SWAN en curso (web)."""
        self._swan_cancel.set()
        with self._swan_lock:
            proc = self._swan_proc
        if proc is not None:
            import swan_runner
            swan_runner.matar_proceso_arbol(proc)
        return {"ok": True}

    def ruta_existe(self, ruta):
        try:
            p = motor_web._ruta_usuario(ruta, "Ruta", debe_existir=False)
            return p.exists()
        except ValueError:
            return False

    # ------------------------------------------------------------------ analizar
    def revision_datos(self, ruta):
        return motor_web.revision_datos(ruta)

    def calcular_malla(self, lat, lon, ancho, alto, celda):
        try:
            return {"ok": True, **motor_web.calcular_malla(lat, lon, ancho, alto, celda)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def estado_cds_credenciales(self):
        return {"ok": True, **io_era5.estado_credenciales_cds()}

    def guardar_cds_credenciales(self, url, key=""):
        try:
            datos = io_era5.guardar_credenciales_cds(url, key or None)
            return {"ok": True, **datos}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def probar_cds_credenciales(self, url="", key=""):
        try:
            datos = io_era5.probar_credenciales_cds(
                url or None, key or None)
            return {"ok": True, **datos}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def descargar_era5(self, lat, lon, inicio, fin, viento=True, espectro=False):
        if not io_era5.leer_credenciales_cds():
            return {"ok": False, "error": "Faltan credenciales ERA5"}
        try:
            motor_web._validar_era5(lat, lon, inicio, fin)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        def log(msg):
            self._emit("log", {"msg": msg})

        def trabajo():
            return motor_web.descargar_era5(
                lat, lon, inicio, fin, con_viento=bool(viento),
                con_espectro=bool(espectro), log_fn=log)

        return self._run_task("era5", trabajo)

    def generar_tablero_oleaje(self, ruta):
        try:
            motor_web._ruta_usuario(ruta, "Archivo", debe_existir=True)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        def trabajo():
            out = motor_web.generar_tablero_oleaje(ruta, abrir=False)
            return {"ruta": out, "preview": motor_web.preview_archivo(out)}

        return self._run_task("tablero_oleaje", trabajo)

    def comparar_series(self, ruta_a, ruta_b):
        try:
            return {"ok": True, **motor_web.comparar_series(ruta_a, ruta_b)}
        except (ValueError, TypeError) as e:
            return {"ok": False, "error": str(e)}

    def revision_con_referencia(self, ruta, ruta_ref=""):
        res = motor_web.revision_datos(ruta)
        if ruta_ref:
            try:
                res["comparacion"] = motor_web.comparar_series(ruta, ruta_ref)
            except ValueError as e:
                res["comparacion"] = {"error": str(e)}
        return res

    def listar_recientes(self):
        return {"ok": True, "items": motor_web.listar_recientes()}

    def listar_cache_era5(self):
        return {"ok": True, "items": motor_web.listar_cache_era5()}

    def eliminar_cache_era5(self, carpeta):
        try:
            return motor_web.eliminar_cache_era5(carpeta)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def guardar_preferencias(self, prefs_json):
        try:
            prefs = self._parse_json(prefs_json, "preferencias")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        motor_web.guardar_preferencias(prefs)
        return {"ok": True}

    def obtener_preferencias(self):
        return {"ok": True, "prefs": motor_web.obtener_preferencias()}

    def preview_malla(self, malla_json, lat=None, lon=None):
        try:
            malla = self._parse_json(malla_json, "malla")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        try:
            return {"ok": True, "img": motor_web.preview_malla(malla, lat, lon)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def preview_batimetria(self, ruta_bot, malla_json):
        try:
            malla = self._parse_json(malla_json, "malla")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        try:
            return {"ok": True, "img": motor_web.preview_batimetria(ruta_bot, malla)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def validar_bot_malla(self, ruta_bot, malla_json):
        try:
            malla = self._parse_json(malla_json, "malla")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        try:
            return motor_web.validar_bot_malla(ruta_bot, malla)
        except Exception as e:
            return {"ok": False, "error": self._error_tarea(e)}

    def preview_archivo(self, ruta):
        try:
            img = motor_web.preview_archivo(ruta)
            return {"ok": True, "img": img}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def info_aplicacion(self):
        return {"ok": True, **motor_web.info_aplicacion()}

    def guardar_sesion_wizard(self, wizard, step, ctx_json):
        try:
            ctx = self._parse_json(ctx_json, "contexto wizard")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        motor_web.guardar_sesion_wizard(wizard, int(step), ctx)
        return {"ok": True}

    def cargar_sesion_wizard(self):
        ses = motor_web.cargar_sesion_wizard()
        return {"ok": True, "sesion": ses}

    def limpiar_sesion_wizard(self):
        motor_web.limpiar_sesion_wizard()
        return {"ok": True}

    def abrir_archivo(self, ruta):
        try:
            p = motor_web._ruta_usuario(ruta, "Archivo", debe_existir=True)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        try:
            sistema.abrir_archivo(p)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    # ------------------------------------------------------------------ modelar
    def generar_batimetria(self, malla_json, zona_utm, destino, nombre=None, raster_ruta=None):
        try:
            malla = self._parse_json(malla_json, "malla")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if not destino:
            return {"ok": False, "error": "Falta carpeta destino."}
        return self._run_task("batimetria", lambda: motor_web.generar_batimetria(
            malla, zona_utm, destino, nombre=nombre, raster_ruta=raster_ruta or None))

    def listar_plantillas_malla(self):
        return {"ok": True, "plantillas": motor_web.listar_plantillas_malla()}

    def evaluar_resolucion_malla(self, malla_json):
        try:
            malla = self._parse_json(malla_json, "malla")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, **motor_web.evaluar_resolucion_malla(malla)}

    def preview_malla_anidada(self, malla_grande_json, malla_nido_json):
        try:
            g = self._parse_json(malla_grande_json, "malla grande")
            n = self._parse_json(malla_nido_json, "malla nido")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        try:
            return {"ok": True, "img": motor_web.preview_malla_anidada(g, n)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def checklist_correr_swan(self, ctx_json):
        try:
            ctx = self._parse_json(ctx_json, "contexto SWAN")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        items = motor_web.checklist_correr_swan(ctx)
        return {"ok": True, "items": items, "listo": all(i["ok"] for i in items)}

    def abrir_logs_swan(self, carpeta):
        try:
            return motor_web.abrir_logs_swan(carpeta)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def derivar_borde(self, ruta_serie, modo, tr=100):
        try:
            return {"ok": True, **motor_web.derivar_borde(ruta_serie, modo, int(tr))}
        except (ValueError, TypeError) as e:
            return {"ok": False, "error": str(e)}

    def estado_cache_era5_borde(self, lat, lon, inicio, fin):
        try:
            return {"ok": True, **motor_web.estado_cache_era5_borde(
                lat, lon, inicio, fin)}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def derivar_borde_era5(self, lat, lon, inicio, fin, modo, tr=100,
                           descargar_si_falta=False):
        """
        Deriva borde desde ERA5 en el punto. Si no hay caché y descargar_si_falta,
        lanza tarea en background (descarga + derivación).
        """
        try:
            motor_web._validar_era5(lat, lon, inicio, fin)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if descargar_si_falta:
            st = motor_web.estado_cache_era5_borde(lat, lon, inicio, fin)
            if not st["en_cache"]:
                if not io_era5.leer_credenciales_cds():
                    return {"ok": False, "error": "Faltan credenciales ERA5"}

                def log(msg):
                    self._emit("log", {"msg": msg})

                def trabajo():
                    motor_web.descargar_era5(
                        lat, lon, inicio, fin, con_viento=False,
                        con_espectro=False, log_fn=log)
                    return motor_web.derivar_borde_era5(
                        lat, lon, inicio, fin, modo, int(tr))

                return self._run_task("borde_era5", trabajo)
        try:
            return {"ok": True, **motor_web.derivar_borde_era5(
                lat, lon, inicio, fin, modo, int(tr))}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def validar_nido(self, malla_grande_json, malla_nido_json):
        try:
            g = self._parse_json(malla_grande_json, "malla grande")
            n = self._parse_json(malla_nido_json, "malla nido")
        except ValueError as e:
            return {"errores": [str(e)], "avisos": []}
        try:
            return motor_web.validar_nido(g, n)
        except Exception as e:
            return {"errores": [self._error_tarea(e)], "avisos": []}

    def validar_correr_swan(self, ctx_json):
        try:
            ctx = self._parse_json(ctx_json, "contexto SWAN")
        except ValueError as e:
            return {"errores": [str(e)], "avisos": []}
        try:
            return motor_web.validar_correr_swan(ctx)
        except Exception as e:
            return {"errores": [self._error_tarea(e)], "avisos": []}

    def escribir_y_correr_swan(self, ctx_json, nombre):
        try:
            ctx = self._parse_json(ctx_json, "contexto SWAN")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if "dominios" not in ctx or "carpeta_caso" not in ctx:
            return {"ok": False, "error": "Contexto SWAN incompleto."}

        def trabajo():
            self._swan_cancel.clear()
            self._swan_proc = None
            log_lines = [motor_web.escribir_caso_swan(ctx, nombre or "MiCaso")]

            def log_fn(msg):
                self._emit("log", {"msg": msg})

            def prog_fn(i, n):
                self._emit("progress", {"i": i, "n": n})

            def on_proc(proc):
                with self._swan_lock:
                    self._swan_proc = proc

            ok = motor_web.correr_swan_carpeta(
                ctx["carpeta_caso"], log_fn=log_fn, progreso_fn=prog_fn,
                on_proc=on_proc, cancelado=self._swan_cancel.is_set)
            with self._swan_lock:
                self._swan_proc = None
            if self._swan_cancel.is_set():
                log_lines.append("Corrida SWAN cancelada por el usuario.")
            else:
                log_lines.append(
                    "SWAN terminó normalmente." if ok else
                    "SWAN terminó CON ERRORES. Revisa .prt/.erf.")
            return {"ok": ok and not self._swan_cancel.is_set(),
                    "log": "\n".join(log_lines),
                    "carpeta": ctx["carpeta_caso"],
                    "cancelado": self._swan_cancel.is_set()}

        return self._run_task("swan", trabajo)

    def generar_mapas_swan(self, carpeta):
        def trabajo():
            out = motor_web.generar_tablero_swan_mapas(carpeta, abrir=False)
            return {"ruta": out, "preview": motor_web.preview_archivo(out)}
        return self._run_task("mapas_swan", trabajo)

    def punto_espectral(self, lat, lon, zona_utm):
        try:
            return {"ok": True, "punto": motor_web.punto_espectral_desde_latlon(
                lat, lon, zona_utm)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------ ver
    def info_carpeta_swan(self, carpeta):
        try:
            return {"ok": True, **motor_web.info_carpeta_swan(carpeta)}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": self._error_tarea(e)}

    def generar_producto_ver(self, ctx_json):
        try:
            ctx = self._parse_json(ctx_json, "contexto ver")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if "carpeta" not in ctx:
            return {"ok": False, "error": "Falta la carpeta de la corrida."}
        carpeta = ctx["carpeta"]
        utm = ctx.get("utm_large")
        nonst = ctx.get("nonst")

        def trabajo():
            if nonst:
                def prog(i, n):
                    self._emit("progress", {"i": i, "n": n})
                ruta = motor_web.generar_video_swan(
                    carpeta, utm_large=utm, progreso_fn=prog, abrir=False)
            else:
                ruta = motor_web.generar_tablero_swan_mapas(
                    carpeta, utm_large=utm, abrir=False)
            return {"ruta": ruta, "preview": motor_web.preview_archivo(ruta)}

        return self._run_task("ver_producto", trabajo)

    # ------------------------------------------------------------------ avanzado
    def despachar_avanzado(self, ruta, utm_x=None, utm_y=None):
        utm = None
        try:
            if utm_x not in (None, "") and utm_y not in (None, ""):
                ux, uy = float(utm_x), float(utm_y)
                utm = (ux, uy)
        except ValueError:
            utm = None

        def trabajo():
            def prog(i, n):
                self._emit("progress", {"i": i, "n": n})
            ruta = motor_web.despachar_avanzado(ruta, utm_large=utm, progreso_fn=prog)
            # despachar abre el archivo; regeneramos preview sin reabrir
            return {"ruta": ruta, "preview": motor_web.preview_archivo(ruta)}

        return self._run_task("avanzado", trabajo)

    def correr_swan_existente(self, carpeta):
        if not carpeta:
            return {"ok": False, "error": "Falta la carpeta del caso."}

        def trabajo():
            self._swan_cancel.clear()
            self._swan_proc = None

            def log_fn(msg):
                self._emit("log", {"msg": msg})

            def prog_fn(i, n):
                self._emit("progress", {"i": i, "n": n})

            def on_proc(proc):
                with self._swan_lock:
                    self._swan_proc = proc

            ok = motor_web.correr_swan_carpeta(
                carpeta, log_fn=log_fn, progreso_fn=prog_fn,
                on_proc=on_proc, cancelado=self._swan_cancel.is_set)
            with self._swan_lock:
                self._swan_proc = None
            msg = ("SWAN terminó normalmente." if ok else
                   "SWAN terminó CON ERRORES. Revisa .prt/.erf.")
            if self._swan_cancel.is_set():
                msg = "Corrida SWAN cancelada por el usuario."
            return {"ok": ok and not self._swan_cancel.is_set(),
                    "log": msg, "carpeta": carpeta,
                    "cancelado": self._swan_cancel.is_set()}

        return self._run_task("swan_existente", trabajo)


def ruta_ui():
    return Path(__file__).resolve().parent / "ui" / "index.html"
