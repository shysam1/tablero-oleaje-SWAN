"""
Pasos del camino "Analizar oleaje en un punto".

1. Origen de datos: archivo propio (.mat/.csv/.nc) o descarga ERA5 por coordenada.
2. Revisión: carga, validación física y qué productos se podrán generar.
3. Generar el tablero de curvas y abrirlo.
Reutiliza io_era5 / io_oleaje / validacion / productos / tablero_oleaje / rutas.
"""

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import asistente
import config
import rutas
import io_era5
import io_oleaje
import validacion
import productos
import tablero_oleaje


class PasoOrigen(asistente.Paso):
    titulo = "Origen de los datos"

    def __init__(self, master):
        super().__init__(master)
        self.modo = tk.StringVar(value="archivo")
        self.ruta = tk.StringVar()
        ttk.Radiobutton(self, text="Tengo un archivo (.mat / .csv / .nc)",
                        variable=self.modo, value="archivo",
                        command=self._refrescar).pack(anchor="w")
        fila = ttk.Frame(self); fila.pack(fill="x", padx=(20, 0))
        ttk.Entry(fila, textvariable=self.ruta).pack(side="left", fill="x", expand=True)
        self.boton_arch = ttk.Button(fila, text="Archivo…", command=self._elegir)
        self.boton_arch.pack(side="left", padx=(6, 0))

        ttk.Radiobutton(self, text="Descargar de ERA5 por coordenada",
                        variable=self.modo, value="era5",
                        command=self._refrescar).pack(anchor="w", pady=(10, 0))
        self.marco_era5 = ttk.Frame(self)
        self.marco_era5.pack(fill="x", padx=(20, 0))
        self.campos = {}
        self.entradas_era5 = []            # Entry anidados, para habilitar/deshabilitar
        for etiqueta, clave, valor in [
                ("Latitud", "lat", "-37.0"), ("Longitud", "lon", "-73.5"),
                ("Inicio (YYYY-MM-DD)", "inicio", "2024-07-28"),
                ("Fin (YYYY-MM-DD)", "fin", "2024-07-29")]:
            f = ttk.Frame(self.marco_era5); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ent = ttk.Entry(f, textvariable=var)
            ent.pack(side="left", fill="x", expand=True)
            self.campos[clave] = var
            self.entradas_era5.append(ent)
        self.viento = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.marco_era5, text="Incluir viento (sea/swell)",
                        variable=self.viento).pack(anchor="w")
        self.boton_desc = ttk.Button(self.marco_era5, text="Descargar serie ERA5",
                                     command=self._descargar)
        self.boton_desc.pack(anchor="w", pady=(4, 0))
        self.nc_descargado = None
        self._refrescar()

    def _refrescar(self):
        es_arch = self.modo.get() == "archivo"
        self.boton_arch.config(state="normal" if es_arch else "disabled")
        estado_era5 = "normal" if not es_arch else "disabled"
        for hijo in self.marco_era5.winfo_children():
            try:
                hijo.config(state=estado_era5)
            except tk.TclError:
                pass
        # Los Entry van dentro de sub-frames, así que winfo_children no los alcanza.
        for ent in self.entradas_era5:
            ent.config(state=estado_era5)

    def _elegir(self):
        r = filedialog.askopenfilename(
            title="Archivo de oleaje",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.mat *.csv *.nc"), ("Todos", "*.*")])
        if r:
            self.ruta.set(r)
            config.guardar("ultima_carpeta_datos", str(Path(r).parent))

    def _descargar(self):
        try:
            lat = float(self.campos["lat"].get()); lon = float(self.campos["lon"].get())
            inicio = self.campos["inicio"].get(); fin = self.campos["fin"].get()
            if not (inicio and fin):
                raise ValueError("Faltan fechas de inicio/fin.")
        except ValueError as e:
            messagebox.showerror("Datos inválidos", str(e)); return

        def trabajo(log, progreso):
            ds = io_era5.descargar_serie(lat, lon, inicio, fin,
                                         incluir_viento=self.viento.get())
            log(f"Serie ERA5 descargada: {ds.sizes.get('time', 0)} pasos.")
            carpeta = rutas.carpeta_salida(io_era5._nombre_fuente(lat, lon, "serie"))
            return str(carpeta / "era5_serie.nc")

        def al_terminar(nc):
            if nc is None:
                return
            self.nc_descargado = nc
            self.ruta.set(nc)
            self.wizard.log.insert("end", f"Listo: {nc}\n")

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if self.modo.get() == "archivo":
            r = self.ruta.get().strip()
            if not r or not Path(r).exists():
                return False, "Selecciona un archivo de oleaje existente."
            return True, ""
        if not self.nc_descargado or not Path(self.nc_descargado).exists():
            return False, "Descarga la serie ERA5 antes de continuar."
        return True, ""

    def recoger(self, contexto):
        contexto["ruta_datos"] = self.ruta.get().strip()


class PasoRevision(asistente.Paso):
    titulo = "Revisión de los datos"

    def __init__(self, master):
        super().__init__(master)
        self.texto = tk.Text(self, height=14, font=("Consolas", 9), wrap="word")
        self.texto.pack(fill="both", expand=True)

    def entrar(self, contexto):
        self.texto.config(state="normal")
        self.texto.delete("1.0", "end")
        try:
            ds = io_oleaje.cargar(contexto["ruta_datos"])
            variables = ", ".join(ds.data_vars) or "(ninguna)"
            n = int(ds.sizes.get("time", 0))
            self.texto.insert("end", f"Variables presentes: {variables}\n")
            self.texto.insert("end", f"Pasos de tiempo: {n}\n\n")
            self.texto.insert("end", "Validación física:\n")
            for r in validacion.validar(ds):
                if not r["aplicable"]:
                    self.texto.insert("end", f"  [n/a] {r['nombre']}: {r['detalle']}\n")
                elif r["n_falla"] == 0:
                    self.texto.insert("end", f"  [ok ] {r['nombre']}\n")
                else:
                    self.texto.insert("end",
                                      f"  [!! ] {r['nombre']}: {r['n_falla']}/{r['n_total']}\n")
            self.texto.insert("end", "\nProductos que se podrán generar:\n")
            for it in productos.evaluar(ds):
                if it["disponible"]:
                    self.texto.insert("end", f"  ✓ {it['nombre']}\n")
                else:
                    self.texto.insert("end",
                                      f"  ✗ {it['nombre']} (faltan: {', '.join(it['faltan'])})\n")
        except Exception as e:
            self.texto.insert("end", f"Error al analizar el archivo:\n{e}\n")
        finally:
            self.texto.config(state="disabled")


class PasoTablero(asistente.Paso):
    titulo = "Generar el tablero"

    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Genera el tablero de curvas y se abre al terminar."
                  ).pack(anchor="w")
        ttk.Button(self, text="Generar tablero",
                   command=self._generar).pack(anchor="w", pady=(8, 0))
        self.resultado = None

    def entrar(self, contexto):
        self._contexto = contexto
        self.resultado = None

    def _generar(self):
        ruta = self._contexto["ruta_datos"]

        def trabajo(log, progreso):
            return tablero_oleaje.generar_tablero(str(ruta))

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
            return False, "Pulsa «Generar tablero» y espera a que termine."
        return True, ""


PASOS_ANALIZAR = [PasoOrigen, PasoRevision, PasoTablero]
