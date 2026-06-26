"""
Genera la batimetría (.bot) de un caso SWAN a partir de la malla de cómputo.

Proyecta los nodos de la malla (UTM) a lat/lon, muestrea un raster de batimetría
(descargado de GEBCO/ETOPO por coordenadas, o uno local) e escribe el .bot con la
misma convención que lee io_swan (reshape + flipud). SWAN usa profundidad positiva
hacia abajo, así que depth = -elevation.

La parte de red (descarga) está aislada de la lógica pura, que se testea con
rasters sintéticos sin tocar internet.
"""

import re
from pathlib import Path

import numpy as np
import xarray as xr


def epsg_utm(zona):
    """
    EPSG de una zona UTM: '19S'->32719, '18S'->32718, '19N'->32619.
    Lanza ValueError si la cadena no es una zona válida.
    """
    texto = str(zona).strip().upper()
    m = re.fullmatch(r"(\d{1,2})\s*([NS])", texto)
    if not m:
        raise ValueError(f"Zona UTM inválida: {zona!r} (usa p. ej. '19S').")
    numero = int(m.group(1))
    if not 1 <= numero <= 60:
        raise ValueError(f"Huso UTM fuera de rango: {numero}")
    return (32700 if m.group(2) == "S" else 32600) + numero


_ALIAS_LAT = ("lat", "latitude", "y")
_ALIAS_LON = ("lon", "longitude", "x")
_ALIAS_ELEV = ("elevation", "altitude", "z")


def _normalizar_raster(ds):
    """
    Deja el raster con dimensiones 'lat'/'lon' (ascendentes) y la variable de
    elevación llamada 'elevation' (m, positivo hacia arriba), venga de ETOPO
    (altitude/latitude/longitude) o GEBCO (elevation/lat/lon).
    """
    ren = {}
    for cand in _ALIAS_LAT:
        if cand in ds.variables and cand != "lat":
            ren[cand] = "lat"
            break
    for cand in _ALIAS_LON:
        if cand in ds.variables and cand != "lon":
            ren[cand] = "lon"
            break
    var = next((v for v in _ALIAS_ELEV if v in ds.data_vars), None)
    if var is None:
        raise ValueError(
            f"El raster no tiene variable de elevación reconocible (busqué {_ALIAS_ELEV}).")
    if var != "elevation":
        ren[var] = "elevation"
    ds = ds.rename(ren)
    return ds[["elevation"]].sortby("lat").sortby("lon")


def generar_bot(malla, zona_utm, carpeta, raster=None, nombre="bati.bot", margen=0.05):
    """
    Escribe el .bot de la malla (UTM) muestreando un raster de batimetría.

    malla: dict {xpc, ypc, xlenc, ylenc, mxc, myc}. zona_utm: p. ej. '19S'.
    raster: Dataset normalizado (lat/lon/elevation); si None, se descarga por bbox.
    Devuelve (ruta_bot, meta) con meta = {n_nodos, prof_min, prof_max, pct_tierra, epsg}.
    """
    from pyproj import Transformer
    from scipy.interpolate import RegularGridInterpolator

    mxc, myc = int(malla["mxc"]), int(malla["myc"])
    nx, ny = mxc + 1, myc + 1
    dx = float(malla["xlenc"]) / mxc
    dy = float(malla["ylenc"]) / myc
    xs = float(malla["xpc"]) + np.arange(nx) * dx       # oeste→este
    ys = float(malla["ypc"]) + np.arange(ny) * dy       # sur→norte
    gx, gy = np.meshgrid(xs, ys)                        # (ny, nx)

    epsg = epsg_utm(zona_utm)
    a_geo = Transformer.from_crs(epsg, 4326, always_xy=True)
    lon_nodos, lat_nodos = a_geo.transform(gx, gy)      # (ny, nx)

    carpeta = Path(carpeta)
    if raster is None:
        raster = descargar_raster(float(lat_nodos.min()) - margen,
                                  float(lat_nodos.max()) + margen,
                                  float(lon_nodos.min()) - margen,
                                  float(lon_nodos.max()) + margen,
                                  carpeta / "_raster_bati.nc")

    lats = raster["lat"].values
    lons = raster["lon"].values
    elev = np.asarray(raster["elevation"].values, dtype=float)
    interp = RegularGridInterpolator((lats, lons), elev,
                                     bounds_error=False, fill_value=None)
    # Recortar al rango del raster: en los bordes usa el valor del borde (no extrapola).
    plat = np.clip(lat_nodos.ravel(), lats.min(), lats.max())
    plon = np.clip(lon_nodos.ravel(), lons.min(), lons.max())
    elev_nodos = interp(np.column_stack([plat, plon])).reshape(ny, nx)
    depth = -elev_nodos                                 # SWAN: profundidad +hacia abajo

    bat = np.flipud(depth).ravel()                      # convención inversa de io_swan
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_text("\n".join(f"{v:.2f}" for v in bat))

    meta = {"n_nodos": int(bat.size),
            "prof_min": float(np.nanmin(depth)), "prof_max": float(np.nanmax(depth)),
            "pct_tierra": float(np.mean(depth <= 0) * 100.0), "epsg": epsg}
    return ruta, meta
