"""
Orquestador del tablero de oleaje.

Punto de entrada del pipeline. Recibe un archivo de oleaje (.mat/.csv/.nc),
construye el Dataset, lo guarda en NetCDF, valida físicamente, evalúa qué
productos puede generar y arma una figura multipanel solo con los disponibles.

Uso directo:
    python tablero_oleaje.py
Uso como función:
    from tablero_oleaje import generar_tablero
    generar_tablero("mi_archivo.mat")
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # backend sin ventana: solo guardamos PNG
import matplotlib.pyplot as plt

import io_oleaje
import validacion
import productos
import rutas


def _construir_figura(ds, disponibles):
    """Arma la figura multipanel con los productos disponibles."""
    n = len(disponibles)
    cols = 3 if n >= 3 else n
    filas = int(np.ceil(n / cols))
    fig = plt.figure(figsize=(cols * 5.2, filas * 4.2))

    for i, item in enumerate(disponibles):
        ax = fig.add_subplot(filas, cols, i + 1, projection=item["proyeccion"])
        item["dibujar"](ax, item["resultado"])

    fuente = ds.attrs.get("fuente", "oleaje")
    t0 = pd.to_datetime(ds["time"].values[0]).strftime("%Y-%m")
    t1 = pd.to_datetime(ds["time"].values[-1]).strftime("%Y-%m")
    fig.suptitle(f"Tablero de oleaje — {fuente}   ({t0} a {t1})",
                 fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def generar_tablero(ruta_entrada, ruta_nc=None, ruta_png=None):
    """
    Ejecuta el pipeline completo y devuelve la ruta del tablero PNG.

    1. Carga el archivo y construye el Dataset.
    2. Lo guarda en NetCDF (si la entrada no lo era).
    3. Valida físicamente e imprime el reporte.
    4. Evalúa capacidades e imprime qué se puede generar.
    5. Dibuja y guarda el tablero con los productos disponibles.
    """
    ruta_entrada = Path(ruta_entrada)
    ds = io_oleaje.cargar(ruta_entrada)
    destino = rutas.carpeta_salida(ruta_entrada.stem)

    if ruta_entrada.suffix.lower() != ".nc":
        ruta_nc = Path(ruta_nc) if ruta_nc else destino / f"oleaje_{ruta_entrada.stem}.nc"
        io_oleaje.guardar_netcdf(ds, ruta_nc)
        print(f"NetCDF guardado en: {ruta_nc}")

    validacion.imprimir_reporte(validacion.validar(ds))

    informe = productos.evaluar(ds)
    productos.imprimir_capacidades(informe)
    disponibles = [it for it in informe if it["disponible"]]

    if not disponibles:
        ds.close()
        raise ValueError(
            "No se pudo generar ningún panel del tablero: el archivo no tiene "
            "variables de oleaje suficientes (revisa el reporte de validación "
            "de arriba). Verifica que la fuente incluya Hs/Tp/Dir.")

    fig = _construir_figura(ds, disponibles)
    ruta_png = Path(ruta_png) if ruta_png else destino / f"tablero_{ruta_entrada.stem}.png"
    fig.savefig(ruta_png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    ds.close()

    print(f"\nTablero guardado en: {ruta_png}")
    return ruta_png


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # Caso base: nodo de oleaje frente a Talcahuano (Tarea 3 Costas).
    RUTA_MAT = Path(
        r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python"
        r"\Tarea 3 Costas\Datos_Nodo10_37S_75W_Talcahuano.mat")

    generar_tablero(RUTA_MAT)        # salidas en salidas\<nombre del archivo>\
