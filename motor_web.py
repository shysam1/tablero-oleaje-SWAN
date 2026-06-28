"""
Lógica de negocio de la GUI web (sin tkinter).

Funciones puras / IO reutilizadas por api_web.py. Extraídas de pasos_* y
app_tablero para no duplicar el motor existente.
"""

import io
import traceback
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

import borde_oleaje
import config
import geo_malla
import io_batimetria
import io_era5
import io_oleaje
import io_swan
import io_swan_nonst
import previews
import productos
import rutas
import seguridad
import sistema
import swan_builder
import swan_runner
import tablero_oleaje
import tablero_swan
import validacion
import video_swan

_VERSION_APP = "2026.06.27"
_MAX_RECIENTES = 12
_RESOLUCION_ETOPO_KM = 1.85
# Nombres únicos al copiar batimetrías al caso anidado (evita sobrescritura).
_BOT_GRANDE = "bati_grande.bot"
_BOT_NIDO = "bati_nido.bot"

PLANTILLAS_MALLA = {
    "coronel": {
        "nombre": "Bahía de Coronel",
        "lat": "-36.97", "lon": "-73.15", "ancho": "48", "alto": "59", "celda": "1000",
        "nido": {"lat": "-36.97", "lon": "-73.15", "ancho": "9", "alto": "10", "celda": "200"},
    },
    "renaca": {
        "nombre": "Reñaca / Viña",
        "lat": "-32.97", "lon": "-71.55", "ancho": "8", "alto": "8", "celda": "100",
    },
    "talcahuano": {
        "nombre": "Golfo de Arauco (grueso)",
        "lat": "-36.5", "lon": "-73.2", "ancho": "80", "alto": "60", "celda": "2000",
    },
}


def _celda_malla(malla):
    mxc, myc = int(malla["mxc"]), int(malla["myc"])
    return max(float(malla["xlenc"]) / mxc, float(malla["ylenc"]) / myc)


def evaluar_resolucion_malla(malla):
    """Avisos si la celda es más fina que ETOPO (~1,8 km)."""
    celda = _celda_malla(malla)
    avisos = []
    if celda < 500:
        avisos.append(
            f"La celda (~{celda:.0f} m) es mucho más fina que ETOPO (~{_RESOLUCION_ETOPO_KM * 1000:.0f} m). "
            "El .bot automático será suave; usa raster local o .bot propio para bahías finas.")
    elif celda < 1500:
        avisos.append(
            f"La celda (~{celda:.0f} m) es más fina que ETOPO (~{_RESOLUCION_ETOPO_KM * 1000:.0f} m). "
            "Revisa la preview de batimetría antes de correr.")
    return {"celda_m": round(celda), "avisos": avisos, "fuente_etopo_km": _RESOLUCION_ETOPO_KM}


def _semáforo_batimetria(meta):
    pct = float(meta.get("pct_tierra", 0))
    if pct > 20:
        return "err", f"{pct:.0f}% de nodos en tierra: el dominio parece demasiado hacia costa/tierra."
    if pct > 5:
        return "warn", f"{pct:.0f}% en tierra: revisa que el rectángulo cubra sobre todo mar."
    return "ok", "Batimetría coherente para SWAN."


def _enriquecer_meta_bati(meta, malla, fuente):
    celda = _celda_malla(malla)
    meta = dict(meta)
    meta["fuente"] = fuente
    meta["celda_m"] = round(celda)
    meta["resolucion_fuente_km"] = _RESOLUCION_ETOPO_KM if fuente == "ETOPO180" else None
    estado, msg = _semáforo_batimetria(meta)
    meta["estado"] = estado
    meta["mensaje"] = msg
    meta["advertencias"] = evaluar_resolucion_malla(malla)["avisos"]
    if fuente == "ETOPO180" and celda < 500:
        meta["advertencias"] = list(meta["advertencias"]) + [
            "Para celdas < 500 m conviene un .bot de batimetría fina (SHOA, GEBCO local)."]
    return meta


