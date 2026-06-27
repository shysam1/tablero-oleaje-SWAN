"""
Interfaz gráfica del Tablero de Oleaje.

Arranca en una pantalla de inicio ("¿Qué quieres hacer?") con tres caminos
guiados (analizar una serie, modelar con SWAN, ver una corrida existente) y un
acceso al modo avanzado, que es la caja de herramientas de siempre (selector +
Crear + Procesar SWAN + Descargar ERA5). Todo vive en la misma ventana, que
intercambia "vistas".
"""

import io
import os
import sys
import threading
import traceback
from contextlib import redirect_stdout
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

import tablero_oleaje
import tablero_swan
import video_swan
import io_swan_nonst
import gui_swan
import config
import io_era5
import rutas
import io_oleaje
import borde_oleaje
import asistente
import estilo
import pasos_analizar
import pasos_modelar
import pasos_ver


class _SumideroNulo(io.TextIOBase):
    """Stream que descarta lo que se le escribe (para reemplazar a stdout None)."""

    def write(self, _texto):
        return 0

    def flush(self):
        pass


def _asegurar_salida_estandar():
    """
    Bajo pythonw.exe (sin consola) `sys.stdout`/`sys.stderr` son None, así que
    cualquier print() del pipeline (avisos de io_swan, reportes de validación,
    capacidades de productos…) reventaría con AttributeError al escribir en None.
    Si faltan, se redirigen a un sumidero para que la app no dependa de la consola.
    Sólo actúa cuando son None: con consola (o bajo pytest) no toca nada.
    """
    if sys.stdout is None:
        sys.stdout = _SumideroNulo()
    if sys.stderr is None:
        sys.stderr = _SumideroNulo()


def validar_inputs_era5(lat_txt, lon_txt, inicio, fin):
    """Convierte y valida lat/lon; devuelve (lat, lon). Lanza ValueError si no sirven."""
    lat = float(lat_txt)
    lon = float(lon_txt)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Latitud/longitud fuera de rango.")
    if not (inicio and fin):
        raise ValueError("Faltan fechas de inicio/fin.")
    return lat, lon


