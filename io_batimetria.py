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


def nodos_esperados_bot(malla):
    """Número de valores que debe tener un .bot para la malla (esquinas de celda)."""
    mxc, myc = int(malla["mxc"]), int(malla["myc"])
    nx, ny = mxc + 1, myc + 1
    return nx * ny, nx, ny, mxc, myc


def leer_bot_como_grilla(ruta_bot, malla):
    """
    Lee un .bot y lo devuelve como grilla de profundidad (ny, nx), ny=myc+1.

    Lanza ValueError si el conteo de valores no coincide con la malla.
    """
    mxc, myc = int(malla["mxc"]), int(malla["myc"])
    nx, ny = mxc + 1, myc + 1
    esperado = nx * ny
    vals = np.array(
        [float(l) for l in Path(ruta_bot).read_text().split() if l.strip()],
        dtype=float,
    )
    if vals.size != esperado:
        raise ValueError(
            f"El .bot tiene {vals.size} valores; la malla {mxc}×{myc} celdas "
            f"requiere {esperado} ({ny}×{nx} nodos).")
    return np.flipud(vals.reshape(ny, nx))


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
    if mxc <= 0 or myc <= 0:
        raise ValueError("mxc y myc deben ser > 0.")
    if float(malla["xlenc"]) <= 0 or float(malla["ylenc"]) <= 0:
        raise ValueError("xlenc y ylenc deben ser > 0.")
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
    import seguridad
    nombre_seguro = seguridad.sanitizar_segmento(nombre, "nombre del .bot")
    ruta = carpeta / nombre_seguro
    if np.any(np.isnan(bat)):
        raise ValueError(
            "La batimetría contiene nodos sin dato (NaN). Reduce el dominio o "
            "usa un raster que cubra toda la malla.")
    ruta.write_text("\n".join(f"{v:.2f}" for v in bat))

    meta = {"n_nodos": int(bat.size),
            "prof_min": float(np.nanmin(depth)), "prof_max": float(np.nanmax(depth)),
            "pct_tierra": float(np.mean(depth <= 0) * 100.0), "epsg": epsg}
    return ruta, meta


# Fuente de batimetría global (ERDDAP de NOAA). ETOPO1 (~1.85 km) confirmado
# estable; cambiar a un dataset más fino si se valida su id/variable.
_BASE_ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
_DATASET_ERDDAP = "etopo180"
_VAR_ERDDAP = "altitude"


def _url_erddap(lat_min, lat_max, lon_min, lon_max):
    """URL ERDDAP (.nc) del recorte por bbox del dataset de batimetría."""
    rango = (f"%5B({lat_min}):({lat_max})%5D"
             f"%5B({lon_min}):({lon_max})%5D")
    return f"{_BASE_ERDDAP}/{_DATASET_ERDDAP}.nc?{_VAR_ERDDAP}{rango}"


def descargar_raster(lat_min, lat_max, lon_min, lon_max, destino):
    """Descarga el recorte de batimetría por HTTP y lo devuelve normalizado."""
    import urllib.request
    import urllib.error
    url = _url_erddap(lat_min, lat_max, lon_min, lon_max)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            tipo = resp.headers.get_content_type()
            cuerpo = resp.read()
    except urllib.error.HTTPError as e:
        # ERDDAP devuelve el detalle del error en el cuerpo; incluirlo ayuda a
        # entender (bbox fuera de rango, dataset movido, etc.).
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        raise RuntimeError(
            f"El servidor de batimetría respondió {e.code} {e.reason}. "
            f"{detalle}".strip()) from e
    except Exception as e:
        raise RuntimeError(
            "No se pudo descargar la batimetría (¿sin internet?). "
            "Usa un archivo de batimetría local.") from e

    # ERDDAP a veces responde 200 con un cuerpo de error (texto/HTML) en vez del
    # .nc: guardar eso a ciegas haría que xarray reventara con un error críptico.
    # Se valida por código, content-type y los bytes mágicos de NetCDF (clásico
    # 'CDF...') o HDF5/NetCDF-4 ('\x89HDF').
    if status and status != 200:
        raise RuntimeError(f"El servidor de batimetría respondió código {status}.")
    es_netcdf = cuerpo[:3] == b"CDF" or cuerpo[:4] == b"\x89HDF"
    if "netcdf" not in (tipo or "") and not es_netcdf:
        muestra = cuerpo[:300].decode("utf-8", "ignore").strip()
        raise RuntimeError(
            "La respuesta del servidor de batimetría no es un NetCDF válido "
            f"(content-type {tipo!r}). Usa un archivo de batimetría local. "
            f"Detalle: {muestra}")
    destino.write_bytes(cuerpo)
    with xr.open_dataset(destino) as raw:
        return _normalizar_raster(raw.load())


def leer_raster_local(ruta):
    """Abre un raster de batimetría propio (.nc) y lo devuelve normalizado."""
    with xr.open_dataset(ruta) as raw:
        return _normalizar_raster(raw.load())