def _abrir(ruta):
    try:
        sistema.abrir_archivo(ruta)
    except Exception:
        pass


def _validar_era5(lat, lon, inicio, fin):
    lat, lon = io_era5.validar_coord_era5(lat, lon)
    io_era5.validar_rango_fechas(inicio, fin)
    return lat, lon


def _ruta_usuario(ruta, etiqueta="ruta", debe_existir=False):
    """Ruta absoluta confinada al home del usuario o salidas/."""
    return seguridad.confina_usuario(ruta, etiqueta=etiqueta, debe_existir=debe_existir)


def _copiar_bot_si_hace_falta(destino, ruta_bot, alias=None):
    """Copia un .bot al caso solo al escribir/correr, no durante validación."""
    destino = _ruta_usuario(destino, "Carpeta del caso")
    ruta_bot = _ruta_usuario(ruta_bot, "Batimetría", debe_existir=True)
    nombre_dest = alias or ruta_bot.name
    dest = destino / nombre_dest
    if ruta_bot.resolve() != dest.resolve():
        dest.write_bytes(ruta_bot.read_bytes())
    return nombre_dest


def _nombre_bot_en_caso(anidado, es_nido=False):
    """Nombre del .bot dentro de la carpeta del caso (alias si hay anidado)."""
    if anidado:
        return _BOT_NIDO if es_nido else _BOT_GRANDE
    return None


def _estado_validacion(r):
    if not r["aplicable"]:
        return "na"
    if r["n_falla"] == 0:
        return "ok"
    return "warn"


def revision_datos(ruta):
    """Carga, valida y evalúa productos. Devuelve dict serializable."""
    lineas = []
    vacio = {
        "ok": False, "reporte": "", "motivo": "",
        "variables": [], "n_pasos": 0,
        "validacion": [], "productos": [], "comparacion": None,
    }
    if not ruta or not str(ruta).strip():
        vacio.update({"reporte": "No se indicó archivo.",
                      "motivo": "Selecciona un archivo de datos."})
        return vacio
    p = None
    try:
        p = _ruta_usuario(ruta, "Archivo", debe_existir=True)
    except ValueError as e:
        vacio.update({"reporte": str(e),
                      "motivo": "Ruta no permitida o inexistente."})
        return vacio
    ds = None
    try:
        ds = _cargar_para_analisis(p)
        variables = list(ds.data_vars)
        n = int(ds.sizes.get("time", 0))
        lineas.append(f"Variables presentes: {', '.join(variables) or '(ninguna)'}")
        lineas.append(f"Pasos de tiempo: {n}\n")
        lineas.append("Validación física:")
        val_items = []
        for r in validacion.validar(ds):
            est = _estado_validacion(r)
            val_items.append({
                "nombre": r["nombre"], "estado": est,
                "detalle": r.get("detalle", ""),
                "n_falla": r.get("n_falla", 0),
                "n_total": r.get("n_total", 0),
            })
            if not r["aplicable"]:
                lineas.append(f"  [n/a] {r['nombre']}: {r['detalle']}")
            elif r["n_falla"] == 0:
                lineas.append(f"  [ok ] {r['nombre']}")
            else:
                lineas.append(
                    f"  [!! ] {r['nombre']}: {r['n_falla']}/{r['n_total']}")
        lineas.append("\nProductos que se podrán generar:")
        hay_producto = False
        prod_items = []
        for it in productos.evaluar(ds):
            motivo = it.get("motivo") or (
                f"faltan: {', '.join(it['faltan'])}" if it.get("faltan") else "")
            prod_items.append({
                "nombre": it["nombre"],
                "disponible": it["disponible"],
                "faltan": it.get("faltan") or [],
                "motivo": motivo,
            })
            if it["disponible"]:
                hay_producto = True
                lineas.append(f"  ✓ {it['nombre']}")
            else:
                lineas.append(f"  ✗ {it['nombre']} ({motivo})")
        return {
            "ok": hay_producto,
            "reporte": "\n".join(lineas),
            "motivo": ("" if hay_producto else
                       "Los datos no permiten generar ningún producto."),
            "variables": variables,
            "n_pasos": n,
            "validacion": val_items,
            "productos": prod_items,
            "comparacion": None,
        }
    except Exception as e:
        lineas.append(f"Error al analizar el archivo:\n{e}")
        return {
            "ok": False,
            "reporte": "\n".join(lineas),
            "motivo": "No se pudieron cargar los datos.",
            "variables": [], "n_pasos": 0,
            "validacion": [], "productos": [], "comparacion": None,
        }
    finally:
        if ds is not None:
            ds.close()