class VistaInicio(ttk.Frame):
    """Pantalla de inicio: sidebar Mac + tarjetas de camino."""

    def __init__(self, master, ir_a):
        super().__init__(master, padding=0)
        self.ir_a = ir_a
        self._iconos = []

        self._layout = tk.Frame(self, bg=estilo.PALETA["fondo"])
        self._layout.pack(fill="both", expand=True)

        self._sidebar = tk.Frame(self._layout, bg=estilo.PALETA["sidebar"],
                                 width=estilo.ANCHO_SIDEBAR)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._construir_sidebar()

        self._main = tk.Frame(self._layout, bg=estilo.PALETA["fondo"])
        self._main.pack(side="left", fill="both", expand=True)

        contenido = tk.Frame(self._main, bg=estilo.PALETA["fondo"], padx=28, pady=24)
        contenido.pack(fill="both", expand=True)

        tk.Label(contenido, text="¿Qué quieres hacer?", font=estilo.FUENTE_TITULO,
                 bg=estilo.PALETA["fondo"], fg=estilo.PALETA["texto"]).pack(anchor="w")
        tk.Label(
            contenido,
            text="Elige un flujo guiado o abre las herramientas sueltas.",
            font=estilo.FUENTE_SUBTITULO, bg=estilo.PALETA["fondo"],
            fg=estilo.PALETA["texto_secundario"]).pack(anchor="w", pady=(4, 20))

        self._cont_tarjetas = tk.Frame(contenido, bg=estilo.PALETA["fondo"])
        self._cont_tarjetas.pack(fill="both", expand=True)

        iconos = estilo.cargar_iconos(self)
        self._iconos = list(iconos.values())
        datos = [
            ("Analizar oleaje\nen un punto",
             "Datos propios o descargados de ERA5 → curvas, régimen extremo, "
             "espectro.", "analizar", "analizar",
             estilo.PALETA["analizar"], estilo.PALETA["analizar_fondo"]),
            ("Modelar propagación\ncon SWAN",
             "Desde cero: malla → batimetría → borde → correr → mapas.",
             "modelar", "modelar",
             estilo.PALETA["modelar"], estilo.PALETA["modelar_fondo"]),
            ("Ver una corrida\nSWAN ya hecha",
             "Tienes la carpeta corrida y solo quieres graficarla (mapas o video).",
             "ver", "ver",
             estilo.PALETA["ver"], estilo.PALETA["ver_fondo"]),
        ]
        self._tarjetas = []
        for titulo, desc, destino, clave_icono, color, fondo_icono in datos:
            tarj = estilo.TarjetaCamino(
                self._cont_tarjetas, titulo, desc, destino,
                iconos[clave_icono], color, fondo_icono, ir_a)
            self._tarjetas.append(tarj)

        pie = tk.Frame(contenido, bg=estilo.PALETA["fondo"])
        pie.pack(fill="x", pady=(16, 0))
        tk.Label(pie, text="Creado por Javier Tarrazón",
                 font=("Segoe UI", 10), bg=estilo.PALETA["fondo"],
                 fg=estilo.PALETA["texto_secundario"]).pack(side="left")
        ttk.Button(pie, text="Herramientas sueltas →",
                   style="Secondary.TButton",
                   command=lambda: self.ir_a("avanzado")).pack(side="right")

        self._cont_tarjetas.bind("<Configure>", self._reacomodar_tarjetas)
        self.bind("<Configure>", self._ajustar_sidebar)
        self.after_idle(self._reacomodar_tarjetas)
        self.after_idle(self._ajustar_sidebar)

    def _construir_sidebar(self):
        pad = tk.Frame(self._sidebar, bg=estilo.PALETA["sidebar"], padx=12, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="TABLERO DE OLEAJE", font=estilo.FUENTE_NAV_SECCION,
                 bg=estilo.PALETA["sidebar"], fg=estilo.PALETA["texto_secundario"]).pack(
                     anchor="w", pady=(0, 10))

        self._nav_inicio = tk.Label(
            pad, text="  ¿Qué quieres hacer?", font=("Segoe UI", 11, "bold"),
            bg=estilo.PALETA["nav_activo"], fg=estilo.PALETA["primario"],
            anchor="w", padx=8, pady=6)
        self._nav_inicio.pack(fill="x", pady=(0, 2))

        nav_avanzado = tk.Label(
            pad, text="  Modo avanzado", font=estilo.FUENTE_NAV,
            bg=estilo.PALETA["sidebar"], fg=estilo.PALETA["texto"],
            anchor="w", padx=8, pady=6, cursor="hand2")
        nav_avanzado.pack(fill="x", pady=(0, 2))
        nav_avanzado.bind("<Enter>", lambda e: nav_avanzado.configure(
            bg=estilo.PALETA["borde_suave"]))
        nav_avanzado.bind("<Leave>", lambda e: nav_avanzado.configure(
            bg=estilo.PALETA["sidebar"]))
        nav_avanzado.bind("<Button-1>", lambda e: self.ir_a("avanzado"))

    def _ajustar_sidebar(self, event=None):
        ancho = self.winfo_width()
        if ancho < 2:
            return
        if ancho < estilo.ANCHURA_APILADA:
            self._sidebar.pack_forget()
        elif not self._sidebar.winfo_ismapped():
            self._sidebar.pack(side="left", fill="y", before=self._main)

    def _reacomodar_tarjetas(self, event=None):
        ancho = self._cont_tarjetas.winfo_width()
        if ancho < 2:
            return
        apilado = ancho < estilo.ANCHURA_APILADA
        for w in self._tarjetas:
            w.grid_forget()
        if apilado:
            for i, tarj in enumerate(self._tarjetas):
                tarj.grid(row=i, column=0, sticky="ew",
                          pady=(0 if i == 0 else 10, 0))
            self._cont_tarjetas.columnconfigure(0, weight=1)
        else:
            for i, tarj in enumerate(self._tarjetas):
                tarj.grid(row=0, column=i, sticky="nsew",
                          padx=(0 if i == 0 else 10, 0))
                self._cont_tarjetas.columnconfigure(i, weight=1)
            self._cont_tarjetas.rowconfigure(0, weight=1)
        for tarj in self._tarjetas:
            tarj.ajustar_ancho(ancho, apilado)


