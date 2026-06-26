"""
Descarga de oleaje por coordenada desde ERA5 (Copernicus CDS).

Dos productos: serie temporal de parámetros integrados (Hs/Tp/Dir, opcional
viento) y espectros 2D direccionales. Ambos se devuelven como Datasets de xarray
compatibles con el resto del pipeline: la serie entra al tablero de curvas y el
espectro (Efth(time, freq, dir)) a la partición.

La parte de red (cdsapi) está separada de los parsers, que son funciones puras
sobre archivos .nc y se testean sin conexión.
"""

from pathlib import Path

import numpy as np
import xarray as xr

import rutas


def _cliente():
    """
    Devuelve un cdsapi.Client. Si faltan las credenciales ~/.cdsapirc, lanza un
    RuntimeError con el paso a paso para configurarlas (no intenta descargar).
    """
    hogar = Path.home() / ".cdsapirc"
    if not hogar.exists():
        raise RuntimeError(
            "Falta el archivo de credenciales del CDS (~/.cdsapirc).\n"
            "1) Crea una cuenta gratis en https://cds.climate.copernicus.eu\n"
            "2) Acepta los términos del dataset ERA5.\n"
            "3) Copia tu 'url' y 'key' del perfil en un archivo ~/.cdsapirc:\n"
            "     url: https://cds.climate.copernicus.eu/api\n"
            "     key: <UID>:<API-KEY>\n"
            f"   (en este equipo: {hogar})")
    import cdsapi
    return cdsapi.Client()