def calcular_malla(lat, lon, ancho, alto, celda):
    m = geo_malla.malla_desde_latlon(
        float(lat), float(lon), float(ancho), float(alto), float(celda))
    resumen = (f"Zona UTM {m['zona_utm']} · {m['mxc']}×{m['myc']} celdas · "
               f"origen UTM ({m['xpc']:.0f}, {m['ypc']:.0f}).")
    ev = evaluar_resolucion_malla(m)
    return {"malla": m, "resumen": resumen, "avisos_resolucion": ev["avisos"],
            "celda_m": ev["celda_m"]}


def listar_plantillas_malla():
    out = []
    for k, v in PLANTILLAS_MALLA.items():
        item = {"id": k, "nombre": v["nombre"],
                "lat": v["lat"], "lon": v["lon"],
                "ancho": v["ancho"], "alto": v["alto"], "celda": v["celda"]}
        if "nido" in v:
            item["nido"] = v["nido"]
        out.append(item)
    return out


def descargar_era5(lat, lon, inicio, fin, con_viento=True, con_espectro=False,
                   log_fn=None):
    lat, lon = _validar_era5(lat, lon, inicio, fin)

    def _log(msg):
        if log_fn:
            log_fn(msg)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        _log(f"Coordenada ({lat:.3f}, {lon:.3f}), rango {inicio} → {fin}.")
        _, nc = io_era5.ruta_cache_serie(lat, lon, inicio, fin)
        if io_era5._serie_cache_limpia(nc):
            _log("Serie ya en caché local; no se pide al CDS.")
        else:
            _log("Solicitando al Copernicus CDS (cola del servidor; "
                 "puede tardar varios minutos)…")
        ds = io_era5.descargar_serie(lat, lon, inicio, fin,
                                     incluir_viento=con_viento, log_fn=_log)
        log = [f"Serie ERA5 descargada: {ds.sizes.get('time', 0)} pasos."]
        ds.close()
        if con_espectro:
            _log("Descargando espectro 2D ERA5…")
            esp = None
            try:
                esp = io_era5.descargar_espectro(lat, lon, inicio, fin, log_fn=_log)
                esp_dest = nc.parent / "era5_espectro.nc"
                io_era5._escribir_nc_atomico(esp, esp_dest)
                log.append(f"Espectro ERA5: {esp.sizes.get('time', 0)} pasos → {esp_dest.name}.")
            finally:
                if esp is not None:
                    esp.close()
    return {"ruta": str(nc), "log": buffer.getvalue() + "\n".join(log)}


def _cargar_para_analisis(ruta):
    """Carga serie de oleaje y adjunta Efth si hay era5_espectro.nc en la misma carpeta."""
    ds = io_oleaje.cargar(ruta)
    esp_path = Path(ruta).parent / "era5_espectro.nc"
    if "Efth" not in ds and esp_path.is_file():
        import xarray as xr
        dse = xr.open_dataset(esp_path)
        try:
            if "Efth" in dse:
                ds = ds.merge(dse[["Efth"]], compat="override")
        finally:
            dse.close()
    return ds