class VistaAvanzado(ttk.Frame):
    """La caja de herramientas de siempre: selector + Crear + SWAN + ERA5."""

    def __init__(self, master, al_inicio):
        super().__init__(master, padding=12)
        self.al_inicio = al_inicio
        self.ruta_datos = tk.StringVar(value="")
        # Offset UTM del nodo (0,0) del dominio grande SWAN (default: Golfo de
        # Arauco). Sólo afecta las etiquetas UTM de los mapas/videos.
        self.utm_x = tk.StringVar(value="620494")
        self.utm_y = tk.StringVar(value="5876451")
        self._construir_widgets()

    def _marshal(self, func, *args):
        """
        Agenda func(*args) en el hilo de la GUI desde un hilo de trabajo, ignorando
        en silencio si la vista ya se destruyó (al cerrar la app o volver a inicio).
        """
        def _run():
            if self.winfo_exists():
                func(*args)
        try:
            self.after(0, _run)
        except tk.TclError:
            pass

    def _construir_widgets(self):
        fila_top = ttk.Frame(self)
        fila_top.pack(fill="x", pady=(4, 0))
        self.boton_inicio = ttk.Button(fila_top, text="← Inicio",
                                       style="Secondary.TButton",
                                       command=self.al_inicio)
        self.boton_inicio.pack(side="left")
        ttk.Label(fila_top, text="Modo avanzado",
                  style="WizardTitulo.TLabel").pack(side="left", padx=(12, 0))
        ttk.Label(self, text="Serie temporal (.mat/.csv/.nc) → curvas. "
                  "Carpeta SWAN → mapas. Carpeta SWAN no estacionaria → video.",
                  style="Muted.TLabel").pack(anchor="w", pady=(8, 12))

        panel = estilo.PanelTarjeta(self)
        panel.pack(fill="x", pady=(0, 8))
        cuerpo = panel.cuerpo

        fila = tk.Frame(cuerpo, bg=estilo.PALETA["fondo_tarjeta"])
        fila.pack(fill="x", pady=(0, 10))
        ent = ttk.Entry(fila, textvariable=self.ruta_datos)
        ent.pack(side="left", fill="x", expand=True)
        ttk.Button(fila, text="Archivo…", style="Secondary.TButton",
                   command=self._elegir_archivo).pack(side="left", padx=(8, 0))
        ttk.Button(fila, text="Carpeta SWAN…", style="Secondary.TButton",
                   command=self._elegir_carpeta).pack(side="left", padx=(6, 0))

        fila_b = tk.Frame(cuerpo, bg=estilo.PALETA["fondo_tarjeta"])
        fila_b.pack(fill="x")
        self.boton_crear = ttk.Button(fila_b, text="Crear", style="Primary.TButton",
                                      command=self._crear)
        self.boton_crear.pack(side="left")
        ttk.Button(fila_b, text="Procesar SWAN…", style="Secondary.TButton",
                   command=self._abrir_swan).pack(side="left", padx=(8, 0))
        ttk.Button(fila_b, text="Descargar ERA5…", style="Secondary.TButton",
                   command=self._abrir_era5).pack(side="left", padx=(6, 0))

        fila_utm = tk.Frame(cuerpo, bg=estilo.PALETA["fondo_tarjeta"])
        fila_utm.pack(fill="x", pady=(12, 0))
        ttk.Label(fila_utm, text="Offset UTM grande (avanzado):",
                  style="CardMuted.TLabel").pack(side="left")
        ttk.Entry(fila_utm, textvariable=self.utm_x, width=10).pack(
            side="left", padx=(6, 0))
        ttk.Entry(fila_utm, textvariable=self.utm_y, width=10).pack(
            side="left", padx=(4, 0))

        self.estado = ttk.Label(self, text="Listo.", style="EstadoListo.TLabel")
        self.estado.pack(anchor="w")

        # Barra de avance (sólo se llena en el modo video, frame a frame).
        self.progreso = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progreso.pack(fill="x", pady=(4, 0))

        # Consola embebida: muestra el reporte que el pipeline imprime.
        self.salida = scrolledtext.ScrolledText(self, height=14,
                                                font=("Consolas", 9))
        self.salida.pack(fill="both", expand=True, pady=(8, 0))

    def _abrir_swan(self):
        """Abre la ventana de corrida SWAN (el paso previo a graficar)."""
        gui_swan.VentanaSwan(self)

    def _abrir_era5(self):
        """Ventana de descarga ERA5 por coordenada (serie + espectro opcional)."""
        win = tk.Toplevel(self)
        win.title("Descargar ERA5 por coordenada")
        win.geometry("360x300")
        campos = {}
        for etiqueta, clave, valor in [
                ("Latitud", "lat", "-37.0"), ("Longitud", "lon", "-73.5"),
                ("Inicio (YYYY-MM-DD)", "inicio", "2024-07-28"),
                ("Fin (YYYY-MM-DD)", "fin", "2024-07-29")]:
            fila = ttk.Frame(win); fila.pack(fill="x", padx=10, pady=4)
            ttk.Label(fila, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ttk.Entry(fila, textvariable=var).pack(side="left", fill="x", expand=True)
            campos[clave] = var
        espectro = tk.BooleanVar(value=True)
        viento = tk.BooleanVar(value=True)
        ttk.Checkbutton(win, text="Incluir espectros 2D", variable=espectro).pack(
            anchor="w", padx=10)
        ttk.Checkbutton(win, text="Incluir viento (clasificación sea/swell)",
                        variable=viento).pack(anchor="w", padx=10)

        def lanzar():
            try:
                lat, lon = validar_inputs_era5(
                    campos["lat"].get(), campos["lon"].get(),
                    campos["inicio"].get(), campos["fin"].get())
            except ValueError as e:
                messagebox.showerror("Datos inválidos", str(e)); return
            win.destroy()
            self.boton_inicio.config(state="disabled")
            self.estado.config(text="Descargando ERA5…")
            estilo.configurar_estado(self.estado, "procesando")
            self.salida.delete("1.0", "end")
            threading.Thread(target=self._descargar_era5, daemon=True,
                             args=(lat, lon, campos["inicio"].get(),
                                   campos["fin"].get(), espectro.get(),
                                   viento.get())).start()

        ttk.Button(win, text="Descargar", command=lanzar).pack(pady=12, ipadx=10)

        def enviar_borde():
            try:
                lat, lon = validar_inputs_era5(
                    campos["lat"].get(), campos["lon"].get(),
                    campos["inicio"].get(), campos["fin"].get())
            except ValueError as e:
                messagebox.showerror("Datos inválidos", str(e))
                return
            nc = (rutas.carpeta_salida(io_era5._nombre_fuente(lat, lon, "serie"))
                  / "era5_serie.nc")
            if not nc.exists():
                messagebox.showwarning(
                    "Sin datos",
                    "Primero descarga la serie ERA5 para esta coordenada.")
                return
            cond = gui_swan.dialogo_condicion(win)
            if not cond:
                return
            modo, tr = cond
            try:
                ds = io_oleaje.cargar(nc)
                borde = borde_oleaje.condicion_borde(ds, modo, tr)
            except Exception as e:
                messagebox.showerror("No se pudo derivar el borde", str(e))
                return
            gui_swan.VentanaSwan(self, borde_inicial=borde)

        ttk.Button(win, text="Enviar a SWAN como borde",
                   command=enviar_borde).pack(pady=(0, 10), ipadx=6)

    def _descargar_era5(self, lat, lon, inicio, fin, con_espectro, con_viento):
        """Corre la descarga fuera del hilo de la GUI y deja el .nc listo para Crear."""
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                ds = io_era5.descargar_serie(lat, lon, inicio, fin,
                                             incluir_viento=con_viento)
                print(f"Serie ERA5 descargada: {ds.sizes.get('time', 0)} pasos.")
                if con_espectro:
                    esp = io_era5.descargar_espectro(lat, lon, inicio, fin)
                    print(f"Espectro ERA5 descargado: {esp.sizes.get('time', 0)} pasos.")
            carpeta = rutas.carpeta_salida(io_era5._nombre_fuente(lat, lon, "serie"))
            nc_serie = carpeta / "era5_serie.nc"
            self._marshal(self.ruta_datos.set, str(nc_serie))
            self._marshal(self._exito, buffer.getvalue(), str(carpeta))
        except Exception:
            self._marshal(self._error, buffer.getvalue() + "\n" + traceback.format_exc())

    def _elegir_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Selecciona el archivo de oleaje",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.mat *.csv *.nc"),
                       ("Todos los archivos", "*.*")])
        if ruta:
            self.ruta_datos.set(ruta)
            config.guardar("ultima_carpeta_datos", str(Path(ruta).parent))

    def _elegir_carpeta(self):
        ruta = filedialog.askdirectory(
            title="Selecciona la carpeta de corrida SWAN",
            initialdir=config.obtener("ultima_carpeta_datos"))
        if ruta:
            self.ruta_datos.set(ruta)
            config.guardar("ultima_carpeta_datos", str(Path(ruta).parent))

    def _crear(self):
        ruta = self.ruta_datos.get().strip()
        if not ruta:
            messagebox.showwarning("Falta el archivo",
                                   "Primero selecciona un archivo de oleaje.")
            return
        if not Path(ruta).exists():
            messagebox.showerror("Archivo no encontrado", f"No existe:\n{ruta}")
            return
        self.boton_crear.config(state="disabled")
        self.boton_inicio.config(state="disabled")
        self.estado.config(text="Procesando…")
        estilo.configurar_estado(self.estado, "procesando")
        self.progreso["value"] = 0
        self.salida.delete("1.0", "end")
        threading.Thread(target=self._procesar, args=(ruta,), daemon=True).start()

    def _procesar(self, ruta):
        """Corre el pipeline capturando lo que imprime, fuera del hilo de la GUI."""
        buffer = io.StringIO()

        def progreso(i, n):
            self._marshal(self._set_progreso, i, n)

        try:
            with redirect_stdout(buffer):
                salida = self._despachar(Path(ruta), progreso)
            self._marshal(self._exito, buffer.getvalue(), str(salida))
        except Exception:
            self._marshal(self._error,
                          buffer.getvalue() + "\n" + traceback.format_exc())

    def _utm_large(self):
        """Offset UTM del campo avanzado, o None si está vacío/ inválido."""
        try:
            return (float(self.utm_x.get()), float(self.utm_y.get()))
        except ValueError:
            return None

    def _despachar(self, ruta, progreso):
        """
        Elige el pipeline según la entrada:
          carpeta SWAN no estacionaria → video del evento (con avance),
          carpeta SWAN estacionaria    → tablero de mapas,
          serie temporal               → tablero de curvas.
        """
        carpeta = ruta.parent if ruta.suffix.lower() == ".swn" else ruta
        utm = self._utm_large()
        if ruta.is_dir() or ruta.suffix.lower() == ".swn":
            if io_swan_nonst.es_corrida_nonst(carpeta):
                return video_swan.generar_videos(carpeta, multipanel=True,
                                                 utm_large=utm, progreso=progreso)[0]
            return tablero_swan.generar_tablero_swan(carpeta, utm_large=utm)
        return tablero_oleaje.generar_tablero(str(ruta))

    def _set_progreso(self, i, n):
        if not self.winfo_exists():
            return
        self.progreso["maximum"] = n
        self.progreso["value"] = i + 1
        self.estado.config(text=f"Generando video… frame {i + 1}/{n}")
        estilo.configurar_estado(self.estado, "procesando")

    def _exito(self, reporte, ruta_salida):
        if not self.winfo_exists():
            return
        self.salida.insert("end", reporte + f"\nResultado: {ruta_salida}\n")
        self.estado.config(text="Listo.")
        estilo.configurar_estado(self.estado, "listo")
        self.progreso["value"] = 0
        self.boton_crear.config(state="normal")
        self.boton_inicio.config(state="normal")
        try:
            os.startfile(ruta_salida)
        except Exception:
            pass

    def _error(self, mensaje):
        if not self.winfo_exists():
            return
        self.salida.insert("end", mensaje)
        self.estado.config(text="Error al generar el resultado.")
        estilo.configurar_estado(self.estado, "error")
        self.progreso["value"] = 0
        self.boton_crear.config(state="normal")
        self.boton_inicio.config(state="normal")
        messagebox.showerror("Error",
                             "Ocurrió un problema. Revisa el detalle en la ventana.")


