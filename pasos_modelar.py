"""
Pasos del camino "Modelar propagación con SWAN" (un dominio en v1).

1. Malla: por lat/lon (centro + tamaño + celda) → geo_malla.
2. Batimetría: descarga automática (GEBCO/ETOPO) o .bot propio → io_batimetria.
3. Borde: manual o derivado de ERA5/serie → borde_oleaje.
4. Correr SWAN: validar_caso → escribir_caso → swan_runner.
5. Ver: tablero_swan del resultado.

El contexto guarda `dominios` como lista (preparado para el nido del 2º
proyecto): en v1 hay un único dominio.
"""

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import asistente
import config
import geo_malla
import io_batimetria
import io_oleaje
import borde_oleaje
import gui_swan
import swan_builder
import swan_runner
import tablero_swan


def _dominio_actual(contexto):
    """Devuelve el dict del dominio en construcción (crea la lista si hace falta)."""
    if "dominios" not in contexto:
        contexto["dominios"] = [{}]
    return contexto["dominios"][0]


class PasoMalla(asistente.Paso):
    titulo = "Malla de cómputo (por lat/lon)"

    def __init__(self, master):
        super().__init__(master)
        self.campos = {}
        for etiqueta, clave, valor in (
                ("Latitud centro", "lat", "-32.97"),
                ("Longitud centro", "lon", "-71.55"),
                ("Ancho [km]", "ancho", "8"),
                ("Alto [km]", "alto", "8"),
                ("Tamaño de celda [m]", "celda", "100")):
            f = ttk.Frame(self); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ttk.Entry(f, textvariable=var, width=14).pack(side="left")
            self.campos[clave] = var
        ttk.Button(self, text="Calcular malla", command=self._calcular).pack(
            anchor="w", pady=(6, 0))
        self.detalle = ttk.Label(self, foreground="#555")
        self.detalle.pack(anchor="w", pady=(6, 0))
        self.malla = None

    def _calcular(self):
        try:
            self.malla = geo_malla.malla_desde_latlon(
                float(self.campos["lat"].get()), float(self.campos["lon"].get()),
                float(self.campos["ancho"].get()), float(self.campos["alto"].get()),
                float(self.campos["celda"].get()))
        except (ValueError, KeyError) as e:
            messagebox.showerror("Datos inválidos", str(e)); return
        m = self.malla
        self.detalle.config(
            text=f"Zona UTM {m['zona_utm']} · {m['mxc']}×{m['myc']} celdas · "
                 f"origen UTM ({m['xpc']:.0f}, {m['ypc']:.0f}).")

    def validar(self):
        if self.malla is None:
            return False, "Pulsa «Calcular malla» con valores válidos."
        return True, ""

    def recoger(self, contexto):
        dom = _dominio_actual(contexto)
        dom["malla"] = self.malla
        dom["zona_utm"] = self.malla["zona_utm"]


