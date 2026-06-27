"""
Ingesta de series de oleaje y construcción de un Dataset de xarray.

Convierte un archivo de oleaje (.mat, .csv o .nc) en un xarray.Dataset con una
coordenada temporal real y las variables de oleaje (Hs, Tp, Dir) etiquetadas con
sus unidades. Permite guardar el resultado en NetCDF y volver a cargarlo.

Este es el cimiento del pipeline: todo lo demás opera sobre el Dataset que entrega.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xarray as xr
from scipy.io import loadmat


# Metadatos de cada variable (convención CF: nombre largo y unidades).
# El registro también define qué variables de oleaje "conoce" el pipeline.
ATRIBUTOS_VARIABLES = {
    "Hs":  {"long_name": "Altura significativa", "units": "m"},
    "Tp":  {"long_name": "Periodo peak", "units": "s"},
    "Dir": {"long_name": "Dirección media de procedencia", "units": "deg"},
}

# Orden de columnas del .mat de Talcahuano (variable 'DataTarea').
COLUMNAS_MAT = ["anio", "mes", "dia", "hora", "Hs", "Tp", "Dir"]

# Columnas que definen el instante de cada registro.
COLUMNAS_TIEMPO = ["anio", "mes", "dia", "hora"]


def _leer_mat(ruta, variable="DataTarea", columnas=COLUMNAS_MAT):
    """Lee una matriz numérica de un .mat y le pone nombres de columna."""
    datos = loadmat(ruta)
    if variable not in datos:
        # loadmat mete claves internas (__header__, __version__, …): se filtran
        # para listar sólo las variables reales en el mensaje de ayuda.
        disponibles = [k for k in datos if not k.startswith("__")]
        raise ValueError(
            f"El .mat no contiene la variable esperada {variable!r}. "
            f"Variables disponibles: {', '.join(disponibles) or '(ninguna)'}. "
            f"Indica la correcta con variable_mat=...")
    matriz = np.asarray(datos[variable])
    if matriz.ndim != 2 or matriz.shape[1] != len(columnas):
        raise ValueError(
            f"La variable {variable!r} del .mat tiene forma {matriz.shape}; "
            f"se esperaba una matriz 2D de {len(columnas)} columnas "
            f"({', '.join(columnas)}).")
    return pd.DataFrame(matriz, columns=columnas)


def _leer_csv(ruta, mapeo=None):
    """Lee un .csv; 'mapeo' renombra columnas al nombre canónico si hace falta."""
    df = pd.read_csv(ruta)
    if mapeo:
        df = df.rename(columns=mapeo)
    return df


def _columna_tiempo(df):
    """Construye la coordenada temporal a partir de anio/mes/dia/hora."""
    partes = df[COLUMNAS_TIEMPO].astype(int).rename(
        columns={"anio": "year", "mes": "month", "dia": "day", "hora": "hour"})
    return pd.to_datetime(partes)


def construir_dataset(df, atributos_globales=None):
    """
    Convierte un DataFrame (con anio/mes/dia/hora + variables) en un Dataset.

    Solo incluye las variables de oleaje que estén realmente presentes en el
    DataFrame: esa es la base del comportamiento adaptativo del pipeline.
    """
    tiempo = _columna_tiempo(df)
    presentes = [v for v in ATRIBUTOS_VARIABLES if v in df.columns]

    ds = xr.Dataset(
        data_vars={v: ("time", df[v].to_numpy(dtype=float)) for v in presentes},
        coords={"time": tiempo.values},
    )

    # Etiquetar cada variable con su nombre largo y unidades.
    for v in presentes:
        ds[v].attrs.update(ATRIBUTOS_VARIABLES[v])
    if atributos_globales:
        ds.attrs.update(atributos_globales)
    return ds


def cargar(ruta, variable_mat="DataTarea", mapeo_csv=None):
    """
    Carga oleaje desde .mat, .csv o .nc y devuelve un xarray.Dataset.

    - .nc  : se abre directamente (ya viene en formato Dataset).
    - .mat : matriz numérica nombrada según COLUMNAS_MAT.
    - .csv : columnas canónicas, o renombradas con 'mapeo_csv'.
    """
    ruta = Path(ruta)
    extension = ruta.suffix.lower()

    if extension == ".nc":
        return xr.open_dataset(ruta)
    if extension == ".mat":
        df = _leer_mat(ruta, variable=variable_mat)
    elif extension == ".csv":
        df = _leer_csv(ruta, mapeo=mapeo_csv)
    else:
        raise ValueError(f"Extensión no soportada: {extension}")

    return construir_dataset(df, atributos_globales={"fuente": ruta.name})


def guardar_netcdf(ds, ruta):
    """Guarda el Dataset en NetCDF y devuelve la ruta."""
    ruta = Path(ruta)
    ds.to_netcdf(ruta)
    return ruta


if __name__ == "__main__":
    # Permite imprimir tildes en la consola de Windows sin que reviente.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # Caso base: nodo de oleaje frente a Talcahuano (Tarea 3 Costas).
    RUTA_MAT = Path(
        r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python"
        r"\Tarea 3 Costas\Datos_Nodo10_37S_75W_Talcahuano.mat")
    RUTA_NC = Path(__file__).with_name("oleaje_talcahuano.nc")

    ds = cargar(RUTA_MAT)
    print(ds)

    ruta = guardar_netcdf(ds, RUTA_NC)
    print(f"\nNetCDF guardado en: {ruta}")

    # Verificación del round-trip: recargar desde NetCDF y comparar valores.
    ds_recargado = cargar(RUTA_NC)
    print(f"Round-trip NetCDF coincide: {ds.equals(ds_recargado.load())}")
    ds_recargado.close()
