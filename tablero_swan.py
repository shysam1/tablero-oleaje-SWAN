"""
Orquestador del tablero de mapas SWAN.

Recibe la carpeta de una corrida SWAN (p. ej. extremo_Tr100), construye los
Datasets 2D, evalúa qué mapas puede generar y arma una figura multipanel con
los disponibles. Análogo a tablero_oleaje.py, pero para campos espaciales.
"""

from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import io_swan
import productos_swan
import rutas


def _construir_figura(corrida, disponibles):
    """Arma la figura multipanel con los mapas disponibles."""
    n = len(disponibles)
    cols = 2 if n >= 2 else 1
    filas = int(np.ceil(n / cols))
    # Layout 'constrained': separa filas, colorbars y el eje polar sin solapes.
    fig = plt.figure(figsize=(cols * 7, filas * 6.4), layout="constrained")

    for i, item in enumerate(disponibles):
        ax = fig.add_subplot(filas, cols, i + 1, projection=item["proyeccion"])
        item["dibujar"](ax, item["datos"], corrida["meta"])

    meta = corrida["meta"]
    fig.suptitle(f"Tablero SWAN — {meta.get('condicion', '')}   "
                 f"(borde: Hs={meta.get('Hs_borde', '?')} m, "
                 f"Tp={meta.get('Tp_borde', '?')} s, Dp={meta.get('Dp_borde', '?')}°)",
                 fontsize=14, fontweight="bold")
    return fig


def generar_tablero_swan(carpeta, ruta_png=None, utm_large=None, titulos=None):
    """
    Ejecuta el pipeline SWAN completo y devuelve la ruta del tablero PNG.

    1. Carga la corrida (dominios + espectro).
    2. Evalúa e imprime qué mapas se pueden generar.
    3. Dibuja y guarda el tablero con los disponibles.

    utm_large/titulos: opcionales, para corridas de otro lugar o rótulos propios.
    """
    carpeta = Path(carpeta)
    kw = {} if utm_large is None else {"utm_large": utm_large}
    corrida = io_swan.cargar_corrida(carpeta, titulos=titulos, **kw)

    informe = productos_swan.evaluar(corrida)
    productos_swan.imprimir_capacidades(informe)
    disponibles = [it for it in informe if it["disponible"]]

    fig = _construir_figura(corrida, disponibles)
    ruta_png = Path(ruta_png) if ruta_png else \
        rutas.carpeta_salida(carpeta.name) / f"tablero_swan_{carpeta.name}.png"
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"\nTablero SWAN guardado en: {ruta_png}")
    return ruta_png


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    CARPETA = Path(
        r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python"
        r"\SWAN_Coronel\extremo_Tr100")
    generar_tablero_swan(CARPETA)
