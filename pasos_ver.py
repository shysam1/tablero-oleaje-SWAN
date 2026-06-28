"""
Pasos del camino "Ver una corrida SWAN ya hecha".

1. Elegir la carpeta de la corrida.
2. Autodetectar si es estacionaria (mapas) o no estacionaria (video) y mostrar
   lo detectado; ofrecer el offset UTM avanzado.
3. Generar el producto (tablero de mapas o video) y abrirlo.
Reutiliza tablero_swan / video_swan / io_swan_nonst sin tocar el motor.
"""

from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

import asistente
import config
import io_swan
import sistema
import io_swan_nonst
import swan_runner
import tablero_swan
import video_swan


class PasoCarpeta(asistente.Paso):
    titulo = "Elegir carpeta de la corrida"

    def __init__(self, master):
        super().__init__(master)
        self.carpeta = tk.StringVar()
        ttk.Label(self, text="Carpeta con los archivos .swn y las salidas de SWAN:"
                  ).pack(anchor="w", pady=(0, 6))
        fila = ttk.Frame(self); fila.pack(fill="x")
        ttk.Entry(fila, textvariable=self.carpeta).pack(
            side="left", fill="x", expand=True)
        ttk.Button(fila, text="Carpeta…", command=self._elegir).pack(
            side="left", padx=(6, 0))
        self.detalle = ttk.Label(self, foreground="#555")
        self.detalle.pack(anchor="w", pady=(8, 0))

    def _elegir(self):
        d = filedialog.askdirectory(
            title="Carpeta de la corrida SWAN",
            initialdir=config.obtener("ultima_carpeta_swan"))
        if not d:
            return
        self.carpeta.set(d)
        config.guardar("ultima_carpeta_swan", d)
        casos = swan_runner.casos_ordenados(d)
        self.detalle.config(
            text=(f"Casos detectados: {', '.join(casos)}" if casos
                  else "No se encontraron archivos .swn en la carpeta."))

    def validar(self):
        d = self.carpeta.get().strip()
        if not d or not Path(d).is_dir():
            return False, "Elige una carpeta válida con la corrida SWAN."
        return True, ""

    def recoger(self, contexto):
        contexto["carpeta"] = self.carpeta.get().strip()


class PasoTipo(asistente.Paso):
    titulo = "Tipo de corrida"

    def __init__(self, master):
        super().__init__(master)
        self.info = ttk.Label(self, foreground="#333", justify="left")
        self.info.pack(anchor="w")
        fila = ttk.Frame(self); fila.pack(fill="x", pady=(10, 0))
        ttk.Label(fila, text="Offset UTM grande (avanzado):",
                  foreground="#888").pack(side="left")
        self.utm_x = tk.StringVar(value="620494")    # default Coronel (Golfo de Arauco)
        self.utm_y = tk.StringVar(value="5876451")
        ttk.Entry(fila, textvariable=self.utm_x, width=10).pack(side="left", padx=(4, 0))
        ttk.Entry(fila, textvariable=self.utm_y, width=10).pack(side="left", padx=(2, 0))
        self.nonst = False                 # se actualiza en entrar()

    def entrar(self, contexto):
        carpeta = Path(contexto["carpeta"])
        self.nonst = io_swan_nonst.es_corrida_nonst(carpeta)
        tipo = ("no estacionaria → se generará un VIDEO del evento" if self.nonst
                else "estacionaria → se generará un TABLERO DE MAPAS")
        self.info.config(text=f"Carpeta: {carpeta.name}\nDetectada como {tipo}.")
        utm = io_swan.inferir_utm_desde_carpeta(carpeta)
        self.utm_x.set(str(utm["utm_x"]))
        self.utm_y.set(str(utm["utm_y"]))
        contexto["utm_mensaje"] = utm.get("mensaje", "")

    def recoger(self, contexto):
        contexto["nonst"] = self.nonst
        try:
            contexto["utm_large"] = (float(self.utm_x.get()), float(self.utm_y.get()))
        except ValueError:
            contexto["utm_large"] = None


class PasoGenerar(asistente.Paso):
    titulo = "Generar y ver"

    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Genera el producto y se abrirá al terminar.").pack(
            anchor="w")
        self.boton = ttk.Button(self, text="Generar", style="Primary.TButton",
                                  command=self._generar)
        self.boton.pack(anchor="w", pady=(8, 0))
        self.resultado = None

    def entrar(self, contexto):
        self._contexto = contexto
        self.resultado = None
        producto = "video" if contexto.get("nonst") else "tablero de mapas"
        self.boton.config(text=f"Generar {producto}")

    def _generar(self):
        ctx = self._contexto
        carpeta = ctx["carpeta"]
        utm = ctx.get("utm_large")
        nonst = ctx.get("nonst")

        def trabajo(log, progreso):
            if nonst:
                return video_swan.generar_videos(
                    carpeta, multipanel=True, utm_large=utm, progreso=progreso)[0]
            return tablero_swan.generar_tablero_swan(carpeta, utm_large=utm)

        def al_terminar(res):
            if res is None:
                return
            self.resultado = res
            self.wizard.log.insert("end", f"Resultado: {res}\n")
            try:
                sistema.abrir_archivo(res)
            except Exception as e:
                self.wizard.log.insert("end", f"No se pudo abrir {res}: {e}\n")

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if self.resultado is None:
            return False, "Pulsa «Generar» y espera a que termine antes de finalizar."
        return True, ""


PASOS_VER = [PasoCarpeta, PasoTipo, PasoGenerar]
