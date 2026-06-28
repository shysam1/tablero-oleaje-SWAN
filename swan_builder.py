"""
Generador de archivos de comando SWAN (.swn) a partir de parámetros.

Arma un caso SWAN estacionario o no estacionario con la estructura de los .swn
del usuario (CGRID + batimetría INPGRID/READINP + condiciones de borde JONSWAP +
física estándar de costa + salidas BLOCK). Pensado para el asistente de la GUI:
el usuario rellena los parámetros esenciales y este módulo escribe un .swn válido
listo para correr con swan_runner.

No cubre todas las opciones de SWAN, sólo el flujo típico de propagación de
oleaje hacia la costa que usa el usuario; el resto se edita a mano si hace falta.
"""

from pathlib import Path
import math

import seguridad

_G = 9.81                                  # gravedad [m/s²]

# Cantidad SWAN por variable de salida (coincide con _QUANT_VAR de io_swan).
_QUANT = {"Hs": "HS", "Tp": "TPS", "Dir": "DIR", "Setup": "SETUP"}
_ARCHIVO = {"Hs": "Hs.txt", "Tp": "Tp.txt", "Dir": "Dir.txt", "Setup": "Setup.txt"}


def _completar(malla, batimetria):
    """Aplica los valores por defecto de malla e INPGRID (igual que construir_swn)."""
    m = {"alpc": 0.0, "mdc": 180, "flow": 0.04, "fhigh": 1.0, "msc": 30, **malla}
    if m["mxc"] <= 0 or m["myc"] <= 0:
        raise ValueError("mxc y myc deben ser > 0.")
    if m["xlenc"] <= 0 or m["ylenc"] <= 0:
        raise ValueError("xlenc y ylenc deben ser > 0.")
    b = {"xpinp": m["xpc"], "ypinp": m["ypc"], "alpinp": 0.0,
         "mxinp": m["mxc"], "myinp": m["myc"],
         "dxinp": m["xlenc"] / m["mxc"], "dyinp": m["ylenc"] / m["myc"],
         "fac": 1.0, "idla": 1, **batimetria}
    return m, b


def validar_caso(malla, batimetria, bordes, carpeta=None, requiere_bordes=True):
    """
    Comprueba la coherencia física del caso antes de generarlo/correrlo.

    Devuelve (errores, advertencias): los errores impiden una corrida con sentido
    (se debería abortar); las advertencias sugieren revisar pero no bloquean.
    Si se da `carpeta`, valida también el tamaño del archivo de batimetría.
    """
    m, b = _completar(malla, batimetria)
    errores, avisos = [], []

    # Malla con sentido.
    if m["mxc"] < 2 or m["myc"] < 2:
        errores.append("La malla necesita al menos 2 celdas por lado.")
    if m["xlenc"] <= 0 or m["ylenc"] <= 0:
        errores.append("El tamaño del dominio (largo X/Y) debe ser positivo.")

    # La batimetría (INPGRID) debe cubrir todo el dominio de cómputo (CGRID).
    cubre = (b["xpinp"] <= m["xpc"] and b["ypinp"] <= m["ypc"] and
             b["xpinp"] + b["mxinp"] * b["dxinp"] >= m["xpc"] + m["xlenc"] - 1e-6 and
             b["ypinp"] + b["myinp"] * b["dyinp"] >= m["ypc"] + m["ylenc"] - 1e-6)
    if not cubre:
        errores.append("La batimetría (INPGRID) no cubre todo el dominio de "
                       "cómputo (CGRID); SWAN no tendría fondo en parte de la malla.")

    # Tamaño del archivo de batimetría = (mxinp+1)·(myinp+1) valores.
    if carpeta is not None:
        ruta_bot = Path(batimetria.get("ruta") or (Path(carpeta) / b["archivo"]))
        if not ruta_bot.exists():
            errores.append(f"No se encuentra la batimetría '{b['archivo']}'.")
        else:
            n = len(ruta_bot.read_text().split())
            esperado = (b["mxinp"] + 1) * (b["myinp"] + 1)
            if n != esperado:
                errores.append(
                    f"La batimetría '{b['archivo']}' tiene {n} valores; el INPGRID "
                    f"espera {esperado} ({b['myinp'] + 1}×{b['mxinp'] + 1}). "
                    f"Revisa mxinp/myinp o el archivo.")

    # Resolución de malla frente a la longitud de onda en aguas profundas.
    dmax = max(m["xlenc"] / m["mxc"], m["ylenc"] / m["myc"])
    pers = [bd["per"] for bd in bordes
            if seguridad.es_finito_positivo(bd.get("per"))]
    tp = min(pers, default=None)
    if tp:
        L0 = _G * tp ** 2 / (2 * math.pi)
        celdas = L0 / dmax
        if celdas < 4:
            avisos.append(
                f"Resolución gruesa: ~{celdas:.1f} celdas por longitud de onda "
                f"(L0={L0:.0f} m con Tp={tp:g} s, dx≈{dmax:.0f} m). En aguas "
                f"someras la onda es más corta aún; considera más celdas.")

    # Condiciones de borde.
    if requiere_bordes and not bordes:
        errores.append("Define al menos una condición de borde (lado de entrada).")
    for bd in bordes:
        lado = bd.get("lado", "?")
        hs = bd.get("hs")
        if not seguridad.es_finito_positivo(hs):
            errores.append(f"Hs del borde {lado} debe ser > 0.")
        per = bd.get("per")
        if not seguridad.es_finito_positivo(per):
            errores.append(f"Falta el periodo del borde {lado} o no es válido.")
        dir_ = bd.get("dir")
        if dir_ is None:
            errores.append(f"Falta la dirección del borde {lado}.")
        elif not seguridad.es_finito_en_rango(dir_, 0.0, 360.0):
            avisos.append(f"La dirección del borde {lado} ({dir_}°) "
                          f"está fuera de 0–360°.")

    return errores, avisos


