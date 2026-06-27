"""
Ventana "Procesar SWAN" de la app: el paso previo a graficar.

Dos modos en pestañas, sobre un log en vivo común:
  - Correr caso existente: elige una carpeta con el/los .swn ya armados y los
    ejecuta con swan_runner (orden grande→nido), mostrando la salida de SWAN.
  - Armar y correr: formulario con los parámetros esenciales (malla, batimetría,
    borde, salidas); genera el .swn con swan_builder y lo corre.

Al terminar, la carpeta queda con las salidas listas para el botón "Crear" de la
ventana principal. El cálculo corre en un hilo para no congelar la interfaz.
"""

import os
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

import swan_runner
import swan_builder
import config
import io_oleaje
import borde_oleaje
import io_batimetria
import geo_malla


def dialogo_condicion(parent):
    """
    Diálogo modal para elegir la condición de borde. Devuelve (modo, T) o None si
    se cancela. T solo aplica al modo 'retorno'. Compartido por las dos vías
    (formulario SWAN y ventana ERA5).
    """
    win = tk.Toplevel(parent)
    win.title("Condición de borde")
    win.transient(parent)
    win.grab_set()
    modo = tk.StringVar(value="retorno")
    tr = tk.StringVar(value="100")
    for val, txt in (("retorno", "Periodo de retorno (Gumbel)"),
                     ("maximo", "Máximo observado"),
                     ("reinante", "Oleaje reinante (p50)")):
        ttk.Radiobutton(win, text=txt, variable=modo, value=val).pack(
            anchor="w", padx=12, pady=2)
    fila = ttk.Frame(win)
    fila.pack(anchor="w", padx=12, pady=(4, 0))
    ttk.Label(fila, text="T [años] (solo retorno):").pack(side="left")
    ttk.Entry(fila, textvariable=tr, width=6).pack(side="left", padx=(4, 0))

    elegido = {}

    def aceptar():
        try:
            elegido["tr"] = int(float(tr.get()))
        except ValueError:
            elegido["tr"] = 100
        elegido["modo"] = modo.get()
        win.destroy()

    ttk.Button(win, text="Aceptar", command=aceptar).pack(pady=10, ipadx=8)
    parent.wait_window(win)
    if "modo" not in elegido:
        return None
    return elegido["modo"], elegido["tr"]


def dialogo_latlon(parent):
    """
    Diálogo para definir la malla por lat/lon (centro + tamaño + celda).
    Devuelve un dict {lat, lon, ancho, alto, celda} (strings) o None si se cancela.
    """
    win = tk.Toplevel(parent)
    win.title("Definir malla por lat/lon")
    win.transient(parent)
    win.grab_set()
    campos = {}
    for etiqueta, clave, valor in (
            ("Latitud centro", "lat", "-32.97"),
            ("Longitud centro", "lon", "-71.55"),
            ("Ancho [km]", "ancho", "8"),
            ("Alto [km]", "alto", "8"),
            ("Tamaño de celda [m]", "celda", "100")):
        fila = ttk.Frame(win)
        fila.pack(fill="x", padx=10, pady=3)
        ttk.Label(fila, text=etiqueta, width=20).pack(side="left")
        var = tk.StringVar(value=valor)
        ttk.Entry(fila, textvariable=var, width=12).pack(side="left")
        campos[clave] = var

    elegido = {}

    def aceptar():
        elegido.update({k: v.get() for k, v in campos.items()})
        win.destroy()

    ttk.Button(win, text="Calcular", command=aceptar).pack(pady=10, ipadx=8)
    parent.wait_window(win)
    return elegido or None