class PasoBatimetria(asistente.Paso):
    titulo = "Batimetría"

    def __init__(self, master):
        super().__init__(master)
        self.bot = tk.StringVar()
        ttk.Label(self, text="Necesitas un archivo .bot que cubra la malla."
                  ).pack(anchor="w")
        ttk.Button(self, text="Descargar batimetría automática (GEBCO/ETOPO)",
                   command=self._descargar).pack(anchor="w", pady=(8, 0))
        ttk.Button(self, text="Usar un .bot propio…",
                   command=self._elegir).pack(anchor="w", pady=(4, 0))
        self.detalle = ttk.Label(self, textvariable=self.bot, foreground="#555")
        self.detalle.pack(anchor="w", pady=(8, 0))

    def entrar(self, contexto):
        self._contexto = contexto

    def _carpeta_destino(self):
        """Carpeta del caso: se pide una vez y se guarda en el contexto."""
        ctx = self._contexto
        if ctx.get("carpeta_caso"):
            return ctx["carpeta_caso"]
        d = filedialog.askdirectory(
            title="Carpeta donde se armará el caso SWAN",
            initialdir=config.obtener("ultima_carpeta_swan"))
        if d:
            ctx["carpeta_caso"] = d
            config.guardar("ultima_carpeta_swan", d)
        return d

    def _descargar(self):
        ctx = self._contexto
        dom = _dominio_actual(ctx)
        if "malla" not in dom:
            messagebox.showwarning("Falta la malla", "Define la malla primero.")
            return
        destino = self._carpeta_destino()
        if not destino:
            return
        malla = dom["malla"]
        zona = dom["zona_utm"]

        def trabajo(log, progreso):
            ruta, meta = io_batimetria.generar_bot(malla, zona, destino)
            log(f"Batimetría: {ruta.name} — prof. {meta['prof_min']:.1f} a "
                f"{meta['prof_max']:.1f} m, {meta['pct_tierra']:.0f}% en tierra.")
            return str(ruta)

        def al_terminar(res):
            if res:
                self.bot.set(res)

        self.wizard.tarea(trabajo, al_terminar)

    def _elegir(self):
        r = filedialog.askopenfilename(
            title="Batimetría SWAN (.bot)",
            initialdir=config.obtener("ultima_carpeta_swan"),
            filetypes=[("Batimetría", "*.bot"), ("Todos", "*.*")])
        if r:
            self.bot.set(r)

    def validar(self):
        b = self.bot.get().strip()
        if not b or not Path(b).exists():
            return False, "Genera o selecciona un archivo de batimetría .bot."
        return True, ""

    def recoger(self, contexto):
        _dominio_actual(contexto)["bot"] = self.bot.get().strip()