def construir_swn(nombre, malla, batimetria, bordes, salidas=("Hs", "Tp", "Dir"),
                  estacionario=True, tiempo=None, friccion=True, setup=True,
                  viento=False, cuadruples=False,
                  nido=None, bou_nest=None, punto_espectral=None):
    """
    Devuelve el texto de un .swn.

    nombre:    nombre del proyecto (PROJ).
    malla:     dict con xpc, ypc, xlenc, ylenc, mxc, myc y, opcionales, alpc=0,
               mdc=180, flow=0.04, fhigh=1.0, msc=30.
    batimetria:dict con 'archivo' y, opcionales, xpinp/ypinp/mxinp/myinp/dxinp/
               dyinp/fac (por defecto se derivan de la malla) e 'idla' (=1).
    bordes:    lista de dicts {lado: 'N'|'S'|'E'|'W', hs, per, dir, dd}.
    salidas:   variables a escribir como BLOCK (Hs/Tp/Dir/Setup).
    estacionario: True → COMPUTE STAT; False → COMPUTE NONSTAT con `tiempo`.
    tiempo:    dict {inicio, paso, fin} en formato 'YYYYMMDD.HHMMSS' (no estac.).
    nido:      dict {sname, nestfile, xpn, ypn, xlenn, ylenn, mxn, myn}. Si se da,
               el dominio emite NGRID + NESTOUT (es el grande de un anidado).
    bou_nest:  nombre del archivo de contorno. Si se da, el dominio usa
               BOU NEST en vez de BOUN SIDE (es el nido de un anidado).
    punto_espectral: dict {x, y, archivo}. Si se da, emite POINTS + SPEC 2D.
    """
    m, b = _completar(malla, batimetria)
    nombre = seguridad.escapar_comilla_swan(nombre)
    bot_file = seguridad.escapar_comilla_swan(b["archivo"])

    L = ["$ Archivo SWAN generado por el Tablero de Oleaje",
         f"PROJ '{nombre}' '1'",
         "$",
         "$ Direcciones en convención náutica (de dónde viene el oleaje).",
         "SET NAUTICAL",
         "$",
         "$*********** Malla y batimetría ***********",
         f"CGRID {m['xpc']} {m['ypc']} {m['alpc']} {m['xlenc']} {m['ylenc']} "
         f"{m['mxc']} {m['myc']} CIRCLE {m['mdc']} {m['flow']} {m['fhigh']} {m['msc']}",
         f"INPGRID BOTTOM {b['xpinp']} {b['ypinp']} {b['alpinp']} "
         f"{b['mxinp']} {b['myinp']} {b['dxinp']} {b['dyinp']}",
         f"READINP BOTTOM {b['fac']} '{bot_file}' {b['idla']} 0 FREE"]

    L += ["$", "$*********** Condiciones de borde ***********"]
    if bou_nest:
        nest = seguridad.escapar_comilla_swan(bou_nest)
        L.append(f"BOU NEST '{nest}' CLOSED")
    else:
        L.append("BOU SHAPE JONSWAP 3.3 PEAK DSPR DEGREES")
        for bd in bordes:
            dd = bd.get("dd", 0.0)
            L.append(f"BOUN SIDE {bd['lado']} CCW CON PAR "
                     f"{bd['hs']} {bd['per']} {bd['dir']} {dd}")

    L += ["$", "$*********** Procesos físicos ***********"]
    if not viento:
        L.append("OFF WINDGROWTH")
    if not cuadruples:
        L.append("OFF QUAD")
    L.append("BREAKING CON 1.0 0.29")
    if friccion:
        L.append("FRICTION")
    if setup:
        L.append("SETUP")

    L += ["$", "$*********** Salidas ***********"]
    if nido:
        sname = seguridad.escapar_comilla_swan(nido["sname"])
        nestfile = seguridad.escapar_comilla_swan(nido["nestfile"])
        L.append(f"NGRID '{sname}' {nido['xpn']} {nido['ypn']} 0. "
                 f"{nido['xlenn']} {nido['ylenn']} {nido['mxn']} {nido['myn']}")
    for var in salidas:
        if var in _QUANT:
            L.append(f"BLOCK 'COMPGRID' NOHEADER '{_ARCHIVO[var]}' {_QUANT[var]}")
    if nido:
        L.append(f"NESTOUT '{sname}' '{nestfile}'")
    if punto_espectral:
        pe = punto_espectral
        spec_arch = seguridad.escapar_comilla_swan(pe["archivo"])
        L.append(f"POINTS 'SpecOut' {pe['x']} {pe['y']}")
        L.append(f"SPEC 'SpecOut' SPEC2D ABS '{spec_arch}'")

    L.append("$")
    if estacionario:
        L.append("COMPUTE")
    else:
        t = tiempo or {}
        for clave in ("inicio", "paso", "fin"):
            if not str(t.get(clave, "")).strip():
                raise ValueError(
                    "Modo no estacionario requiere inicio, paso y fin "
                    "(formato YYYYMMDD.HHMMSS).")
        L.append(f"COMPUTE NONSTAT {t['inicio']} {t['paso']} {t['fin']}")
    L += ["STOP", ""]
    return "\n".join(L)