class AppTablero(tk.Tk):
    """Ventana principal: contenedor que intercambia vistas (inicio/wizards/avanzado)."""

    def __init__(self):
        # Si se lanzó con pythonw (sin consola), blinda los print() del pipeline.
        _asegurar_salida_estandar()
        super().__init__()
        estilo.aplicar_tema(self)
        self.title("Tablero de Oleaje")
        self.geometry("900x660")
        self.minsize(520, 580)
        self.contenedor = ttk.Frame(self)
        self.contenedor.pack(fill="both", expand=True)
        self.contenedor.rowconfigure(0, weight=1)
        self.contenedor.columnconfigure(0, weight=1)
        self._vista = None
        self.mostrar("inicio")

    def _crear_vista(self, nombre):
        """Crea la vista pedida (las vistas son de usar y tirar para empezar limpias)."""
        ir_inicio = lambda: self.mostrar("inicio")
        if nombre == "inicio":
            return VistaInicio(self.contenedor, ir_a=self.mostrar)
        if nombre == "avanzado":
            return VistaAvanzado(self.contenedor, al_inicio=ir_inicio)
        if nombre == "analizar":
            return asistente.Wizard(self.contenedor, "Analizar oleaje en un punto",
                                    pasos_analizar.PASOS_ANALIZAR, ir_inicio)
        if nombre == "modelar":
            return asistente.Wizard(self.contenedor, "Modelar propagación con SWAN",
                                    pasos_modelar.PASOS_MODELAR, ir_inicio)
        if nombre == "ver":
            return asistente.Wizard(self.contenedor, "Ver una corrida SWAN",
                                    pasos_ver.PASOS_VER, ir_inicio)
        raise ValueError(f"Vista desconocida: {nombre}")

    def mostrar(self, nombre):
        """Reemplaza la vista visible por una nueva instancia de `nombre`."""
        if self._vista is not None:
            self._vista.destroy()
        try:
            self._vista = self._crear_vista(nombre)
        except ValueError as e:
            messagebox.showinfo("Aún no disponible",
                                f"Este camino todavía no está disponible.\n({e})")
            self._vista = self._crear_vista("inicio")
        self._vista.grid(row=0, column=0, sticky="nsew")


if __name__ == "__main__":
    _asegurar_salida_estandar()
    AppTablero().mainloop()