def generar_batimetria(malla, zona_utm, destino, nombre=None, raster_ruta=None):
    malla_io = {k: v for k, v in malla.items() if k != "zona_utm"}
    dest = _ruta_usuario(destino, "Carpeta destino")
    raster = None
    fuente = "ETOPO180"
    if raster_ruta:
        rp = _ruta_usuario(raster_ruta, "Raster de batimetría", debe_existir=True)
        raster = io_batimetria.leer_raster_local(rp)
        fuente = rp.name
    ruta, meta = io_batimetria.generar_bot(
        malla_io, zona_utm, dest, raster=raster, nombre=nombre or "bati.bot")
    meta = _enriquecer_meta_bati(meta, malla_io, fuente)
    log = (f"{ruta.name} — {meta['fuente']}: prof. {meta['prof_min']:.1f}–"
           f"{meta['prof_max']:.1f} m, {meta['pct_tierra']:.0f}% tierra, "
           f"{meta['n_nodos']} nodos. {meta['mensaje']}")
    return {"ruta": str(ruta), "log": log, "meta": meta}


def derivar_borde(ruta_serie, modo, tr):
    p = _ruta_usuario(ruta_serie, "Archivo de serie", debe_existir=True)
    ds = io_oleaje.cargar(p)
    try:
        borde = borde_oleaje.condicion_borde(ds, modo, int(tr))
    finally:
        ds.close()
    return {
        "hs": borde.get("hs"),
        "per": borde.get("per"),
        "dir": borde.get("dir"),
        "dd": borde.get("dd", 20.0),
        "descripcion": borde.get("descripcion", ""),
        "ruta_serie": str(p),
    }


def estado_cache_era5_borde(lat, lon, inicio, fin):
    """Indica si ya hay era5_serie.nc parseado para el punto y rango."""
    lat, lon = _validar_era5(lat, lon, inicio, fin)
    _, nc = io_era5.ruta_cache_serie(lat, lon, inicio, fin)
    return {"ruta": str(nc), "en_cache": io_era5._serie_cache_limpia(nc)}


def derivar_borde_era5(lat, lon, inicio, fin, modo, tr):
    """
    Deriva Hs/Tp/Dir de borde desde la caché ERA5 del punto.
    Lanza ValueError si no hay serie descargada (usar descargar_era5 antes).
    """
    st = estado_cache_era5_borde(lat, lon, inicio, fin)
    if not st["en_cache"]:
        raise ValueError(
            "No hay serie ERA5 en caché para ese punto y rango de fechas.")
    return derivar_borde(st["ruta"], modo, int(tr))


def info_carpeta_swan(carpeta):
    p = _ruta_usuario(carpeta, "Carpeta SWAN", debe_existir=True)
    if not p.is_dir():
        raise ValueError(f"No es una carpeta válida: {carpeta}")
    casos = swan_runner.casos_ordenados(str(p))
    nonst = io_swan_nonst.es_corrida_nonst(p)
    tipo = ("no estacionaria → video" if nonst
            else "estacionaria → tablero de mapas")
    utm = io_swan.inferir_utm_desde_carpeta(p)
    return {
        "casos": casos,
        "nonst": nonst,
        "resumen": f"Carpeta: {p.name}\nDetectada como {tipo}.",
        **utm,
    }


def validar_nido(malla_grande, malla_nido):
    errores, avisos = swan_builder.validar_caso_anidado(malla_grande, malla_nido)
    return {"errores": errores, "avisos": avisos, "ok": not errores}


