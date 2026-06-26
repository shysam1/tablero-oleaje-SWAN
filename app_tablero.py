"""
Interfaz gráfica para generar el tablero de oleaje.

Permite elegir un archivo de oleaje (.mat/.csv/.nc) o una carpeta de corrida
SWAN, pulsar "Crear" y genera el producto que corresponda reutilizando los
pipelines. Autodetecta tres modos:
  - serie temporal (.mat/.csv/.nc)        → tablero de curvas (PNG),
  - carpeta SWAN estacionaria             → tablero de mapas (PNG),
  - carpeta SWAN no estacionaria (NonSt)  → video del evento (MP4/GIF).
Muestra el reporte del pipeline y abre el resultado al terminar.

El cálculo corre en un hilo aparte para que la ventana no se congele; en el
modo video, una barra reporta el avance frame a frame.
"""

import io
import os
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


def validar_inputs_era5(lat_txt, lon_txt, inicio, fin):
    """Convierte y valida lat/lon; devuelve (lat, lon). Lanza ValueError si no sirven."""
    lat = float(lat_txt)
    lon = float(lon_txt)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Latitud/longitud fuera de rango.")
    if not (inicio and fin):
        raise ValueError("Faltan fechas de inicio/fin.")
    return lat, lon


class AppTablero(tk.Tk):
    """Ventana principal de la aplicación."""

    def __init__(self):
        super().__init__()
        self.title("Tablero de Oleaje")
        self.geometry("680x550")
        self.minsize(600, 490)
        self.ruta_datos = tk.StringVar(value="")
        # Offset UTM del nodo (0,0) del dominio grande SWAN (default: Golfo de
        # Arauco). Sólo afecta las etiquetas UTM de los mapas/videos; cámbialo
        # para una corrida de otro lugar.
        self.utm_x = tk.StringVar(value="620494")
        self.utm_y = tk.StringVar(value="5876451")
        self._construir_widgets()

    def _construir_widgets(self):
        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Tablero de Oleaje",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(marco, text="Serie temporal (.mat/.csv/.nc) → curvas. "
                  "Carpeta SWAN → mapas. Carpeta SWAN no estacionaria → video.",
                  foreground="#555").pack(anchor="w", pady=(0, 10))

        # Selector: campo de texto + botones para archivo o carpeta SWAN.
        fila = ttk.Frame(marco)
        fila.pack(fill="x", pady=4)
        ttk.Entry(fila, textvariable=self.ruta_datos).pack(
            side="left", fill="x", expand=True)
        ttk.Button(fila, text="Archivo…", command=self._elegir_archivo).pack(
            side="left", padx=(6, 0))
        ttk.Button(fila, text="Carpeta SWAN…", command=self._elegir_carpeta).pack(
            side="left", padx=(6, 0))

        fila_b = ttk.Frame(marco)
        fila_b.pack(pady=10)
        self.boton_crear = ttk.Button(fila_b, text="Crear", command=self._crear)
        self.boton_crear.pack(side="left", ipadx=10, ipady=4)
        ttk.Button(fila_b, text="Procesar SWAN…", command=self._abrir_swan).pack(
            side="left", padx=(8, 0), ipadx=6, ipady=4)
        ttk.Button(fila_b, text="Descargar ERA5…", command=self._abrir_era5).pack(
            side="left", padx=(8, 0), ipadx=6, ipady=4)

        # Campo avanzado: offset UTM del dominio grande SWAN (sólo mapas/videos).
        fila_utm = ttk.Frame(marco)
        fila_utm.pack(fill="x", pady=(0, 2))
        ttk.Label(fila_utm, text="Offset UTM grande (avanzado):",
                  foreground="#888").pack(side="left")
        ttk.Entry(fila_utm, textvariable=self.utm_x, width=10).pack(
            side="left", padx=(4, 0))
        ttk.Entry(fila_utm, textvariable=self.utm_y, width=10).pack(
            side="left", padx=(2, 0))

        self.estado = ttk.Label(marco, text="Listo.", foreground="#1f6feb")
        self.estado.pack(anchor="w")

        # Barra de avance (sólo se llena en el modo video, frame a frame).
        self.progreso = ttk.Progressbar(marco, mode="determinate", maximum=100)
        self.progreso.pack(fill="x", pady=(4, 0))

        # Consola embebida: muestra el reporte que el pipeline imprime.
        self.salida = scrolledtext.ScrolledText(marco, height=14, font=("Consolas", 9))
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
            self.estado.config(text="Descargando ERA5…", foreground="#d18616")
            self.salida.delete("1.0", "end")
            threading.Thread(target=self._descargar_era5, daemon=True,
                             args=(lat, lon, campos["inicio"].get(),
                                   campos["fin"].get(), espectro.get(),
                                   viento.get())).start()

        ttk.Button(win, text="Descargar", command=lanzar).pack(pady=12, ipadx=10)

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
            # Dejar el .nc seleccionado para que el botón Crear genere el tablero.
            self.after(0, self.ruta_datos.set, str(nc_serie))
            self.after(0, self._exito, buffer.getvalue(), str(carpeta))
        except Exception:
            self.after(0, self._error, buffer.getvalue() + "\n" + traceback.format_exc())

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

        # Deshabilitar el botón y lanzar el cálculo en segundo plano.
        self.boton_crear.config(state="disabled")
        self.estado.config(text="Procesando…", foreground="#d18616")
        self.progreso["value"] = 0
        self.salida.delete("1.0", "end")
        threading.Thread(target=self._procesar, args=(ruta,), daemon=True).start()

    def _procesar(self, ruta):
        """Corre el pipeline capturando lo que imprime, fuera del hilo de la GUI."""
        buffer = io.StringIO()

        def progreso(i, n):               # callback del escritor de video
            self.after(0, self._set_progreso, i, n)

        try:
            with redirect_stdout(buffer):
                salida = self._despachar(Path(ruta), progreso)
            self.after(0, self._exito, buffer.getvalue(), str(salida))
        except Exception:
            self.after(0, self._error,
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
        Devuelve la ruta del archivo generado (PNG o video).
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
        """Refleja el avance del video (frame i de n) en la barra y el estado."""
        self.progreso["maximum"] = n
        self.progreso["value"] = i + 1
        self.estado.config(text=f"Generando video… frame {i + 1}/{n}",
                           foreground="#d18616")

    def _exito(self, reporte, ruta_salida):
        self.salida.insert("end", reporte + f"\nResultado: {ruta_salida}\n")
        self.estado.config(text="Listo.", foreground="#1f6feb")
        self.progreso["value"] = 0
        self.boton_crear.config(state="normal")
        try:
            os.startfile(ruta_salida)     # abre PNG o video con el visor por defecto
        except Exception:
            pass

    def _error(self, mensaje):
        self.salida.insert("end", mensaje)
        self.estado.config(text="Error al generar el resultado.", foreground="#d1242f")
        self.progreso["value"] = 0
        self.boton_crear.config(state="normal")
        messagebox.showerror("Error",
                             "Ocurrió un problema. Revisa el detalle en la ventana.")


if __name__ == "__main__":
    AppTablero().mainloop()
