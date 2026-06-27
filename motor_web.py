"""
Lógica de negocio de la GUI web (sin tkinter).

Funciones puras / IO reutilizadas por api_web.py. Extraídas de pasos_* y
app_tablero para no duplicar el motor existente.
"""

import io
import os
import traceback
from contextlib import redirect_stdout
from pathlib import Path

import borde_oleaje
import config
import geo_malla
import io_batimetria
import io_era5
import io_oleaje
import io_swan_nonst
import productos
import rutas
import swan_builder
import swan_runner
import tablero_oleaje
import tablero_swan
import validacion
import video_swan


def _abrir(ruta):
    try:
        os.startfile(str(ruta))
    except Exception:
        pass


def revision_datos(ruta):
    """Carga, valida y evalúa productos. Devuelve dict serializable."""
    lineas = []
    try:
        ds = io_oleaje.cargar(ruta)
        variables = ", ".join(ds.data_vars) or "(ninguna)"
        n = int(ds.sizes.get("time", 0))
        lineas.append(f"Variables presentes: {variables}")
        lineas.append(f"Pasos de tiempo: {n}\n")
        lineas.append("Validación física:")
        for r in validacion.validar(ds):
            if not r["aplicable"]:
                lineas.append(f"  [n/a] {r['nombre']}: {r['detalle']}")
            elif r["n_falla"] == 0:
                lineas.append(f"  [ok ] {r['nombre']}")
            else:
                lineas.append(
                    f"  [!! ] {r['nombre']}: {r['n_falla']}/{r['n_total']}")
        lineas.append("\nProductos que se podrán generar:")
        hay_producto = False
        for it in productos.evaluar(ds):
            if it["disponible"]:
                hay_producto = True
                lineas.append(f"  ✓ {it['nombre']}")
            else:
                lineas.append(
                    f"  ✗ {it['nombre']} (faltan: {', '.join(it['faltan'])})")
        ds.close()
        return {
            "ok": hay_producto,
            "reporte": "\n".join(lineas),
            "motivo": ("" if hay_producto else
                       "Los datos no permiten generar ningún producto."),
        }
    except Exception as e:
        lineas.append(f"Error al analizar el archivo:\n{e}")
        return {
            "ok": False,
            "reporte": "\n".join(lineas),
            "motivo": "No se pudieron cargar los datos.",
        }


def calcular_malla(lat, lon, ancho, alto, celda):
    m = geo_malla.malla_desde_latlon(
        float(lat), float(lon), float(ancho), float(alto), float(celda))
    resumen = (f"Zona UTM {m['zona_utm']} · {m['mxc']}×{m['myc']} celdas · "
               f"origen UTM ({m['xpc']:.0f}, {m['ypc']:.0f}).")
    return {"malla": m, "resumen": resumen}


def descargar_era5(lat, lon, inicio, fin, con_viento=True, con_espectro=False):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        ds = io_era5.descargar_serie(float(lat), float(lon), inicio, fin,
                                     incluir_viento=con_viento)
        log = [f"Serie ERA5 descargada: {ds.sizes.get('time', 0)} pasos."]
        if con_espectro:
            esp = io_era5.descargar_espectro(float(lat), float(lon), inicio, fin)
            log.append(f"Espectro ERA5 descargado: {esp.sizes.get('time', 0)} pasos.")
    carpeta = rutas.carpeta_salida(
        io_era5._nombre_fuente(float(lat), float(lon), "serie"))
    nc = str(carpeta / "era5_serie.nc")
    return {"ruta": nc, "log": buffer.getvalue() + "\n".join(log)}


def generar_batimetria(malla, zona_utm, destino, nombre=None):
    malla_io = {k: v for k, v in malla.items() if k != "zona_utm"}
    ruta, meta = io_batimetria.generar_bot(
        malla_io, zona_utm, destino, nombre=nombre or "bati.bot")
    log = (f"Batimetría: {ruta.name} — prof. {meta['prof_min']:.1f} a "
           f"{meta['prof_max']:.1f} m, {meta['pct_tierra']:.0f}% en tierra.")
    return {"ruta": str(ruta), "log": log}


def derivar_borde(ruta_serie, modo, tr):
    ds = io_oleaje.cargar(ruta_serie)
    borde = borde_oleaje.condicion_borde(ds, modo, int(tr))
    ds.close()
    return {
        "hs": borde.get("hs"),
        "per": borde.get("per"),
        "dir": borde.get("dir"),
        "dd": borde.get("dd", 20.0),
        "descripcion": borde.get("descripcion", ""),
    }