def checklist_correr_swan(ctx):
    """Lista de requisitos previos a correr SWAN (para la UI)."""
    items = []
    dominios = ctx.get("dominios") or []
    g = dominios[0] if dominios else {}
    carpeta = ctx.get("carpeta_caso")
    items.append({"id": "carpeta", "label": "Carpeta del caso",
                  "ok": bool(carpeta), "detalle": carpeta or "Sin definir"})
    items.append({"id": "malla", "label": "Malla del dominio grande",
                  "ok": bool(g.get("malla")), "detalle": g.get("malla_ui", {}).get("resumen", "")})
    items.append({"id": "bot", "label": "Batimetría (.bot) grande",
                  "ok": bool(g.get("bot")), "detalle": Path(g["bot"]).name if g.get("bot") else ""})
    bordes = g.get("bordes") or []
    items.append({"id": "borde", "label": "Condición de borde",
                  "ok": len(bordes) > 0,
                  "detalle": ", ".join(b["lado"] for b in bordes) if bordes else "Sin lados"})
    if ctx.get("nido_activo") and len(dominios) >= 2:
        n = dominios[1]
        items.append({"id": "nido_malla", "label": "Malla del nido",
                      "ok": bool(n.get("malla")), "detalle": n.get("malla_ui", {}).get("resumen", "")})
        items.append({"id": "nido_bot", "label": "Batimetría del nido",
                      "ok": bool(n.get("bot")), "detalle": Path(n["bot"]).name if n.get("bot") else ""})
    return items


def abrir_logs_swan(carpeta):
    """Abre la carpeta del caso (archivos .prt/.erf visibles en el explorador)."""
    p = _ruta_usuario(carpeta, "Carpeta SWAN", debe_existir=True)
    prt = list(p.glob("*.prt"))
    erf = list(p.glob("*.erf"))
    _abrir(p)
    return {"ok": True, "prt": [x.name for x in prt], "erf": [x.name for x in erf]}


def validar_correr_swan(ctx):
    """Valida contexto del wizard modelar (solo lectura, sin copiar archivos)."""
    dominios = ctx.get("dominios", [])
    destino = ctx.get("carpeta_caso")
    if not dominios or not destino:
        return {"errores": ["Completa malla, batimetría y borde."], "avisos": []}
    g = dominios[0]
    if any(k not in g for k in ("malla", "bot", "bordes")):
        return {"errores": ["Faltan malla, batimetría o borde del dominio grande."],
                "avisos": []}

    destino = _ruta_usuario(destino, "Carpeta del caso")
    bot_g = _ruta_usuario(g["bot"], "Batimetría", debe_existir=True)
    malla_g = {k: v for k, v in g["malla"].items() if k != "zona_utm"}
    bordes = g["bordes"]

    anidado = len(dominios) >= 2
    bot_g_nom = _nombre_bot_en_caso(anidado, es_nido=False) or bot_g.name
    errores, avisos = swan_builder.validar_caso(
        malla_g, {"archivo": bot_g_nom, "ruta": str(bot_g)}, bordes,
        carpeta=destino)

    if anidado:
        n = dominios[1]
        if any(k not in n for k in ("malla", "bot")):
            return {"errores": ["Faltan malla y batimetría del nido."], "avisos": avisos}
        bot_n = _ruta_usuario(n["bot"], "Batimetría del nido", debe_existir=True)
        malla_n = {k: v for k, v in n["malla"].items() if k != "zona_utm"}
        bot_n_nom = _nombre_bot_en_caso(anidado, es_nido=True)
        e_an, a_an = swan_builder.validar_caso_anidado(g["malla"], n["malla"])
        errores += e_an
        avisos += a_an
        e_n, a_n = swan_builder.validar_caso(
            malla_n, {"archivo": bot_n_nom, "ruta": str(bot_n)}, [], carpeta=destino,
            requiere_bordes=False)
        errores += e_n
        avisos += a_n

    return {"errores": errores, "avisos": avisos, "anidado": anidado}


