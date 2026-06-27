"""
Pasos del camino "Modelar propagación con SWAN" (1 o 2 dominios).

1. Malla: por lat/lon (centro + tamaño + celda) → geo_malla.
2. Batimetría: descarga automática (GEBCO/ETOPO) o .bot propio → io_batimetria.
3. Borde: manual o derivado de ERA5/serie → borde_oleaje.
4. Nido (opcional): dominio anidado más fino; si se activa añade un segundo
   elemento a `contexto["dominios"]`.
5. Correr SWAN: valida y escribe 1 caso simple o un par anidado según cuántos
   dominios haya en `contexto["dominios"]`; llama a swan_runner.
6. Ver: tablero_swan del resultado.

`contexto["dominios"]` es una lista de 1 o 2 dicts de dominio.
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
        if not r:
            return
        # Asegura la carpeta del caso (donde se armará el .swn) también en este
        # camino; sin ella, PasoCorrer no tendría dónde escribir el caso.
        if not self._carpeta_destino():
            return
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


class PasoNido(asistente.Paso):
    titulo = "Dominio anidado (opcional)"

    def __init__(self, master):
        super().__init__(master)
        self.activo = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Agregar un dominio anidado (nido) más fino",
                        variable=self.activo, command=self._refrescar).pack(anchor="w")
        self.marco = ttk.Frame(self)
        self.marco.pack(fill="x", padx=(20, 0), pady=(6, 0))
        self._editables = []               # widgets a habilitar/deshabilitar

        # Malla del nido
        self.campos = {}
        for etiqueta, clave, valor in (
                ("Latitud centro", "lat", "-36.97"),
                ("Longitud centro", "lon", "-73.15"),
                ("Ancho [km]", "ancho", "9"),
                ("Alto [km]", "alto", "10"),
                ("Tamaño de celda [m]", "celda", "200")):
            f = ttk.Frame(self.marco); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ent = ttk.Entry(f, textvariable=var, width=14); ent.pack(side="left")
            self.campos[clave] = var
            self._editables.append(ent)
        self.boton_malla = ttk.Button(self.marco, text="Calcular malla del nido",
                                      command=self._calcular)
        self.boton_malla.pack(anchor="w", pady=(4, 0))
        self._editables.append(self.boton_malla)
        self.detalle = ttk.Label(self.marco, foreground="#555")
        self.detalle.pack(anchor="w")

        # Batimetría del nido
        self.bot = tk.StringVar()
        fb = ttk.Frame(self.marco); fb.pack(fill="x", pady=(6, 0))
        self.boton_bati = ttk.Button(fb, text="Generar batimetría del nido",
                                     command=self._bati)
        self.boton_bati.pack(side="left")
        self.boton_bot = ttk.Button(fb, text="Usar .bot propio…",
                                    command=self._elegir_bot)
        self.boton_bot.pack(side="left", padx=(6, 0))
        self._editables += [self.boton_bati, self.boton_bot]
        ttk.Label(self.marco, textvariable=self.bot, foreground="#555").pack(anchor="w")

        # Punto espectral
        self.con_espectro = tk.BooleanVar(value=False)
        self.check_esp = ttk.Checkbutton(self.marco, text="Salida espectral en un punto",
                                         variable=self.con_espectro)
        self.check_esp.pack(anchor="w", pady=(6, 0))
        self._editables.append(self.check_esp)
        fe = ttk.Frame(self.marco); fe.pack(fill="x")
        self.pe = {}
        for etiqueta, clave, valor in (("Lat punto", "lat", "-36.98"),
                                       ("Lon punto", "lon", "-73.13")):
            ttk.Label(fe, text=etiqueta).pack(side="left")
            var = tk.StringVar(value=valor)
            ent = ttk.Entry(fe, textvariable=var, width=10)
            ent.pack(side="left", padx=(2, 8))
            self.pe[clave] = var
            self._editables.append(ent)

        self.malla = None
        self._refrescar()

    def entrar(self, contexto):
        self._contexto = contexto

    def _refrescar(self):
        estado = "normal" if self.activo.get() else "disabled"
        for w in self._editables:
            try:
                w.config(state=estado)
            except tk.TclError:
                pass

    def _calcular(self):
        try:
            self.malla = geo_malla.malla_desde_latlon(
                float(self.campos["lat"].get()), float(self.campos["lon"].get()),
                float(self.campos["ancho"].get()), float(self.campos["alto"].get()),
                float(self.campos["celda"].get()))
        except (ValueError, KeyError) as e:
            messagebox.showerror("Datos inválidos", str(e)); return
        m = self.malla
        self.detalle.config(text=f"Nido: zona UTM {m['zona_utm']} · "
                            f"{m['mxc']}×{m['myc']} celdas.")

    def _bati(self):
        if self.malla is None:
            messagebox.showwarning("Falta la malla", "Calcula la malla del nido primero.")
            return
        destino = self._contexto.get("carpeta_caso")
        if not destino:
            messagebox.showwarning("Falta carpeta",
                                   "Genera primero la batimetría del dominio grande "
                                   "(define la carpeta del caso).")
            return
        malla = {k: v for k, v in self.malla.items() if k != "zona_utm"}

        def trabajo(log, progreso):
            ruta, meta = io_batimetria.generar_bot(
                malla, self.malla["zona_utm"], destino, nombre="bati_nido.bot")
            log(f"Batimetría del nido: {ruta.name} — prof. {meta['prof_min']:.1f} a "
                f"{meta['prof_max']:.1f} m, {meta['pct_tierra']:.0f}% en tierra.")
            return str(ruta)

        def al_terminar(res):
            if res:
                self.bot.set(res)

        self.wizard.tarea(trabajo, al_terminar)

    def _elegir_bot(self):
        r = filedialog.askopenfilename(
            title="Batimetría del nido (.bot)",
            initialdir=config.obtener("ultima_carpeta_swan"),
            filetypes=[("Batimetría", "*.bot"), ("Todos", "*.*")])
        if r:
            self.bot.set(r)

    def validar(self):
        if not self.activo.get():
            return True, ""                 # nido opcional, apagado
        if self.malla is None:
            return False, "Calcula la malla del nido o desactiva el dominio anidado."
        grande = self._contexto.get("dominios", [{}])[0].get("malla")
        if grande:
            errores, _ = swan_builder.validar_caso_anidado(grande, self.malla)
            if errores:
                return False, "\n".join(errores)
        b = self.bot.get().strip()
        if not b or not Path(b).exists():
            return False, "Genera o selecciona la batimetría del nido."
        return True, ""

    def recoger(self, contexto):
        if not self.activo.get():
            return
        dom = {"malla": self.malla, "bot": self.bot.get().strip()}
        if self.con_espectro.get():
            try:
                import pyproj
                este, norte = pyproj.Transformer.from_crs(
                    "EPSG:4326", f"EPSG:{io_batimetria.epsg_utm(self.malla['zona_utm'])}",
                    always_xy=True).transform(float(self.pe["lon"].get()),
                                              float(self.pe["lat"].get()))
                dom["punto_espectral"] = {"x": round(este), "y": round(norte),
                                          "archivo": "Espectro_Punto.txt"}
            except Exception:
                messagebox.showwarning(
                    "Punto espectral no agregado",
                    "No se pudo convertir el punto espectral a UTM; "
                    "se omitirá la salida espectral del nido.")
                dom["punto_espectral"] = None
        contexto["dominios"].append(dom)


class PasoCorrer(asistente.Paso):
    titulo = "Correr SWAN"

    def __init__(self, master):
        super().__init__(master)
        self.nombre = tk.StringVar(value="MiCaso")
        f = ttk.Frame(self); f.pack(fill="x")
        ttk.Label(f, text="Nombre del caso:", width=18).pack(side="left")
        ttk.Entry(f, textvariable=self.nombre, width=20).pack(side="left")
        ttk.Button(self, text="Generar .swn y correr", style="Primary.TButton",
                   command=self._correr).pack(anchor="w", pady=(8, 0))
        self.ok = False
        self.corrido = False               # distingue "aún no corre" de "corrió y falló"

    def entrar(self, contexto):
        self._contexto = contexto
        self.ok = False
        self.corrido = False

    def _correr(self):
        ctx = self._contexto
        dominios = ctx.get("dominios", [])
        if not dominios or not ctx.get("carpeta_caso"):
            messagebox.showerror(
                "Faltan datos",
                "Completa malla, batimetría y borde antes de correr SWAN.")
            return
        g = dominios[0]
        if any(k not in g for k in ("malla", "bot", "bordes")):
            messagebox.showerror("Faltan datos",
                                 "Completa malla, batimetría y borde del dominio grande.")
            return
        destino = Path(ctx["carpeta_caso"])
        nombre = self.nombre.get().strip() or "MiCaso"
        bot_g = Path(g["bot"])
        if bot_g.parent != destino:
            (destino / bot_g.name).write_bytes(bot_g.read_bytes())
        malla_g = {k: v for k, v in g["malla"].items() if k != "zona_utm"}
        bordes = g["bordes"]

        errores, avisos = swan_builder.validar_caso(
            malla_g, {"archivo": bot_g.name}, bordes, carpeta=destino)

        anidado = len(dominios) >= 2
        if anidado:
            n = dominios[1]
            if any(k not in n for k in ("malla", "bot")):
                messagebox.showerror("Faltan datos",
                                     "Completa malla y batimetría del nido.")
                return
            bot_n = Path(n["bot"])
            if bot_n.parent != destino:
                (destino / bot_n.name).write_bytes(bot_n.read_bytes())
            malla_n = {k: v for k, v in n["malla"].items() if k != "zona_utm"}
            e_an, a_an = swan_builder.validar_caso_anidado(g["malla"], n["malla"])
            errores += e_an
            avisos += a_an
            e_n, a_n = swan_builder.validar_caso(
                malla_n, {"archivo": bot_n.name}, [], carpeta=destino,
                requiere_bordes=False)
            errores += e_n
            avisos += a_n

        if errores:
            messagebox.showerror("Revisa el caso", "\n\n".join(errores)); return
        if avisos and not messagebox.askyesno(
                "Advertencias", "\n\n".join(avisos) + "\n\n¿Continuar igual?"):
            return

        if anidado:
            ruta_g, ruta_n = swan_builder.escribir_par_anidado(
                destino, nombre, nombre + "_nido",
                malla_g, {"archivo": bot_g.name}, bordes,
                malla_n, {"archivo": Path(n["bot"]).name},
                salidas=("Hs", "Tp", "Dir"),
                punto_espectral=n.get("punto_espectral"))
            self.wizard.log.insert("end",
                                   f"Par anidado generado: {ruta_g.name}, {ruta_n.name}\n")
        else:
            ruta_swn = swan_builder.escribir_caso(
                destino, nombre, nombre=nombre, malla=malla_g,
                batimetria={"archivo": bot_g.name}, bordes=bordes,
                salidas=("Hs", "Tp", "Dir"), estacionario=True)
            self.wizard.log.insert("end", f"Caso generado: {ruta_swn}\n")

        def trabajo(log, progreso):
            ok, _ = swan_runner.correr_swan(str(destino), log=log, progreso=progreso)
            return ok

        def al_terminar(ok):
            self.corrido = True
            self.ok = bool(ok)
            self.wizard.log.insert(
                "end",
                "SWAN terminó normalmente.\n" if self.ok else
                "SWAN terminó CON ERRORES: ningún caso alcanzó 'norm_end' o se generó "
                "un .erf. Revisa el log y los .prt/.erf; no se puede continuar.\n")

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if not self.corrido:
            return False, "Corre SWAN y espera a que termine antes de continuar."
        if not self.ok:
            return False, ("SWAN terminó con errores: ningún resultado válido. "
                           "Revisa el log (.prt/.erf) y corrige antes de continuar.")
        return True, ""

    def recoger(self, contexto):
        contexto["carpeta_resultado"] = contexto["carpeta_caso"]


class PasoVer(asistente.Paso):
    titulo = "Ver resultados"

    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Genera el tablero de mapas de la corrida."
                  ).pack(anchor="w")
        ttk.Button(self, text="Generar mapas", style="Primary.TButton",
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


PASOS_MODELAR = [PasoMalla, PasoBatimetria, PasoBorde, PasoNido, PasoCorrer, PasoVer]