class VentanaSwan(tk.Toplevel):
    """Ventana modal-ligera para generar y/o correr corridas SWAN."""

    LADOS = ("N", "S", "E", "W")
    VARIABLES = ("Hs", "Tp", "Dir", "Setup")

    def __init__(self, master=None, borde_inicial=None):
        super().__init__(master)
        self.title("Procesar SWAN")
        self.geometry("720x640")
        self.minsize(640, 560)
        self._proc = None                  # proceso SWAN en curso (para cancelar)
        self._cancelar = threading.Event()
        self._construir()
        # Cerrar la ventana mientras corre SWAN debe cancelar la corrida y matar el
        # proceso: si no, queda un swan.exe huérfano y los callbacks del hilo tocan
        # widgets ya destruidos.
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        if borde_inicial:
            self.aplicar_borde(borde_inicial)
            self.nb.select(1)        # deja activa la pestaña "Armar y correr"

    def _vivo(self):
        """True si la ventana sigue existiendo (no tocar widgets ya destruidos)."""
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _marshal(self, func, *args):
        """
        Agenda func(*args) en el hilo de la GUI desde un hilo de trabajo. Ignora
        en silencio si la ventana ya se cerró (evita TclError "invalid command").
        """
        def _run():
            if self._vivo():
                func(*args)
        try:
            self.after(0, _run)
        except tk.TclError:
            pass

    def _al_cerrar(self):
        """Cancela la corrida en curso (mata swan.exe) y cierra la ventana."""
        self._cancelar.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self.destroy()

    # ------------------------------------------------------------------ UI
    def _construir(self):
        marco = ttk.Frame(self, padding=10)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Procesar SWAN",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(marco, text="Corre el modelo SWAN y deja la carpeta lista para "
                  "graficar con «Crear».", foreground="#555").pack(anchor="w",
                                                                   pady=(0, 8))

        nb = ttk.Notebook(marco)
        self.nb = nb
        nb.pack(fill="x")
        nb.add(self._pestana_existente(nb), text="Correr caso existente")
        nb.add(self._pestana_nuevo(nb), text="Armar y correr")

        # Estado + progreso + cancelar + log, compartidos por ambas pestañas.
        fila_e = ttk.Frame(marco)
        fila_e.pack(fill="x", pady=(8, 0))
        self.estado = ttk.Label(fila_e, text="Listo.", foreground="#1f6feb")
        self.estado.pack(side="left")
        self.boton_cancelar = ttk.Button(fila_e, text="Cancelar",
                                         command=self._cancelar_corrida,
                                         state="disabled")
        self.boton_cancelar.pack(side="right")
        self.progreso = ttk.Progressbar(marco, mode="determinate", maximum=100)
        self.progreso.pack(fill="x", pady=(4, 0))
        self.log = scrolledtext.ScrolledText(marco, height=14, font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(8, 0))

    def _pestana_existente(self, nb):
        f = ttk.Frame(nb, padding=10)
        self.carpeta_exist = tk.StringVar()
        fila = ttk.Frame(f)
        fila.pack(fill="x")
        ttk.Entry(fila, textvariable=self.carpeta_exist).pack(
            side="left", fill="x", expand=True)
        ttk.Button(fila, text="Carpeta…",
                   command=self._elegir_carpeta_exist).pack(side="left", padx=(6, 0))
        self.casos_lbl = ttk.Label(f, text="", foreground="#555")
        self.casos_lbl.pack(anchor="w", pady=(6, 0))
        self.boton_correr = ttk.Button(f, text="Correr SWAN",
                                       command=self._correr_existente)
        self.boton_correr.pack(anchor="w", pady=10, ipadx=8, ipady=3)
        return f

    def _pestana_nuevo(self, nb):
        f = ttk.Frame(nb, padding=10)
        self.v = {}                        # variables del formulario

        def campo(cont, etiqueta, clave, valor, ancho=10):
            fila = ttk.Frame(cont)
            fila.pack(side="left", padx=4)
            ttk.Label(fila, text=etiqueta).pack(anchor="w")
            var = tk.StringVar(value=str(valor))
            ttk.Entry(fila, textvariable=var, width=ancho).pack()
            self.v[clave] = var

        # Identidad y destino
        sup = ttk.Frame(f)
        sup.pack(fill="x")
        campo(sup, "Nombre", "nombre", "MiCaso", 16)
        self.dest_nuevo = tk.StringVar()
        cont_d = ttk.Frame(sup)
        cont_d.pack(side="left", padx=4)
        ttk.Label(cont_d, text="Carpeta destino").pack(anchor="w")
        fd = ttk.Frame(cont_d)
        fd.pack()
        ttk.Entry(fd, textvariable=self.dest_nuevo, width=24).pack(side="left")
        ttk.Button(fd, text="…", width=3,
                   command=lambda: self._elegir_dir(self.dest_nuevo)).pack(side="left")

        # Batimetría
        bat = ttk.Frame(f)
        bat.pack(fill="x", pady=(8, 0))
        self.bat_archivo = tk.StringVar()
        ttk.Label(bat, text="Batimetría (.bot)").pack(side="left")
        ttk.Entry(bat, textvariable=self.bat_archivo, width=34).pack(
            side="left", padx=4)
        ttk.Button(bat, text="…", width=3,
                   command=self._elegir_bot).pack(side="left")
        ttk.Button(bat, text="Generar batimetría…",
                   command=self._generar_batimetria).pack(side="left", padx=(6, 0))

        # Malla
        ttk.Label(f, text="Malla de cómputo", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", pady=(10, 2))
        m1 = ttk.Frame(f); m1.pack(fill="x")
        campo(m1, "Origen X (UTM)", "xpc", 0.0)
        campo(m1, "Origen Y (UTM)", "ypc", 0.0)
        campo(m1, "Largo X [m]", "xlenc", 10000)
        campo(m1, "Largo Y [m]", "ylenc", 12000)
        m2 = ttk.Frame(f); m2.pack(fill="x", pady=(4, 0))
        campo(m2, "Celdas X", "mxc", 100)
        campo(m2, "Celdas Y", "myc", 120)
        campo(m2, "Zona UTM", "zona_utm", "19S", ancho=6)

        ttk.Button(f, text="Definir por lat/lon…",
                   command=self._definir_malla_latlon).pack(anchor="w", pady=(6, 0))

        # Condición de borde
        ttk.Label(f, text="Condición de borde (marejada)",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
        b1 = ttk.Frame(f); b1.pack(fill="x")
        campo(b1, "Hs [m]", "hs", 3.0)
        campo(b1, "Tp [s]", "per", 12.0)
        campo(b1, "Dir [°]", "dir", 290.0)
        campo(b1, "Dispersión [°]", "dd", 20.0)
        # Lados de entrada
        lad = ttk.Frame(f); lad.pack(fill="x", pady=(4, 0))
        ttk.Label(lad, text="Lados:").pack(side="left")
        self.lados = {}
        for s in self.LADOS:
            var = tk.BooleanVar(value=s in ("N", "W"))
            ttk.Checkbutton(lad, text=s, variable=var).pack(side="left")
            self.lados[s] = var

        # Salidas + tipo
        sal = ttk.Frame(f); sal.pack(fill="x", pady=(10, 0))
        ttk.Label(sal, text="Salidas:").pack(side="left")
        self.salidas = {}
        for var_n in self.VARIABLES:
            var = tk.BooleanVar(value=var_n != "Setup")
            ttk.Checkbutton(sal, text=var_n, variable=var).pack(side="left")
            self.salidas[var_n] = var
        self.estacionario = tk.BooleanVar(value=True)
        ttk.Checkbutton(sal, text="Estacionario", variable=self.estacionario).pack(
            side="left", padx=(16, 0))

        ttk.Button(f, text="Tomar borde de ERA5/serie…",
                   command=self._tomar_borde_archivo).pack(anchor="w", pady=(8, 0))

        self.boton_armar = ttk.Button(f, text="Generar .swn y correr",
                                      command=self._armar_y_correr)
        self.boton_armar.pack(anchor="w", pady=12, ipadx=8, ipady=3)
        return f

    def aplicar_borde(self, borde):
        """
        Rellena los campos Hs/Tp/Dir del formulario 'Armar y correr' con un borde
        derivado de una serie (dict {hs, per, dir, descripcion}). Deja en blanco
        las claves None y no toca lado/dispersión/malla/batimetría.
        """
        for clave in ("hs", "per", "dir"):
            val = borde.get(clave)
            self.v[clave].set("" if val is None else f"{val:g}")
        self.log.insert("end", f"Borde aplicado — {borde.get('descripcion', '')}: "
                        f"Hs={borde.get('hs')}, Tp={borde.get('per')}, "
                        f"Dir={borde.get('dir')}\n")
        self.log.see("end")

    def _tomar_borde_archivo(self):
        """Vía A: elige un archivo de serie + condición y rellena el borde."""
        ruta = filedialog.askopenfilename(
            title="Serie de oleaje (ERA5/.mat/.csv/.nc)",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.nc *.mat *.csv"), ("Todos", "*.*")])
        if not ruta:
            return
        cond = dialogo_condicion(self)
        if not cond:
            return
        modo, tr = cond
        try:
            ds = io_oleaje.cargar(ruta)
            borde = borde_oleaje.condicion_borde(ds, modo, tr)
        except Exception as e:
            messagebox.showerror("No se pudo derivar el borde", str(e))
            return
        self.aplicar_borde(borde)

    # -------------------------------------------------------------- acciones
    def _elegir_dir(self, var):
        d = filedialog.askdirectory(title="Carpeta",
                                    initialdir=config.obtener("ultima_carpeta_swan"))
        if d:
            var.set(d)
            config.guardar("ultima_carpeta_swan", d)

    def _elegir_carpeta_exist(self):
        d = filedialog.askdirectory(title="Carpeta del caso SWAN",
                                    initialdir=config.obtener("ultima_carpeta_swan"))
        if not d:
            return
        self.carpeta_exist.set(d)
        config.guardar("ultima_carpeta_swan", d)
        casos = swan_runner.casos_ordenados(d)
        self.casos_lbl.config(
            text=(f"Casos detectados (en orden): {', '.join(casos)}" if casos
                  else "No se encontraron archivos .swn en la carpeta."))

    def _elegir_bot(self):
        r = filedialog.askopenfilename(title="Batimetría SWAN",
                                       initialdir=config.obtener("ultima_carpeta_swan"),
                                       filetypes=[("Batimetría", "*.bot"),
                                                  ("Todos", "*.*")])
        if r:
            self.bat_archivo.set(r)

    def _generar_batimetria(self):
        """Genera el .bot desde la malla (descarga GEBCO/ETOPO o usa raster local)."""
        try:
            malla = {k: float(self.v[k].get())
                     for k in ("xpc", "ypc", "xlenc", "ylenc")}
            malla["mxc"] = int(float(self.v["mxc"].get()))
            malla["myc"] = int(float(self.v["myc"].get()))
            zona = self.v["zona_utm"].get()
        except (ValueError, KeyError) as e:
            messagebox.showerror("Malla inválida",
                                 f"Revisa los campos de malla/zona: {e}")
            return
        destino = self.dest_nuevo.get().strip()
        if not destino:
            messagebox.showwarning("Falta carpeta",
                                   "Elige la carpeta destino del caso primero.")
            return
        raster = None
        if messagebox.askyesno(
                "Batimetría",
                "¿Usar un archivo de batimetría local?\n"
                "Sí = elegir un .nc propio (SHOA u otro)\n"
                "No = descargar GEBCO/ETOPO automáticamente"):
            ruta_r = filedialog.askopenfilename(
                title="Raster de batimetría (.nc)",
                filetypes=[("NetCDF", "*.nc"), ("Todos", "*.*")])
            if not ruta_r:
                return
            try:
                raster = io_batimetria.leer_raster_local(ruta_r)
            except Exception as e:
                messagebox.showerror("Raster inválido", str(e))
                return
        self.log.insert("end", "Generando batimetría…\n")
        self.log.see("end")
        threading.Thread(target=self._bati_worker, daemon=True,
                         args=(malla, zona, destino, raster)).start()

    def _bati_worker(self, malla, zona, destino, raster):
        """Corre generar_bot fuera del hilo de la GUI y rellena el campo .bot."""
        try:
            ruta, meta = io_batimetria.generar_bot(malla, zona, destino, raster=raster)
        except Exception as e:
            self._marshal(lambda: self.log.insert("end", f"Error batimetría: {e}\n"))
            return

        def ok():
            self.bat_archivo.set(str(ruta))
            self.log.insert(
                "end",
                f"Batimetría lista: {ruta.name} — profundidad "
                f"{meta['prof_min']:.1f} a {meta['prof_max']:.1f} m, "
                f"{meta['pct_tierra']:.0f}% en tierra.\n")
            self.log.see("end")
        self._marshal(ok)

    def _definir_malla_latlon(self):
        """Calcula la malla UTM desde lat/lon y rellena los campos del formulario."""
        datos = dialogo_latlon(self)
        if not datos:
            return
        try:
            m = geo_malla.malla_desde_latlon(
                float(datos["lat"]), float(datos["lon"]),
                float(datos["ancho"]), float(datos["alto"]), float(datos["celda"]))
        except (ValueError, KeyError) as e:
            messagebox.showerror("Datos inválidos", str(e))
            return
        self.v["xpc"].set(f"{m['xpc']:.0f}")
        self.v["ypc"].set(f"{m['ypc']:.0f}")
        self.v["xlenc"].set(f"{m['xlenc']:.0f}")
        self.v["ylenc"].set(f"{m['ylenc']:.0f}")
        self.v["mxc"].set(str(m["mxc"]))
        self.v["myc"].set(str(m["myc"]))
        self.v["zona_utm"].set(m["zona_utm"])
        self.log.insert("end", f"Malla definida: zona {m['zona_utm']}, "
                        f"{m['mxc']}×{m['myc']} celdas.\n")
        self.log.see("end")

    def _log(self, msg):
        self._marshal(lambda: (self.log.insert("end", msg + "\n"),
                               self.log.see("end")))

    def _set_progreso(self, i, n):
        # SWAN no anuncia cuántas iteraciones hará, así que el avance dentro de un
        # caso no es un % fiable: la barra va en modo indeterminado (gira) y aquí
        # sólo se actualiza el texto del caso en curso.
        self._marshal(lambda: self.estado.config(
            text=f"Corriendo caso {min(i + 1, n)}/{n}…", foreground="#d18616"))

    def _bloquear(self, activo):
        estado = "disabled" if activo else "normal"
        self.boton_correr.config(state=estado)
        self.boton_armar.config(state=estado)
        self.boton_cancelar.config(state="normal" if activo else "disabled")
        # Barra indeterminada animada mientras SWAN trabaja (no hay total fiable).
        if activo:
            self.progreso.config(mode="indeterminate")
            self.progreso.start(12)
        else:
            self.progreso.stop()
            self.progreso.config(mode="determinate", value=0)

    def _cancelar_corrida(self):
        """Marca cancelación y mata el proceso SWAN en curso."""
        self._cancelar.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self.estado.config(text="Cancelando…", foreground="#d1242f")

    def _correr_existente(self):
        carpeta = self.carpeta_exist.get().strip()
        if not carpeta or not Path(carpeta).is_dir():
            messagebox.showwarning("Carpeta", "Elige una carpeta válida con un .swn.")
            return
        self._lanzar(carpeta)

    def _armar_y_correr(self):
        try:
            destino = self.dest_nuevo.get().strip()
            bot = self.bat_archivo.get().strip()
            if not destino:
                raise ValueError("Indica una carpeta destino.")
            if not bot or not Path(bot).exists():
                raise ValueError("Selecciona un archivo de batimetría .bot.")
            destino = Path(destino)
            destino.mkdir(parents=True, exist_ok=True)
            # Copia la batimetría a la carpeta del caso (rutas relativas en el .swn).
            bot = Path(bot)
            if bot.parent != destino:
                (destino / bot.name).write_bytes(bot.read_bytes())

            malla = {k: float(self.v[k].get()) for k in ("xpc", "ypc", "xlenc",
                                                         "ylenc")}
            malla["mxc"] = int(float(self.v["mxc"].get()))
            malla["myc"] = int(float(self.v["myc"].get()))
            bordes = [{"lado": s, "hs": float(self.v["hs"].get()),
                       "per": float(self.v["per"].get()),
                       "dir": float(self.v["dir"].get()),
                       "dd": float(self.v["dd"].get())}
                      for s, on in self.lados.items() if on.get()]
            if not bordes:
                raise ValueError("Elige al menos un lado de entrada del oleaje.")
            salidas = tuple(v for v, on in self.salidas.items() if on.get())
            if not salidas:
                raise ValueError("Elige al menos una variable de salida.")

            # Validación física antes de generar/correr (la batimetría ya está
            # copiada en `destino`, así que se valida también su tamaño).
            errores, avisos = swan_builder.validar_caso(
                malla, {"archivo": bot.name}, bordes, carpeta=destino)
            if errores:
                messagebox.showerror("Revisa el caso", "\n\n".join(errores))
                return
            if avisos and not messagebox.askyesno(
                    "Advertencias", "\n\n".join(avisos) + "\n\n¿Continuar igual?"):
                return

            ruta = swan_builder.escribir_caso(
                destino, self.v["nombre"].get().strip() or "MiCaso",
                nombre=self.v["nombre"].get().strip() or "MiCaso",
                malla=malla, batimetria={"archivo": bot.name}, bordes=bordes,
                salidas=salidas, estacionario=self.estacionario.get())
        except Exception as exc:
            messagebox.showerror("Datos del caso", str(exc))
            return
        self._log(f"Archivo generado: {ruta}")
        self._lanzar(str(destino))

    def _lanzar(self, carpeta):
        config.guardar("ultima_carpeta_swan", carpeta)
        self._cancelar.clear()
        self._proc = None
        self._bloquear(True)               # arranca la barra indeterminada
        self.estado.config(text="Procesando…", foreground="#d18616")
        threading.Thread(target=self._procesar, args=(carpeta,),
                         daemon=True).start()

    def _procesar(self, carpeta):
        try:
            ok, nuevas = swan_runner.correr_swan(
                carpeta, log=self._log, progreso=self._set_progreso,
                on_proc=lambda p: setattr(self, "_proc", p),
                cancelado=self._cancelar.is_set)
            if self._cancelar.is_set():
                self._marshal(self._cancelado_fin)
            else:
                self._marshal(self._terminar, ok, nuevas, carpeta)
        except Exception:
            self._marshal(self._error, traceback.format_exc())

    def _cancelado_fin(self):
        self._bloquear(False)              # detiene y resetea la barra
        self.estado.config(text="Corrida cancelada.", foreground="#d1242f")

    def _terminar(self, ok, nuevas, carpeta):
        self._bloquear(False)              # detiene y resetea la barra
        if ok:
            self.estado.config(text=f"Listo: {len(nuevas)} salida(s) generada(s).",
                               foreground="#1f6feb")
            if messagebox.askyesno(
                    "SWAN terminó",
                    "La corrida terminó correctamente.\n\n¿Abrir la carpeta de "
                    "resultados? Luego puedes usar «Crear» para graficar."):
                try:
                    os.startfile(carpeta)
                except Exception:
                    pass
        else:
            self.estado.config(text="SWAN terminó con avisos; revisa el log/.prt.",
                               foreground="#d1242f")

    def _error(self, mensaje):
        self._bloquear(False)              # detiene y resetea la barra
        self.estado.config(text="Error al correr SWAN.", foreground="#d1242f")
        self.log.insert("end", mensaje + "\n")
        messagebox.showerror("Error", "No se pudo correr SWAN. Revisa el detalle.")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    VentanaSwan(root)
    root.mainloop()