def escribir_caso_swan(ctx, nombre):
    """Genera .swn (par anidado o simple). Devuelve log de escritura."""
    dominios = ctx["dominios"]
    destino = _ruta_usuario(ctx["carpeta_caso"], "Carpeta del caso")
    nombre = seguridad.sanitizar_nombre_caso(nombre or "MiCaso")
    g = dominios[0]
    malla_g = {k: v for k, v in g["malla"].items() if k != "zona_utm"}
    bordes = g["bordes"]
    logs = []
    anidado = len(dominios) >= 2
    alias_g = _nombre_bot_en_caso(anidado, es_nido=False)
    bot_g_name = _copiar_bot_si_hace_falta(destino, g["bot"], alias=alias_g)
    if anidado:
        n = dominios[1]
        bot_n_name = _copiar_bot_si_hace_falta(
            destino, n["bot"], alias=_nombre_bot_en_caso(anidado, es_nido=True))
        malla_n = {k: v for k, v in n["malla"].items() if k != "zona_utm"}
        ruta_g, ruta_n = swan_builder.escribir_par_anidado(
            destino, nombre, nombre + "_nido",
            malla_g, {"archivo": bot_g_name}, bordes,
            malla_n, {"archivo": bot_n_name},
            salidas=("Hs", "Tp", "Dir"),
            punto_espectral=n.get("punto_espectral"))
        logs.append(f"Par anidado generado: {ruta_g.name}, {ruta_n.name}")
    else:
        ruta_swn = swan_builder.escribir_caso(
            destino, nombre, nombre=nombre, malla=malla_g,
            batimetria={"archivo": bot_g_name}, bordes=bordes,
            salidas=("Hs", "Tp", "Dir"), estacionario=True)
        logs.append(f"Caso generado: {ruta_swn.name}")
    ui = g.get("malla_ui") or {}
    io_swan.guardar_meta_caso(
        destino, malla_g,
        zona_utm=g.get("zona_utm"),
        lat_centro=ui.get("lat"),
        lon_centro=ui.get("lon"),
    )
    return "\n".join(logs)


def correr_swan_carpeta(carpeta, log_fn=None, progreso_fn=None,
                        on_proc=None, cancelado=None):
    carpeta = _ruta_usuario(carpeta, "Carpeta SWAN", debe_existir=True)
    ok, _ = swan_runner.correr_swan(
        str(carpeta), log=log_fn, progreso=progreso_fn,
        on_proc=on_proc, cancelado=cancelado)
    return ok


def generar_tablero_oleaje(ruta, abrir=True):
    p = _ruta_usuario(ruta, "Archivo de oleaje", debe_existir=True)
    out = tablero_oleaje.generar_tablero(str(p), cargar_fn=_cargar_para_analisis)
    out = str(out)
    registrar_producto(out, "tablero_oleaje")
    if abrir:
        _abrir(out)
    return out


def comparar_series(ruta_a, ruta_b):
    """Compara Hs de dos series en el periodo común (p. ej. ERA5 vs boya)."""
    pa = _ruta_usuario(ruta_a, "Serie A", debe_existir=True)
    pb = _ruta_usuario(ruta_b, "Serie B", debe_existir=True)
    dsa = dsb = None
    try:
        dsa = io_oleaje.cargar(pa)
        dsb = io_oleaje.cargar(pb)
        if "Hs" not in dsa or "Hs" not in dsb:
            raise ValueError("Ambas series deben incluir la variable Hs.")
        import pandas as pd
        a = dsa[["Hs"]].to_dataframe().reset_index()
        b = dsb[["Hs"]].to_dataframe().reset_index()
        m = pd.merge(a, b, on="time", suffixes=("_a", "_b"))
        if m.empty:
            raise ValueError("No hay pasos temporales en común entre las dos series.")
        diff = m["Hs_a"] - m["Hs_b"]
        return {
            "n": int(len(m)),
            "bias": float(diff.mean()),
            "rmse": float((diff ** 2).mean() ** 0.5),
            "corr": float(m["Hs_a"].corr(m["Hs_b"])) if len(m) > 2 else None,
            "hs_a_media": float(m["Hs_a"].mean()),
            "hs_b_media": float(m["Hs_b"].mean()),
        }
    finally:
        if dsa is not None:
            dsa.close()
        if dsb is not None:
            dsb.close()


