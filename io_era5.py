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


# Identificadores del CDS para cada producto.
_DATASET_SERIE = "reanalysis-era5-single-levels"
_DATASET_ESPECTRO = "reanalysis-era5-single-levels"   # var 2D wave spectra (d2fd)

_VARS_SERIE = ["significant_height_of_combined_wind_waves_and_swell",
               "peak_wave_period", "mean_wave_direction"]
_VARS_VIENTO = ["10m_u_component_of_wind", "10m_v_component_of_wind"]


def _rango_fechas(inicio, fin):
    """Listas de años/meses/días/horas (3-horario) que cubren [inicio, fin]."""
    fechas = np.arange(np.datetime64(inicio), np.datetime64(fin) + 1,
                       dtype="datetime64[D]")
    anios = sorted({str(f)[0:4] for f in fechas})
    meses = sorted({str(f)[5:7] for f in fechas})
    dias = sorted({str(f)[8:10] for f in fechas})
    horas = [f"{h:02d}:00" for h in range(0, 24, 3)]
    return anios, meses, dias, horas


def _peticion_serie(lat, lon, inicio, fin, incluir_viento=False, delta=0.25):
    """Diccionario de petición CDS para la serie de parámetros integrados."""
    anios, meses, dias, horas = _rango_fechas(inicio, fin)
    variables = list(_VARS_SERIE) + (list(_VARS_VIENTO) if incluir_viento else [])
    return {
        "product_type": "reanalysis",
        "variable": variables,
        "year": anios, "month": meses, "day": dias, "time": horas,
        "area": [lat + delta, lon - delta, lat - delta, lon + delta],   # N,W,S,E
        "format": "netcdf",
    }


# Nombres cortos del .nc de ERA5 → variables canónicas del pipeline.
_RENOMBRE_SERIE = {"swh": "Hs", "pp1d": "Tp", "mwd": "Dir",
                   "u10": "u10", "v10": "v10"}

_ATRIBUTOS = {
    "Hs": {"long_name": "Altura significativa", "units": "m"},
    "Tp": {"long_name": "Período de pico", "units": "s"},
    "Dir": {"long_name": "Dirección media", "units": "deg"},
}


def _parsear_serie_nc(ruta, lat, lon):
    """Abre el .nc de ERA5, selecciona el punto más cercano y renombra a Hs/Tp/Dir."""
    bruto = xr.open_dataset(ruta)
    punto = bruto.sel(latitude=lat, longitude=lon, method="nearest")
    punto = punto.drop_vars(["latitude", "longitude"], errors="ignore")

    presentes = {k: v for k, v in _RENOMBRE_SERIE.items() if k in punto.data_vars}
    ds = punto[list(presentes)].rename(presentes)
    for v, attrs in _ATRIBUTOS.items():
        if v in ds.data_vars:
            ds[v].attrs.update(attrs)
    ds.attrs["fuente"] = f"ERA5 ({lat:.3f}, {lon:.3f})"
    bruto.close()
    return ds


def _nombre_fuente(lat, lon, sufijo):
    """Identificador de carpeta/archivo de salida para una coordenada."""
    return f"ERA5_{lat:+.2f}_{lon:+.2f}_{sufijo}".replace(".", "p")


def _cache_utilizable(ruta):
    """
    True si el .nc cacheado existe, no está vacío y se puede abrir. Una descarga
    interrumpida puede dejar un .nc de 0 bytes o truncado; confiar en él daría un
    error críptico aguas abajo (o datos a medias), así que se re-descarga.
    """
    try:
        if not ruta.exists() or ruta.stat().st_size == 0:
            return False
        with xr.open_dataset(ruta):
            return True
    except Exception:
        return False


def _retrieve_atomico(dataset, peticion, destino):
    """
    Descarga a un archivo temporal y lo renombra al terminar. Así una descarga
    interrumpida nunca deja en su sitio un .nc a medio escribir que luego parezca
    una cache válida.
    """
    tmp = destino.with_name(destino.name + ".part")
    try:
        _cliente().retrieve(dataset, peticion, str(tmp))
        tmp.replace(destino)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def descargar_serie(lat, lon, inicio, fin, incluir_viento=False):
    """
    Descarga la serie ERA5 de Hs/Tp/Dir (opcional viento) para un punto y rango,
    la cachea como .nc en salidas/ y devuelve un Dataset(time) listo para el
    tablero de curvas.
    """
    carpeta = rutas.carpeta_salida(_nombre_fuente(lat, lon, "serie"))
    destino = carpeta / "era5_serie.nc"
    if not _cache_utilizable(destino):
        _retrieve_atomico(_DATASET_SERIE,
                          _peticion_serie(lat, lon, inicio, fin, incluir_viento),
                          destino)
    return _parsear_serie_nc(destino, lat, lon)


_VARS_ESPECTRO = ["2d_wave_spectra"]    # parámetro d2fd del CDS


def _parsear_espectro_nc(ruta):
    """
    .nc de ERA5 2D spectra → Dataset con Efth(time, freq, dir), des-logueado.

    ERA5 guarda d2fd como log10 de la densidad; aquí se reconstruye 10**d2fd y se
    renombran las dimensiones a (freq, dir) para igualar a leer_espectro_temporal.
    """
    bruto = xr.open_dataset(ruta)
    d2fd = bruto["d2fd"]
    efth = np.power(10.0, d2fd)                       # des-logueo; NaN se propaga
    efth = efth.rename({"frequency": "freq", "direction": "dir"})

    ds = xr.Dataset({"Efth": efth})
    ds["Efth"].attrs = {"long_name": "Densidad de energía", "units": "m2/Hz/deg"}
    ds["freq"].attrs = {"long_name": "Frecuencia", "units": "Hz"}
    ds["dir"].attrs = {"long_name": "Dirección", "units": "deg"}
    bruto.close()
    return ds


def descargar_espectro(lat, lon, inicio, fin):
    """
    Descarga el espectro 2D direccional ERA5 para un punto y rango, lo cachea como
    .nc en salidas/ y devuelve un Dataset con Efth(time, freq, dir) listo para la
    partición.
    """
    carpeta = rutas.carpeta_salida(_nombre_fuente(lat, lon, "espectro"))
    destino = carpeta / "era5_espectro.nc"
    if not _cache_utilizable(destino):
        anios, meses, dias, horas = _rango_fechas(inicio, fin)
        peticion = {"product_type": "reanalysis", "variable": _VARS_ESPECTRO,
                    "year": anios, "month": meses, "day": dias, "time": horas,
                    "area": [lat + 0.25, lon - 0.25, lat - 0.25, lon + 0.25],
                    "format": "netcdf"}
        _retrieve_atomico(_DATASET_ESPECTRO, peticion, destino)
    return _parsear_espectro_nc(destino)