class PasoBorde(asistente.Paso):
    titulo = "Condición de borde"

    def __init__(self, master):
        super().__init__(master)
        self.v = {}
        for etiqueta, clave, valor in (("Hs [m]", "hs", "3.0"), ("Tp [s]", "per", "12.0"),
                                       ("Dir [°] (náutica)", "dir", "290.0"),
                                       ("Dispersión [°]", "dd", "20.0")):
            f = ttk.Frame(self); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=18).pack(side="left")
            var = tk.StringVar(value=valor)
            ttk.Entry(f, textvariable=var, width=10).pack(side="left")
            self.v[clave] = var
        lad = ttk.Frame(self); lad.pack(fill="x", pady=(6, 0))
        ttk.Label(lad, text="Lados de entrada:").pack(side="left")
        self.lados = {}
        for s in ("N", "S", "E", "W"):
            var = tk.BooleanVar(value=s in ("N", "W"))
            ttk.Checkbutton(lad, text=s, variable=var).pack(side="left")
            self.lados[s] = var
        ttk.Button(self, text="Derivar de ERA5/serie…",
                   command=self._derivar).pack(anchor="w", pady=(8, 0))

    def _derivar(self):
        r = filedialog.askopenfilename(
            title="Serie de oleaje (ERA5/.mat/.csv/.nc)",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.nc *.mat *.csv"), ("Todos", "*.*")])
        if not r:
            return
        cond = gui_swan.dialogo_condicion(self)
        if not cond:
            return
        modo, tr = cond
        try:
            ds = io_oleaje.cargar(r)
            borde = borde_oleaje.condicion_borde(ds, modo, tr)
        except Exception as e:
            messagebox.showerror("No se pudo derivar el borde", str(e)); return
        for clave in ("hs", "per", "dir"):
            val = borde.get(clave)
            self.v[clave].set("" if val is None else f"{val:g}")
        self.wizard.log.insert("end", f"Borde derivado — {borde.get('descripcion','')}\n")

    def validar(self):
        try:
            hs = float(self.v["hs"].get()); per = float(self.v["per"].get())
            float(self.v["dir"].get()); float(self.v["dd"].get())
        except ValueError:
            return False, "Revisa los valores del borde (deben ser números)."
        if hs <= 0 or per <= 0:
            return False, "Hs y Tp deben ser mayores que cero."
        if not any(v.get() for v in self.lados.values()):
            return False, "Elige al menos un lado de entrada del oleaje."
        return True, ""

    def recoger(self, contexto):
        bordes = [{"lado": s, "hs": float(self.v["hs"].get()),
                   "per": float(self.v["per"].get()),
                   "dir": float(self.v["dir"].get()),
                   "dd": float(self.v["dd"].get())}
                  for s, on in self.lados.items() if on.get()]
        _dominio_actual(contexto)["bordes"] = bordes


class PasoCorrer(asistente.Paso):
    titulo = "Correr SWAN"

    def __init__(self, master):
        super().__init__(master)
        self.nombre = tk.StringVar(value="MiCaso")
        f = ttk.Frame(self); f.pack(fill="x")
        ttk.Label(f, text="Nombre del caso:", width=18).pack(side="left")
        ttk.Entry(f, textvariable=self.nombre, width=20).pack(side="left")
        ttk.Button(self, text="Generar .swn y correr",
                   command=self._correr).pack(anchor="w", pady=(8, 0))
        self.ok = False

    def entrar(self, contexto):
        self._contexto = contexto
        self.ok = False

    def _correr(self):
        ctx = self._contexto
        dom = ctx["dominios"][0]
        destino = Path(ctx["carpeta_caso"])
        bot = Path(dom["bot"])
        # Copiar la batimetría a la carpeta del caso (rutas relativas en el .swn).
        if bot.parent != destino:
            (destino / bot.name).write_bytes(bot.read_bytes())
        malla = dict(dom["malla"]); malla.pop("zona_utm", None)
        bordes = dom["bordes"]

        errores, avisos = swan_builder.validar_caso(
            malla, {"archivo": bot.name}, bordes, carpeta=destino)
        if errores:
            messagebox.showerror("Revisa el caso", "\n\n".join(errores)); return
        if avisos and not messagebox.askyesno(
                "Advertencias", "\n\n".join(avisos) + "\n\n¿Continuar igual?"):
            return
        nombre = self.nombre.get().strip() or "MiCaso"
        ruta_swn = swan_builder.escribir_caso(
            destino, nombre, nombre=nombre, malla=malla,
            batimetria={"archivo": bot.name}, bordes=bordes,
            salidas=("Hs", "Tp", "Dir"), estacionario=True)
        self.wizard.log.insert("end", f"Caso generado: {ruta_swn}\n")

        def trabajo(log, progreso):
            ok, nuevas = swan_runner.correr_swan(str(destino), log=log,
                                                 progreso=progreso)
            return ok

        def al_terminar(ok):
            self.ok = bool(ok)
            self.wizard.log.insert(
                "end", "SWAN terminó.\n" if ok else "SWAN terminó con avisos.\n")

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if not self.ok:
            return False, "Corre SWAN y espera a que termine antes de continuar."
        return True, ""

    def recoger(self, contexto):
        contexto["carpeta_resultado"] = contexto["carpeta_caso"]


class PasoVer(asistente.Paso):
    titulo = "Ver resultados"

    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Genera el tablero de mapas de la corrida."
                  ).pack(anchor="w")
        ttk.Button(self, text="Generar mapas",
                   command=self._generar).pack(anchor="w", pady=(8, 0))
        self.resultado = None

    def entrar(self, contexto):
        self._contexto = contexto
        self.resultado = None

    def _generar(self):
        carpeta = self._contexto["carpeta_resultado"]

        def trabajo(log, progreso):
            return tablero_swan.generar_tablero_swan(carpeta)

        def al_terminar(res):
            if res is None:
                return
            self.resultado = res
            self.wizard.log.insert("end", f"Resultado: {res}\n")
            try:
                os.startfile(str(res))
            except Exception as e:
                self.wizard.log.insert("end", f"No se pudo abrir {res}: {e}\n")

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if self.resultado is None:
            return False, "Pulsa «Generar mapas» y espera a que termine."
        return True, ""


PASOS_MODELAR = [PasoMalla, PasoBatimetria, PasoBorde, PasoCorrer, PasoVer]