def generar_tablero_swan_mapas(carpeta, utm_large=None, abrir=True):
    _ruta_usuario(carpeta, "Carpeta SWAN", debe_existir=True)
    out = tablero_swan.generar_tablero_swan(carpeta, utm_large=utm_large)
    out = str(out)
    registrar_producto(out, "tablero_swan")
    if abrir:
        _abrir(out)
    return out


def generar_video_swan(carpeta, utm_large=None, progreso_fn=None, abrir=True):
    _ruta_usuario(carpeta, "Carpeta SWAN", debe_existir=True)
    videos = video_swan.generar_videos(
        carpeta, multipanel=True, utm_large=utm_large, progreso=progreso_fn)
    if not videos:
        raise RuntimeError("No se generó ningún video para esta carpeta.")
    out = str(videos[0])
    registrar_producto(out, "video_swan")
    if abrir:
        _abrir(out)
    return out


def despachar_avanzado(ruta, utm_large=None, progreso_fn=None):
    """Autodetecta entrada y genera producto (como VistaAvanzado._despachar)."""
    ruta = _ruta_usuario(ruta, "Entrada", debe_existir=True)
    carpeta = ruta.parent if ruta.suffix.lower() == ".swn" else ruta
    if ruta.is_dir() or ruta.suffix.lower() == ".swn":
        if io_swan_nonst.es_corrida_nonst(carpeta):
            return generar_video_swan(carpeta, utm_large=utm_large,
                                      progreso_fn=progreso_fn)
        return generar_tablero_swan_mapas(carpeta, utm_large=utm_large)
    return generar_tablero_oleaje(ruta)


def punto_espectral_desde_latlon(lat, lon, zona_utm):
    import pyproj
    este, norte = pyproj.Transformer.from_crs(
        "EPSG:4326", f"EPSG:{io_batimetria.epsg_utm(zona_utm)}",
        always_xy=True).transform(float(lon), float(lat))
    return {"x": round(este), "y": round(norte), "archivo": "Espectro_Punto.txt"}


def guardar_config_carpeta(clave, ruta):
    config.guardar(clave, str(ruta))


def obtener_config_carpeta(clave, default=""):
    return config.obtener(clave) or default


def guardar_preferencias(prefs):
    """Persiste preferencias de UI (coords ERA5, UTM, etc.)."""
    if not isinstance(prefs, dict):
        return
    actuales = config.obtener("preferencias_ui") or {}
    actuales.update(prefs)
    config.guardar("preferencias_ui", actuales)


def obtener_preferencias():
    return config.obtener("preferencias_ui") or {}


def registrar_producto(ruta, tipo):
    """Añade un producto generado al historial reciente."""
    try:
        p = Path(ruta)
        if not p.is_file():
            return
        p = p.resolve()
        recientes = config.obtener("productos_recientes") or []
        recientes = [x for x in recientes if x.get("ruta") != str(p)]
        recientes.insert(0, {
            "ruta": str(p),
            "tipo": tipo,
            "nombre": p.name,
            "carpeta": str(p.parent),
        })
        config.guardar("productos_recientes", recientes[:_MAX_RECIENTES])
    except Exception:
        pass


def listar_recientes():
    recientes = config.obtener("productos_recientes") or []
    out = []
    for item in recientes:
        p = Path(item.get("ruta", ""))
        if not p.is_file():
            continue
        thumb = previews.imagen_a_base64(p) if p.suffix.lower() == ".png" else None
        out.append({**item, "existe": True, "thumb": thumb})
    return out