def escribir_caso(carpeta, nombre_archivo, **kwargs):
    """
    Escribe un .swn en `carpeta` con `construir_swn(**kwargs)` y devuelve su ruta.
    El nombre del archivo se normaliza a extensión .swn.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    stem = seguridad.sanitizar_nombre_caso(
        Path(str(nombre_archivo)).stem)
    ruta = (carpeta / stem).with_suffix(".swn")
    ruta.write_text(construir_swn(**kwargs), encoding="utf-8")
    return ruta


def validar_caso_anidado(malla_g, malla_n):
    """
    Comprueba la coherencia del par grande/nido. Devuelve (errores, avisos).

    El nido debe estar contenido en el grande, en la misma zona UTM, y con celda
    más fina (lo último es sólo aviso).
    """
    errores, avisos = [], []
    for etiqueta, m in (("grande", malla_g), ("nido", malla_n)):
        if int(m.get("mxc", 0)) <= 0 or int(m.get("myc", 0)) <= 0:
            errores.append(
                f"La malla {etiqueta} necesita mxc y myc mayores que cero.")
            return errores, avisos
    gx0, gy0 = malla_g["xpc"], malla_g["ypc"]
    gx1, gy1 = gx0 + malla_g["xlenc"], gy0 + malla_g["ylenc"]
    nx0, ny0 = malla_n["xpc"], malla_n["ypc"]
    nx1, ny1 = nx0 + malla_n["xlenc"], ny0 + malla_n["ylenc"]
    if not (nx0 >= gx0 - 1e-6 and ny0 >= gy0 - 1e-6 and
            nx1 <= gx1 + 1e-6 and ny1 <= gy1 + 1e-6):
        errores.append("El nido no está contenido en el dominio grande; "
                       "ajusta su centro o tamaño para que quede dentro.")

    zg, zn = malla_g.get("zona_utm"), malla_n.get("zona_utm")
    if zg and zn and zg != zn:
        errores.append(f"El nido está en zona UTM {zn} y el grande en {zg}; "
                       f"deben coincidir.")

    cg = max(malla_g["xlenc"] / malla_g["mxc"], malla_g["ylenc"] / malla_g["myc"])
    cn = max(malla_n["xlenc"] / malla_n["mxc"], malla_n["ylenc"] / malla_n["myc"])
    if cn >= cg:
        avisos.append(f"La celda del nido (~{cn:.0f} m) no es más fina que la del "
                      f"grande (~{cg:.0f} m); el anidamiento aporta poco.")
    return errores, avisos


def escribir_par_anidado(carpeta, nombre_grande, nombre_nido, malla_g, bat_g,
                         bordes, malla_n, bat_n, salidas=("Hs", "Tp", "Dir"),
                         punto_espectral=None, estacionario=True, tiempo=None):
    """
    Escribe el par de `.swn` de un modelo anidado y devuelve (ruta_grande, ruta_nido).

    El grande lleva NGRID + NESTOUT (recuadro del nido); el nido lleva BOU NEST y,
    opcionalmente, un punto de salida espectral. Las mallas deben venir sin la clave
    'zona_utm' (se quita en la GUI antes de llamar).
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    stem_g = seguridad.sanitizar_nombre_caso(Path(str(nombre_grande)).stem)
    stem_n = seguridad.sanitizar_nombre_caso(Path(str(nombre_nido)).stem)
    sname, nestfile = "nido1", "nest1"
    nido = {"sname": sname, "nestfile": nestfile,
            "xpn": malla_n["xpc"], "ypn": malla_n["ypc"],
            "xlenn": malla_n["xlenc"], "ylenn": malla_n["ylenc"],
            "mxn": malla_n["mxc"], "myn": malla_n["myc"]}
    ruta_g = (carpeta / stem_g).with_suffix(".swn")
    ruta_g.write_text(construir_swn(stem_g, malla_g, bat_g, bordes,
                                    salidas=salidas, estacionario=estacionario,
                                    tiempo=tiempo, nido=nido), encoding="utf-8")
    ruta_n = (carpeta / stem_n).with_suffix(".swn")
    ruta_n.write_text(construir_swn(stem_n, malla_n, bat_n, [],
                                    salidas=salidas, estacionario=estacionario,
                                    tiempo=tiempo, bou_nest=nestfile,
                                    punto_espectral=punto_espectral),
                      encoding="utf-8")
    return ruta_g, ruta_n


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # Ejemplo: caso de demostración (malla genérica + un borde NW).
    texto = construir_swn(
        nombre="DemoOleaje",
        malla={"xpc": 0.0, "ypc": 0.0, "xlenc": 10000, "ylenc": 12000,
               "mxc": 100, "myc": 120},
        batimetria={"archivo": "fondo.bot"},
        bordes=[{"lado": "W", "hs": 3.0, "per": 12.0, "dir": 290.0, "dd": 20.0},
                {"lado": "N", "hs": 3.0, "per": 12.0, "dir": 290.0, "dd": 20.0}],
        salidas=("Hs", "Tp", "Dir", "Setup"))
    print(texto)
