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


def _destino_salidas(ruta_entrada):
    """Carpeta de salida del tablero: junto al .nc si ya está bajo salidas/."""
    ruta_entrada = Path(ruta_entrada)
    try:
        if ruta_entrada.resolve().is_relative_to(rutas.RAIZ_SALIDAS.resolve()):
            return ruta_entrada.parent
    except ValueError:
        pass
    return rutas.carpeta_salida(ruta_entrada.stem)


def _construir_figura(ds, disponibles, omitidos=None):
    """Arma la figura multipanel con los productos disponibles."""
    n = len(disponibles)
    cols = 3 if n >= 3 else max(n, 1)
    filas = int(np.ceil(n / cols))
    fig = plt.figure(figsize=(cols * 5.2, filas * 4.2))

    for i, item in enumerate(disponibles):
        ax = fig.add_subplot(filas, cols, i + 1, projection=item["proyeccion"])
        item["dibujar"](ax, item["resultado"])

    fuente = ds.attrs.get("fuente", "oleaje")
    n = int(ds.sizes.get("time", 0))
    if n == 0:
        titulo_rango = "sin datos temporales"
    else:
        t0 = pd.to_datetime(ds["time"].values[0]).strftime("%Y-%m")
        t1 = pd.to_datetime(ds["time"].values[-1]).strftime("%Y-%m")
        titulo_rango = f"{t0} a {t1}"
    fig.suptitle(f"Tablero de oleaje — {fuente}   ({titulo_rango})",
                 fontsize=15, fontweight="bold")
    if omitidos:
        notas = "; ".join(
            f"{it['nombre']}: {it.get('motivo') or ', '.join(it.get('faltan') or [])}"
            for it in omitidos[:6])
        if len(omitidos) > 6:
            notas += f" (+{len(omitidos) - 6} más)"
        fig.text(0.5, 0.01, f"Paneles omitidos — {notas}",
                 ha="center", va="bottom", fontsize=8, color="#555", wrap=True)
    fig.tight_layout(rect=[0, 0.04 if omitidos else 0, 1, 0.97])
    return fig


def generar_tablero(ruta_entrada, ruta_nc=None, ruta_png=None, cargar_fn=None):
    """
    Ejecuta el pipeline completo y devuelve la ruta del tablero PNG.

    cargar_fn: opcional, p. ej. para adjuntar espectro ERA5 desde era5_espectro.nc.
    """
    ruta_entrada = Path(ruta_entrada)
    cargar = cargar_fn or io_oleaje.cargar
    ds = cargar(ruta_entrada)
    try:
        destino = _destino_salidas(ruta_entrada)

        if ruta_entrada.suffix.lower() != ".nc":
            ruta_nc = Path(ruta_nc) if ruta_nc else destino / f"oleaje_{ruta_entrada.stem}.nc"
            io_oleaje.guardar_netcdf(ds, ruta_nc)
            print(f"NetCDF guardado en: {ruta_nc}")

        validacion.imprimir_reporte(validacion.validar(ds))

        informe = productos.evaluar(ds)
        productos.imprimir_capacidades(informe)
        disponibles = [it for it in informe if it["disponible"]]
        omitidos = [it for it in informe if not it["disponible"]]

        if not disponibles:
            raise ValueError(
                "No se pudo generar ningún panel del tablero: el archivo no tiene "
                "variables de oleaje suficientes (revisa el reporte de validación "
                "de arriba). Verifica que la fuente incluya Hs/Tp/Dir.")

        fig = _construir_figura(ds, disponibles, omitidos=omitidos or None)
        etiqueta = destino.name
        ruta_png = Path(ruta_png) if ruta_png else destino / f"tablero_{etiqueta}.png"
        fig.savefig(ruta_png, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"Tablero guardado en: {ruta_png}")
        return ruta_png
    finally:
        ds.close()


if __name__ == "__main__":
    import argparse

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Genera tablero de curvas desde serie de oleaje.")
    ap.add_argument("entrada", type=Path, help="Archivo .mat, .csv o .nc con serie temporal")
    generar_tablero(ap.parse_args().entrada)