def listar_cache_era5():
    """Lista descargas ERA5 bajo salidas/ con tamaño en disco."""
    raiz = rutas.RAIZ_SALIDAS
    if not raiz.is_dir():
        return []
    entradas = []
    for carpeta in sorted(raiz.glob("ERA5_*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not carpeta.is_dir():
            continue
        nc = carpeta / "era5_serie.nc"
        esp = carpeta / "era5_espectro.nc"
        total = sum(f.stat().st_size for f in carpeta.rglob("*") if f.is_file())
        entradas.append({
            "carpeta": str(carpeta),
            "nombre": carpeta.name,
            "tiene_serie": nc.is_file(),
            "tiene_espectro": esp.is_file(),
            "bytes": total,
            "mb": round(total / (1024 * 1024), 1),
        })
    return entradas


def eliminar_cache_era5(carpeta):
    import shutil
    p = _ruta_usuario(carpeta, "Caché ERA5", debe_existir=True)
    if not p.is_dir():
        raise ValueError("No es una carpeta válida.")
    if "ERA5_" not in p.name:
        raise ValueError("Solo se pueden borrar carpetas ERA5_* bajo salidas/.")
    if not p.resolve().is_relative_to(rutas.RAIZ_SALIDAS.resolve()):
        raise ValueError("La carpeta no está bajo salidas/.")
    shutil.rmtree(p)
    return {"ok": True}


def preview_malla(malla, lat_centro=None, lon_centro=None):
    return previews.preview_malla(malla, lat_centro, lon_centro)


def preview_malla_anidada(malla_grande, malla_nido):
    return previews.preview_malla_anidada(malla_grande, malla_nido)


def preview_batimetria(ruta_bot, malla):
    ruta_bot = _ruta_usuario(ruta_bot, "Batimetría", debe_existir=True)
    malla_io = {k: v for k, v in malla.items() if k != "zona_utm"}
    return previews.preview_batimetria(str(ruta_bot), malla_io)


def validar_bot_malla(ruta_bot, malla):
    """Comprueba que un .bot externo encaja con la malla; devuelve meta con semáforo."""
    ruta = _ruta_usuario(ruta_bot, "Batimetría", debe_existir=True)
    malla_io = {k: v for k, v in malla.items() if k != "zona_utm"}
    esperado, nx, ny, mxc, myc = io_batimetria.nodos_esperados_bot(malla_io)
    n = len(ruta.read_text().split())
    fuente = ruta.name
    base = {
        "n_nodos": n,
        "n_esperados": esperado,
        "nx": nx,
        "ny": ny,
        "mxc": mxc,
        "myc": myc,
        "fuente": fuente,
        "advertencias": [],
    }
    if n != esperado:
        meta = {
            **base,
            "estado": "err",
            "mensaje": (
                f"El .bot tiene {n} valores; esta malla ({mxc}×{myc} celdas) "
                f"requiere {esperado} ({ny}×{nx} nodos)."),
        }
        return {"ok": False, "meta": meta, "error": meta["mensaje"]}
    depth = io_batimetria.leer_bot_como_grilla(str(ruta), malla_io)
    meta = {
        **base,
        "prof_min": float(np.nanmin(depth)),
        "prof_max": float(np.nanmax(depth)),
        "pct_tierra": float(np.mean(depth <= 0) * 100.0),
    }
    meta = _enriquecer_meta_bati(meta, malla_io, fuente)
    return {"ok": meta["estado"] != "err", "meta": meta}


def preview_archivo(ruta):
    p = _ruta_usuario(ruta, "Archivo", debe_existir=True)
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif"):
        return None
    return previews.imagen_a_base64(p)


def info_aplicacion():
    import sys
    return {
        "version": _VERSION_APP,
        "python": sys.version.split()[0],
        "salidas": str(rutas.RAIZ_SALIDAS.resolve()),
        "repo": str(Path(__file__).resolve().parent),
    }


def guardar_sesion_wizard(wizard, step, ctx):
    config.guardar("wizard_sesion", {
        "wizard": wizard, "step": step, "ctx": ctx,
    })


def cargar_sesion_wizard():
    return config.obtener("wizard_sesion")


def limpiar_sesion_wizard():
    config.guardar("wizard_sesion", None)