def info_carpeta_swan(carpeta):
    p = Path(carpeta)
    casos = swan_runner.casos_ordenados(str(p))
    nonst = io_swan_nonst.es_corrida_nonst(p)
    tipo = ("no estacionaria → video" if nonst
            else "estacionaria → tablero de mapas")
    return {
        "casos": casos,
        "nonst": nonst,
        "resumen": f"Carpeta: {p.name}\nDetectada como {tipo}.",
    }


def validar_nido(malla_grande, malla_nido):
    errores, avisos = swan_builder.validar_caso_anidado(malla_grande, malla_nido)
    return {"errores": errores, "avisos": avisos}


def validar_correr_swan(ctx):
    """Valida contexto del wizard modelar antes de escribir/correr."""
    dominios = ctx.get("dominios", [])
    destino = ctx.get("carpeta_caso")
    if not dominios or not destino:
        return {"errores": ["Completa malla, batimetría y borde."], "avisos": []}
    g = dominios[0]
    if any(k not in g for k in ("malla", "bot", "bordes")):
        return {"errores": ["Faltan malla, batimetría o borde del dominio grande."],
                "avisos": []}

    destino = Path(destino)
    bot_g = Path(g["bot"])
    if bot_g.parent != destino:
        (destino / bot_g.name).write_bytes(bot_g.read_bytes())
    malla_g = {k: v for k, v in g["malla"].items() if k != "zona_utm"}
    bordes = g["bordes"]

    errores, avisos = swan_builder.validar_caso(
        malla_g, {"archivo": bot_g.name}, bordes, carpeta=destino)

    anidado = len(dominios) >= 2
    if anidado:
        n = dominios[1]
        if any(k not in n for k in ("malla", "bot")):
            return {"errores": ["Faltan malla y batimetría del nido."], "avisos": avisos}
        bot_n = Path(n["bot"])
        if bot_n.parent != destino:
            (destino / bot_n.name).write_bytes(bot_n.read_bytes())
        malla_n = {k: v for k, v in n["malla"].items() if k != "zona_utm"}
        e_an, a_an = swan_builder.validar_caso_anidado(g["malla"], n["malla"])
        errores += e_an
        avisos += a_an
        e_n, a_n = swan_builder.validar_caso(
            malla_n, {"archivo": bot_n.name}, [], carpeta=destino,
            requiere_bordes=False)
        errores += e_n
        avisos += a_n

    return {"errores": errores, "avisos": avisos, "anidado": anidado}


def escribir_caso_swan(ctx, nombre):
    """Genera .swn (par anidado o simple). Devuelve log de escritura."""
    dominios = ctx["dominios"]
    destino = Path(ctx["carpeta_caso"])
    g = dominios[0]
    bot_g = Path(g["bot"])
    malla_g = {k: v for k, v in g["malla"].items() if k != "zona_utm"}
    bordes = g["bordes"]
    logs = []
    anidado = len(dominios) >= 2
    if anidado:
        n = dominios[1]
        malla_n = {k: v for k, v in n["malla"].items() if k != "zona_utm"}
        ruta_g, ruta_n = swan_builder.escribir_par_anidado(
            destino, nombre, nombre + "_nido",
            malla_g, {"archivo": bot_g.name}, bordes,
            malla_n, {"archivo": Path(n["bot"]).name},
            salidas=("Hs", "Tp", "Dir"),
            punto_espectral=n.get("punto_espectral"))
        logs.append(f"Par anidado generado: {ruta_g.name}, {ruta_n.name}")
    else:
        ruta_swn = swan_builder.escribir_caso(
            destino, nombre, nombre=nombre, malla=malla_g,
            batimetria={"archivo": bot_g.name}, bordes=bordes,
            salidas=("Hs", "Tp", "Dir"), estacionario=True)
        logs.append(f"Caso generado: {ruta_swn.name}")
    return "\n".join(logs)


def correr_swan_carpeta(carpeta, log_fn=None, progreso_fn=None):
    ok, _ = swan_runner.correr_swan(
        str(carpeta), log=log_fn, progreso=progreso_fn)
    return ok


def generar_tablero_oleaje(ruta, abrir=True):
    out = tablero_oleaje.generar_tablero(str(ruta))
    if abrir:
        _abrir(out)
    return str(out)


def generar_tablero_swan_mapas(carpeta, utm_large=None, abrir=True):
    out = tablero_swan.generar_tablero_swan(carpeta, utm_large=utm_large)
    if abrir:
        _abrir(out)
    return str(out)


def generar_video_swan(carpeta, utm_large=None, progreso_fn=None, abrir=True):
    out = video_swan.generar_videos(
        carpeta, multipanel=True, utm_large=utm_large, progreso=progreso_fn)[0]
    if abrir:
        _abrir(out)
    return str(out)


def despachar_avanzado(ruta, utm_large=None, progreso_fn=None):
    """Autodetecta entrada y genera producto (como VistaAvanzado._despachar)."""
    ruta = Path(ruta)
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
