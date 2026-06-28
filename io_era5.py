"""
Descarga de oleaje por coordenada desde ERA5 (Copernicus CDS).

Dos productos: serie temporal de parámetros integrados (Hs/Tp/Dir, opcional
viento) y espectros 2D direccionales. Ambos se devuelven como Datasets de xarray
compatibles con el resto del pipeline: la serie entra al tablero de curvas y el
espectro (Efth(time, freq, dir)) a la partición.

La parte de red (cdsapi) está separada de los parsers, que son funciones puras
sobre archivos .nc y se testean sin conexión.
"""

import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import xarray as xr

import rutas

_CDS_URL_DEFAULT = "https://cds.climate.copernicus.eu/api"


def ruta_cdsapirc():
    """Ruta del archivo de credenciales CDS en el perfil del usuario."""
    return Path.home() / ".cdsapirc"


def _parsear_cdsapirc(texto):
    """Lee url/key del formato plano que usa cdsapi."""
    url = None
    key = None
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if ":" not in linea:
            continue
        nombre, valor = linea.split(":", 1)
        nombre = nombre.strip().lower()
        valor = valor.strip().strip("'\"")
        if nombre == "url":
            url = valor
        elif nombre == "key":
            key = valor
    return url, key


def leer_credenciales_cds():
    """Devuelve {'url', 'key'} o None si no hay archivo legible."""
    ruta = ruta_cdsapirc()
    if not ruta.is_file():
        return None
    try:
        url, key = _parsear_cdsapirc(ruta.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not key:
        return None
    return {"url": url or _CDS_URL_DEFAULT, "key": key}


def enmascarar_clave_cds(key):
    """Muestra UID y solo los últimos caracteres de la API key."""
    if not key:
        return ""
    if ":" not in key:
        return "****"
    uid, secreto = key.split(":", 1)
    if len(secreto) <= 4:
        return f"{uid}:****"
    return f"{uid}:…{secreto[-4:]}"


def estado_credenciales_cds():
    """Estado para la UI (sin exponer la clave completa)."""
    cred = leer_credenciales_cds()
    ruta = ruta_cdsapirc()
    if not cred:
        return {
            "configurado": False,
            "ruta": str(ruta),
            "url": _CDS_URL_DEFAULT,
            "key_enmascarada": "",
            "uid": "",
        }
    uid = cred["key"].split(":", 1)[0] if ":" in cred["key"] else ""
    return {
        "configurado": True,
        "ruta": str(ruta),
        "url": cred["url"],
        "key_enmascarada": enmascarar_clave_cds(cred["key"]),
        "uid": uid,
    }


def _validar_formato_clave_cds(key):
    key = (key or "").strip()
    if not key or ":" not in key:
        raise ValueError(
            "La clave debe tener formato UID:API-KEY (cópiala desde tu perfil CDS).")
    uid, api = key.split(":", 1)
    uid = uid.strip()
    api = api.strip()
    if not uid.isdigit() or not api:
        raise ValueError(
            "La clave debe ser UID:API-KEY, con UID numérico y la API key del perfil.")
    return uid, api


def _normalizar_url_cds(url):
    from seguridad import validar_url_cds
    url = (url or _CDS_URL_DEFAULT).strip()
    if not url:
        url = _CDS_URL_DEFAULT
    return validar_url_cds(url)


def guardar_credenciales_cds(url, key=None):
    """
    Escribe ~/.cdsapirc. Si key es None o vacío y ya hay credenciales, conserva
    la clave anterior (útil al cambiar solo la URL).
    """
    url = _normalizar_url_cds(url)
    prev = leer_credenciales_cds()
    key_nueva = (key or "").strip()
    if key_nueva:
        uid, api = _validar_formato_clave_cds(key_nueva)
        key_final = f"{uid}:{api}"
    elif prev:
        key_final = prev["key"]
    else:
        raise ValueError("Indica la clave UID:API-KEY de tu cuenta CDS.")

    contenido = f"url: {url}\nkey: {key_final}\n"
    destino = ruta_cdsapirc()
    destino.write_text(contenido, encoding="utf-8")
    try:
        destino.chmod(0o600)
    except OSError:
        pass
    return {
        "mensaje": "Credenciales guardadas.",
        **estado_credenciales_cds(),
    }


def probar_credenciales_cds(url=None, key=None, *, timeout=25):
    """
    Comprueba formato y que el CDS acepte la clave (GET /v2/tasks, sin descarga).
    Si url/key son None, usa el archivo ~/.cdsapirc.
    """
    prev = leer_credenciales_cds()
    url_final = _normalizar_url_cds(url or (prev or {}).get("url"))
    key_raw = (key or "").strip() or (prev or {}).get("key")
    if not key_raw:
        raise ValueError("Indica la clave UID:API-KEY para probar la conexión.")
    uid, api = _validar_formato_clave_cds(key_raw)
    key_final = f"{uid}:{api}"
    endpoint = f"{url_final}/v2/tasks?limit=1"
    req = urllib.request.Request(
        endpoint,
        headers={"PRIVATE-TOKEN": key_final},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return {"mensaje": "El CDS aceptó tus credenciales."}
            raise ValueError(f"Respuesta inesperada del CDS ({resp.status}).")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError(
                "El CDS rechazó la clave. Revisa UID:API-KEY y que aceptaste "
                "los términos del dataset ERA5 en tu cuenta."
            ) from exc
        raise ValueError(
            f"Error del CDS al probar la conexión ({exc.code})."
        ) from exc
    except urllib.error.URLError as exc:
        raise ValueError(
            f"No se pudo contactar al CDS: {exc.reason}"
        ) from exc


def _cliente():
    """
    Devuelve un cdsapi.Client. Si faltan las credenciales ~/.cdsapirc, lanza un
    RuntimeError con el paso a paso para configurarlas (no intenta descargar).
    """
    hogar = ruta_cdsapirc()
    if not leer_credenciales_cds():
        raise RuntimeError(
            "Faltan credenciales del Copernicus CDS.\n"
            "1) Crea una cuenta gratis en https://cds.climate.copernicus.eu\n"
            "2) Acepta los términos del dataset ERA5 en tu perfil.\n"
            "3) En la app: barra lateral → «Credenciales ERA5», o crea el archivo:\n"
            f"     {hogar}\n"
            "     url: https://cds.climate.copernicus.eu/api\n"
            "     key: <UID>:<API-KEY>")
    import cdsapi
    return cdsapi.Client()


# Identificadores del CDS para cada producto.
_DATASET_SERIE = "reanalysis-era5-single-levels"
_DATASET_ESPECTRO = "reanalysis-era5-single-levels"   # var 2D wave spectra (d2fd)

_VARS_SERIE = ["significant_height_of_combined_wind_waves_and_swell",
               "peak_wave_period", "mean_wave_direction"]
_VARS_VIENTO = ["10m_u_component_of_wind", "10m_v_component_of_wind"]

# El CDS suele rechazar peticiones ERA5 horarias NetCDF muy largas (403 cost limits).
_MAX_DIAS_UNA_PETICION = 31
_MIN_DIAS_SUBDIVISION = 7          # no partir tramos más pequeños que esto
# Peticiones simultáneas al CDS (2 es conservador; >2 suele empeorar la cola).
_MAX_TRAMOS_PARALELO = 2


def validar_rango_fechas(inicio, fin):
    """
    Comprueba que inicio/fin sean fechas parseables y fin >= inicio.
    Devuelve (inicio, fin) como cadenas normalizadas.
    """
    s0, s1 = str(inicio).strip(), str(fin).strip()
    if not s0 or not s1:
        raise ValueError("Faltan fechas de inicio/fin.")
    t0 = np.datetime64(s0)
    t1 = np.datetime64(s1)
    if np.isnat(t0) or np.isnat(t1):
        raise ValueError("Fechas de inicio/fin no válidas (usa AAAA-MM-DD).")
    if t1 < t0:
        raise ValueError("La fecha fin debe ser igual o posterior a inicio.")
    return s0, s1


def _dias_rango(inicio, fin):
    """Número de días naturales en [inicio, fin] (ambos inclusive)."""
    s0, s1 = validar_rango_fechas(inicio, fin)
    return int((np.datetime64(s1) - np.datetime64(s0)) / np.timedelta64(1, "D")) + 1


def _particiones_por_dias(inicio, fin, max_dias):
    """Parte [inicio, fin] en bloques consecutivos de hasta `max_dias` días."""
    s0, s1 = validar_rango_fechas(inicio, fin)
    if _dias_rango(s0, s1) <= max_dias:
        return [(s0, s1)]
    partes = []
    cursor = np.datetime64(s0)
    fin_np = np.datetime64(s1)
    while cursor <= fin_np:
        tramo_fin = min(cursor + np.timedelta64(max_dias - 1, "D"), fin_np)
        partes.append((str(cursor)[:10], str(tramo_fin)[:10]))
        cursor = tramo_fin + np.timedelta64(1, "D")
    return partes


def _particiones_descarga(inicio, fin, max_dias=_MAX_DIAS_UNA_PETICION):
    """
    Parte [inicio, fin] en tramos de como máximo `max_dias` días, cortando por
    fin de mes natural cuando el rango es largo (recomendación del CDS).
    """
    s0, s1 = validar_rango_fechas(inicio, fin)
    if _dias_rango(s0, s1) <= max_dias:
        return [(s0, s1)]

    import pandas as pd
    t0, t1 = pd.Timestamp(s0), pd.Timestamp(s1)
    partes = []
    cursor = t0
    while cursor <= t1:
        fin_mes = cursor + pd.offsets.MonthEnd(0)
        tramo_fin = min(fin_mes, t1)
        partes.append((cursor.strftime("%Y-%m-%d"), tramo_fin.strftime("%Y-%m-%d")))
        cursor = tramo_fin + pd.Timedelta(days=1)
    return partes


def _es_error_tamaño_cds(exc):
    msg = str(exc).lower()
    return ("cost limits" in msg or "too large" in msg
            or "request is too large" in msg)


def _ruta_chunk(carpeta, inicio, fin):
    s0, s1 = validar_rango_fechas(inicio, fin)
    d0 = str(np.datetime64(s0))[:10].replace("-", "")
    d1 = str(np.datetime64(s1))[:10].replace("-", "")
    return carpeta / "chunks" / f"tramo_{d0}_{d1}.nc"


def _log_con_rebloqueo(log_fn, lock):
    """Envoltorio thread-safe para mensajes de progreso en descargas paralelas."""
    if not log_fn:
        return None
    def _emitir(mensaje):
        with lock:
            log_fn(mensaje)
    return _emitir


def _descargar_tramos_serie(lat, lon, tramos, incluir_viento, carpeta, log_fn=None):
    """
    Descarga varios tramos; hasta `_MAX_TRAMOS_PARALELO` peticiones CDS a la vez.
    Cada petición usa su propio cliente cdsapi (thread-safe). Devuelve datasets
    en el mismo orden cronológico que `tramos`.
    """
    n = len(tramos)
    if n == 0:
        raise ValueError("No hay tramos para descargar.")
    if n == 1:
        t0, t1 = tramos[0]
        if log_fn:
            log_fn(f"Tramo 1/1: {t0} → {t1}")
        return [_obtener_tramo_serie(
            lat, lon, t0, t1, incluir_viento, carpeta, log_fn)]

    lock = threading.Lock()
    log_seguro = _log_con_rebloqueo(log_fn, lock)
    if log_fn:
        log_fn(f"Descargando hasta {_MAX_TRAMOS_PARALELO} tramos en paralelo…")

    partes = [None] * n

    def _tarea(idx, t0, t1):
        if log_seguro:
            log_seguro(f"Tramo {idx + 1}/{n}: {t0} → {t1}")
        return _obtener_tramo_serie(
            lat, lon, t0, t1, incluir_viento, carpeta, log_seguro)

    with ThreadPoolExecutor(max_workers=_MAX_TRAMOS_PARALELO) as pool:
        fut_a_idx = {
            pool.submit(_tarea, idx, t0, t1): idx
            for idx, (t0, t1) in enumerate(tramos)
        }
        for fut in as_completed(fut_a_idx):
            partes[fut_a_idx[fut]] = fut.result()
    return partes


def _concatenar_series(partes):
    """Une tramos temporales, ordena y elimina instantes duplicados."""
    if not partes:
        raise ValueError("No hay tramos para concatenar.")
    if len(partes) == 1:
        return partes[0]
    ds = xr.concat(partes, dim="time").sortby("time")
    t = ds["time"].values
    _, idx = np.unique(t, return_index=True)
    if len(idx) < t.size:
        ds = ds.isel(time=np.sort(idx))
    return ds


def _obtener_tramo_serie(lat, lon, inicio, fin, incluir_viento, carpeta, log_fn=None):
    """
    Descarga (o reutiliza caché de) un tramo corto; devuelve Dataset en memoria.
    Si el CDS rechaza el tamaño, subdivide el tramo y concatena.
    """
    chunk = _ruta_chunk(carpeta, inicio, fin)
    if _serie_cache_limpia(chunk):
        if log_fn:
            log_fn(f"  Tramo {inicio} → {fin}: caché local.")
        with xr.open_dataset(chunk) as raw:
            return raw.load()

    crudo = chunk.with_name(chunk.stem + "_cruda.nc")
    chunk.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            _retrieve_atomico(
                _DATASET_SERIE,
                _peticion_serie(lat, lon, inicio, fin, incluir_viento),
                crudo, log_fn=log_fn)
        except Exception as exc:
            if (_es_error_tamaño_cds(exc)
                    and _dias_rango(inicio, fin) > _MIN_DIAS_SUBDIVISION):
                mitad = max(_MIN_DIAS_SUBDIVISION, _dias_rango(inicio, fin) // 2)
                sub = _particiones_por_dias(inicio, fin, max_dias=mitad)
                if len(sub) > 1:
                    if log_fn:
                        log_fn(f"  CDS rechazó el tramo; subdividiendo en {len(sub)} partes…")
                    return _concatenar_series([
                        _obtener_tramo_serie(lat, lon, a, b, incluir_viento,
                                             carpeta, log_fn)
                        for a, b in sub
                    ])
            raise
        if log_fn:
            log_fn("  Procesando NetCDF del tramo…")
        ds = _parsear_serie_nc(crudo, lat, lon, inicio, fin)
        chunk.parent.mkdir(parents=True, exist_ok=True)
        _escribir_nc_atomico(ds, chunk)
        return ds
    finally:
        if crudo.exists():
            crudo.unlink()


def _rango_fechas(inicio, fin):
    """Listas de años/meses/días/horas (3-horario) que cubren [inicio, fin]."""
    inicio, fin = validar_rango_fechas(inicio, fin)
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
    "Dir": {"long_name": "Dirección media (náutica, procedencia)", "units": "deg"},
}


def _abrir_descarga_cds(ruta):
    """
    Abre una descarga del CDS y devuelve la lista de Datasets que contiene.

    El CDS nuevo entrega un ZIP con un .nc por 'stream' (olas, atmósfera); el
    antiguo, un .nc plano. Devuelve uno o más Datasets ya cargados en memoria,
    sin dejar handles abiertos ni temporales en disco.
    """
    ruta = Path(ruta)
    if zipfile.is_zipfile(ruta):
        tmp = Path(tempfile.mkdtemp())
        try:
            datasets = []
            with zipfile.ZipFile(ruta) as z:
                for nombre in z.namelist():
                    if not nombre.endswith(".nc"):
                        continue
                    destino_m = (tmp / nombre).resolve()
                    tmp_res = tmp.resolve()
                    if not destino_m.is_relative_to(tmp_res):
                        raise ValueError(f"Entrada ZIP sospechosa: {nombre!r}")
                    z.extract(nombre, tmp)
                    with xr.open_dataset(destino_m) as ds:
                        datasets.append(ds.load())
            if not datasets:
                raise ValueError("El ZIP del CDS no contiene ningún .nc.")
            return datasets
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    with xr.open_dataset(ruta) as ds:
        return [ds.load()]


_COORDS_EXTRA = ["latitude", "longitude", "number", "expver"]


def validar_coord_era5(lat, lon):
    """Comprueba lat/lon antes de pedir al CDS. Devuelve (lat, lon) como float."""
    lat = float(lat)
    lon = float(lon)
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitud fuera de rango: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitud fuera de rango: {lon}")
    return lat, lon


def _longitud_para_grilla(lon, longitudes):
    """Alinea la longitud del usuario con la convención del grid ERA5 (0–360 o −180–180)."""
    lon = float(lon)
    lons = np.asarray(longitudes, float)
    if lons.size == 0:
        return lon
    if float(lons.min()) >= 0 and lon < 0:
        return lon % 360.0
    if float(lons.max()) <= 180 and lon >= 180:
        return lon - 360.0
    return lon


def _parsear_serie_nc(ruta, lat, lon, inicio=None, fin=None):
    """
    Abre la descarga de ERA5 (un .nc plano o un .zip con un .nc por 'stream') y
    devuelve un Dataset(time) con Hs/Tp/Dir (+ viento) en el punto más cercano.

    El CDS nuevo separa olas y atmósfera en .nc distintos —con grillas distintas—,
    así que se selecciona el punto en cada uno antes de unirlos. La coordenada
    temporal moderna es 'valid_time'; se renombra a 'time' para el resto del pipeline.
    """
    lat, lon = validar_coord_era5(lat, lon)
    partes = []
    for parte in _abrir_descarga_cds(ruta):
        lon_sel = _longitud_para_grilla(lon, parte["longitude"].values)
        punto = parte.sel(latitude=lat, longitude=lon_sel, method="nearest")
        partes.append(punto.drop_vars(_COORDS_EXTRA, errors="ignore"))
    bruto = xr.merge(partes, compat="override")
    if "valid_time" in bruto.variables:
        bruto = bruto.rename({"valid_time": "time"})

    presentes = {k: v for k, v in _RENOMBRE_SERIE.items() if k in bruto.data_vars}
    if "swh" not in presentes:
        raise ValueError("La descarga ERA5 no incluye altura de ola (swh).")
    faltan = {"pp1d", "mwd"} - set(presentes)
    if faltan:
        raise ValueError(
            f"La descarga ERA5 está incompleta (faltan: {', '.join(sorted(faltan))}).")
    ds = bruto[list(presentes)].rename(presentes)
    # ECMWF mwd = dirección de propagación; pipeline/SWAN usan procedencia náutica.
    if "Dir" in ds.data_vars:
        ds["Dir"] = (ds["Dir"] + 180.0) % 360.0
    for v, attrs in _ATRIBUTOS.items():
        if v in ds.data_vars:
            ds[v].attrs.update(attrs)
    ds.attrs["fuente"] = f"ERA5 ({lat:.3f}, {lon:.3f})"
    if inicio is not None and fin is not None:
        s0, s1 = validar_rango_fechas(inicio, fin)
        ds.attrs["periodo"] = f"{s0} — {s1}"
    return ds


def _nombre_fuente(lat, lon, sufijo, inicio=None, fin=None):
    """
    Identificador de carpeta bajo salidas/.

    Si se indican fechas, el nombre incluye el rango para no mezclar descargas
    distintas del mismo punto.
    """
    stem = f"ERA5_{lat:+.4f}_{lon:+.4f}".replace(".", "p")
    if inicio is not None and fin is not None:
        s0, s1 = validar_rango_fechas(inicio, fin)
        d0 = str(np.datetime64(s0))[:10].replace("-", "")
        d1 = str(np.datetime64(s1))[:10].replace("-", "")
        stem += f"_{d0}_{d1}"
    return f"{stem}_{sufijo}"


def ruta_cache_serie(lat, lon, inicio, fin):
    """Carpeta y .nc parseado de la serie ERA5 para un punto y rango."""
    carpeta = rutas.carpeta_salida(_nombre_fuente(lat, lon, "serie", inicio, fin))
    return carpeta, carpeta / "era5_serie.nc"


def _cache_utilizable(ruta):
    """
    True si el .nc cacheado existe, no está vacío y se puede abrir. Una descarga
    interrumpida puede dejar un .nc de 0 bytes o truncado; confiar en él daría un
    error críptico aguas abajo (o datos a medias), así que se re-descarga.
    """
    try:
        if not ruta.exists() or ruta.stat().st_size == 0:
            return False
        _abrir_descarga_cds(ruta)          # abre el .nc plano o el .zip del CDS nuevo
        return True
    except Exception:
        return False


def _retrieve_atomico(dataset, peticion, destino, log_fn=None):
    """
    Descarga a un archivo temporal y lo renombra al terminar. Así una descarga
    interrumpida nunca deja en su sitio un .nc a medio escribir que luego parezca
    una cache válida.
    """
    tmp = destino.with_name(destino.name + ".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    pulso_stop = threading.Event()

    def _latido_cds():
        while not pulso_stop.wait(300):
            log_fn("  Aún en cola del CDS…")

    try:
        if log_fn:
            log_fn("En cola del CDS; esperando respuesta del servidor…")
            threading.Thread(target=_latido_cds, daemon=True).start()
        _cliente().retrieve(dataset, peticion, str(tmp))
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise RuntimeError(
                "El CDS no entregó datos (archivo vacío). "
                "Revisa credenciales y términos del dataset ERA5.")
        tmp.replace(destino)
        if log_fn:
            log_fn(f"Descarga recibida ({destino.stat().st_size // 1024} KiB).")
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    finally:
        pulso_stop.set()


def _serie_cache_limpia(ruta):
    """
    True si el .nc cacheado ya es la serie PARSEADA del pipeline (abrible y con
    'Hs'). El CDS entrega una descarga cruda (zip/multi-stream) que el resto del
    pipeline (io_oleaje.cargar) no sabe leer; por eso se cachea la serie ya limpia.
    """
    try:
        if not ruta.exists() or ruta.stat().st_size == 0:
            return False
        with xr.open_dataset(ruta) as ds:
            return "Hs" in ds.data_vars
    except Exception:
        return False


def _escribir_nc_atomico(ds, destino):
    """Escribe `ds` a `destino` vía un .part + replace (nunca deja un .nc a medias)."""
    tmp = destino.with_name(destino.name + ".part")
    ds.to_netcdf(tmp)
    tmp.replace(destino)


def descargar_serie(lat, lon, inicio, fin, incluir_viento=False, log_fn=None):
    """
    Descarga la serie ERA5 de Hs/Tp/Dir (opcional viento) para un punto y rango,
    la cachea ya PARSEADA como .nc limpio en salidas/ (Hs/Tp/Dir/time en un punto)
    y devuelve ese Dataset, listo para io_oleaje.cargar y el tablero de curvas.

    Rangos largos se parten en tramos mensuales (límite del CDS), se descargan
    de a dos en paralelo como máximo y se concatenan.
    """
    lat, lon = validar_coord_era5(lat, lon)
    carpeta, destino = ruta_cache_serie(lat, lon, inicio, fin)
    if _serie_cache_limpia(destino):
        if log_fn:
            log_fn(f"Usando caché: {destino}")
        return xr.open_dataset(destino)

    # Caché antigua: un único .nc crudo del CDS en la ruta final (pre-tramos).
    if destino.exists() and not (carpeta / "chunks").is_dir():
        try:
            if log_fn:
                log_fn("Parseando descarga cruda en caché…")
            ds = _parsear_serie_nc(destino, lat, lon, inicio, fin)
            if "Hs" in ds.data_vars:
                _escribir_nc_atomico(ds, destino)
                if log_fn:
                    log_fn("Caché convertida a serie limpia.")
                return ds
        except Exception:
            pass

    tramos = _particiones_descarga(inicio, fin)
    nd = _dias_rango(inicio, fin)
    if len(tramos) > 1 and log_fn:
        log_fn(f"Periodo de {nd} días → {len(tramos)} peticiones al CDS "
               f"(máx. {_MAX_DIAS_UNA_PETICION} días por petición).")

    partes = _descargar_tramos_serie(
        lat, lon, tramos, incluir_viento, carpeta, log_fn)

    ds = _concatenar_series(partes)
    _escribir_nc_atomico(ds, destino)
    if log_fn:
        log_fn(f"Serie completa: {int(ds.sizes.get('time', 0))} pasos → {destino.name}.")
    return ds


_VARS_ESPECTRO = ["2d_wave_spectra"]    # parámetro d2fd del CDS


def ruta_cache_espectro(lat, lon, inicio, fin):
    """
    Carpeta ERA5 de la serie y ruta del espectro parseado (misma carpeta).

    El espectro se guarda junto a era5_serie.nc para que _cargar_para_analisis
    lo encuentre sin duplicar carpetas _serie / _espectro.
    """
    carpeta, _ = ruta_cache_serie(lat, lon, inicio, fin)
    return carpeta, carpeta / "era5_espectro.nc"


def _espectro_cache_limpia(ruta):
    """
    True si el .nc ya es Efth(time, freq, dir) en un punto (sin lat/lon).
    """
    try:
        if not ruta.exists() or ruta.stat().st_size == 0:
            return False
        with xr.open_dataset(ruta) as ds:
            if "Efth" not in ds.data_vars:
                return False
            dims = set(ds["Efth"].dims)
            espurias = dims & {"latitude", "longitude", "lat", "lon"}
            return not espurias and {"freq", "dir"} <= dims
    except Exception:
        return False


def _peticion_espectro(lat, lon, inicio, fin, delta=0.25):
    """Petición CDS para espectro 2D direccional en un recuadro alrededor del punto."""
    anios, meses, dias, horas = _rango_fechas(inicio, fin)
    return {
        "product_type": "reanalysis",
        "variable": _VARS_ESPECTRO,
        "year": anios, "month": meses, "day": dias, "time": horas,
        "area": [lat + delta, lon - delta, lat - delta, lon + delta],
        "format": "netcdf",
    }


def _ruta_chunk_espectro(carpeta, inicio, fin):
    s0, s1 = validar_rango_fechas(inicio, fin)
    d0 = str(np.datetime64(s0))[:10].replace("-", "")
    d1 = str(np.datetime64(s1))[:10].replace("-", "")
    return carpeta / "chunks_espectro" / f"tramo_{d0}_{d1}.nc"


def _parsear_espectro_nc(ruta, lat=None, lon=None, inicio=None, fin=None):
    """
    .nc de ERA5 2D spectra → Dataset con Efth(time, freq, dir), des-logueado.

    ERA5 guarda d2fd como log10 de la densidad; aquí se reconstruye 10**d2fd y se
    renombran las dimensiones a (freq, dir) para igualar a leer_espectro_temporal.
    Si el archivo trae lat/lon (descarga en área), selecciona el punto más cercano.
    Maneja tanto el .nc plano (CDS antiguo) como el .zip por stream (CDS nuevo).
    """
    datasets = _abrir_descarga_cds(ruta)
    bruto = next((d for d in datasets if "d2fd" in d.data_vars), None)
    if bruto is None:
        raise ValueError("La descarga ERA5 no incluye espectro 2D (d2fd).")
    if lat is not None and lon is not None:
        lat, lon = validar_coord_era5(lat, lon)
        if "latitude" in bruto.dims and "longitude" in bruto.dims:
            lon_sel = _longitud_para_grilla(lon, bruto["longitude"].values)
            bruto = bruto.sel(latitude=lat, longitude=lon_sel, method="nearest")
        bruto = bruto.drop_vars(_COORDS_EXTRA, errors="ignore")
    if "valid_time" in bruto.variables:
        bruto = bruto.rename({"valid_time": "time"})
    d2fd = bruto["d2fd"]
    efth = np.power(10.0, np.asarray(d2fd, float))    # des-logueo; NaN se propaga
    efth = xr.DataArray(
        efth,
        dims=d2fd.dims,
        coords={k: d2fd.coords[k] for k in d2fd.dims},
    )
    renombres = {}
    if "frequency" in efth.dims:
        renombres["frequency"] = "freq"
    if "direction" in efth.dims:
        renombres["direction"] = "dir"
    if renombres:
        efth = efth.rename(renombres)

    ds = xr.Dataset({"Efth": efth})
    ds["Efth"].attrs = {"long_name": "Densidad de energía", "units": "m2/Hz/deg"}
    if "freq" in ds.coords:
        ds["freq"].attrs = {"long_name": "Frecuencia", "units": "Hz"}
    if "dir" in ds.coords:
        ds["dir"].attrs = {"long_name": "Dirección", "units": "deg"}
    if lat is not None and lon is not None:
        ds.attrs["fuente"] = f"ERA5 espectro ({lat:.3f}, {lon:.3f})"
        if inicio is not None and fin is not None:
            s0, s1 = validar_rango_fechas(inicio, fin)
            ds.attrs["periodo"] = f"{s0} — {s1}"
    return ds


def _obtener_tramo_espectro(lat, lon, inicio, fin, carpeta, log_fn=None):
    """Descarga o reutiliza un tramo corto de espectro ERA5 parseado en un punto."""
    chunk = _ruta_chunk_espectro(carpeta, inicio, fin)
    if _espectro_cache_limpia(chunk):
        if log_fn:
            log_fn(f"  Tramo espectro {inicio} → {fin}: caché local.")
        with xr.open_dataset(chunk) as raw:
            return raw.load()

    crudo = chunk.with_name(chunk.stem + "_cruda.nc")
    chunk.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            _retrieve_atomico(
                _DATASET_ESPECTRO,
                _peticion_espectro(lat, lon, inicio, fin),
                crudo, log_fn=log_fn)
        except Exception as exc:
            if (_es_error_tamaño_cds(exc)
                    and _dias_rango(inicio, fin) > _MIN_DIAS_SUBDIVISION):
                mitad = max(_MIN_DIAS_SUBDIVISION, _dias_rango(inicio, fin) // 2)
                sub = _particiones_por_dias(inicio, fin, max_dias=mitad)
                if len(sub) > 1:
                    if log_fn:
                        log_fn(f"  CDS rechazó el tramo de espectro; "
                               f"subdividiendo en {len(sub)} partes…")
                    return _concatenar_series([
                        _obtener_tramo_espectro(lat, lon, a, b, carpeta, log_fn)
                        for a, b in sub
                    ])
            raise
        if log_fn:
            log_fn("  Procesando espectro del tramo…")
        ds = _parsear_espectro_nc(crudo, lat, lon, inicio, fin)
        _escribir_nc_atomico(ds, chunk)
        return ds
    finally:
        if crudo.exists():
            crudo.unlink()


def _descargar_tramos_espectro(lat, lon, tramos, carpeta, log_fn=None):
    """Descarga tramos de espectro ERA5 (hasta 2 en paralelo)."""
    n = len(tramos)
    if n == 0:
        raise ValueError("No hay tramos de espectro para descargar.")
    if n == 1:
        t0, t1 = tramos[0]
        if log_fn:
            log_fn(f"Tramo espectro 1/1: {t0} → {t1}")
        return [_obtener_tramo_espectro(lat, lon, t0, t1, carpeta, log_fn)]

    lock = threading.Lock()
    log_seguro = _log_con_rebloqueo(log_fn, lock)
    if log_fn:
        log_fn(f"Descargando hasta {_MAX_TRAMOS_PARALELO} tramos de espectro en paralelo…")

    partes = [None] * n

    def _tarea(idx, t0, t1):
        if log_seguro:
            log_seguro(f"Tramo espectro {idx + 1}/{n}: {t0} → {t1}")
        return _obtener_tramo_espectro(lat, lon, t0, t1, carpeta, log_seguro)

    with ThreadPoolExecutor(max_workers=_MAX_TRAMOS_PARALELO) as pool:
        fut_a_idx = {
            pool.submit(_tarea, idx, t0, t1): idx
            for idx, (t0, t1) in enumerate(tramos)
        }
        for fut in as_completed(fut_a_idx):
            partes[fut_a_idx[fut]] = fut.result()
    return partes


def descargar_espectro(lat, lon, inicio, fin, log_fn=None):
    """
    Descarga el espectro 2D direccional ERA5 para un punto y rango, lo cachea ya
    parseado como era5_espectro.nc (Efth time×freq×dir) junto a la serie ERA5 y
    devuelve ese Dataset listo para partición y tablero.
    """
    lat, lon = validar_coord_era5(lat, lon)
    carpeta, destino = ruta_cache_espectro(lat, lon, inicio, fin)
    if _espectro_cache_limpia(destino):
        if log_fn:
            log_fn(f"Usando caché de espectro: {destino}")
        return xr.open_dataset(destino)

    # Caché antigua: .nc crudo del CDS sin parsear en la ruta final.
    if destino.exists() and not (carpeta / "chunks_espectro").is_dir():
        try:
            if log_fn:
                log_fn("Parseando espectro crudo en caché…")
            ds = _parsear_espectro_nc(destino, lat, lon, inicio, fin)
            if "Efth" in ds.data_vars and "latitude" not in ds["Efth"].dims:
                _escribir_nc_atomico(ds, destino)
                if log_fn:
                    log_fn("Caché de espectro convertida a formato limpio.")
                return ds
        except Exception:
            pass

    tramos = _particiones_descarga(inicio, fin)
    nd = _dias_rango(inicio, fin)
    if len(tramos) > 1 and log_fn:
        log_fn(f"Espectro: periodo de {nd} días → {len(tramos)} peticiones al CDS "
               f"(máx. {_MAX_DIAS_UNA_PETICION} días por petición).")

    partes = _descargar_tramos_espectro(lat, lon, tramos, carpeta, log_fn)
    ds = _concatenar_series(partes)
    _escribir_nc_atomico(ds, destino)
    if log_fn:
        log_fn(f"Espectro completo: {int(ds.sizes.get('time', 0))} pasos → {destino.name}.")
    return ds
