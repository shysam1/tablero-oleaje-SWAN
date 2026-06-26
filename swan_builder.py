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

_G = 9.81                                  # gravedad [m/s²]

# Cantidad SWAN por variable de salida (coincide con _QUANT_VAR de io_swan).
_QUANT = {"Hs": "HS", "Tp": "TPS", "Dir": "DIR", "Setup": "SETUP"}
_ARCHIVO = {"Hs": "Hs.txt", "Tp": "Tp.txt", "Dir": "Dir.txt", "Setup": "Setup.txt"}


def _completar(malla, batimetria):
    """Aplica los valores por defecto de malla e INPGRID (igual que construir_swn)."""
    m = {"alpc": 0.0, "mdc": 180, "flow": 0.04, "fhigh": 1.0, "msc": 30, **malla}
    b = {"xpinp": m["xpc"], "ypinp": m["ypc"], "alpinp": 0.0,
         "mxinp": m["mxc"], "myinp": m["myc"],
         "dxinp": m["xlenc"] / m["mxc"], "dyinp": m["ylenc"] / m["myc"],
         "fac": 1.0, "idla": 1, **batimetria}
    return m, b


def validar_caso(malla, batimetria, bordes, carpeta=None):
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
        ruta_bot = Path(carpeta) / b["archivo"]
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
    tp = min((bd["per"] for bd in bordes), default=None)
    if tp:
        L0 = _G * tp ** 2 / (2 * math.pi)
        celdas = L0 / dmax
        if celdas < 4:
            avisos.append(
                f"Resolución gruesa: ~{celdas:.1f} celdas por longitud de onda "
                f"(L0={L0:.0f} m con Tp={tp:g} s, dx≈{dmax:.0f} m). En aguas "
                f"someras la onda es más corta aún; considera más celdas.")

    # Condiciones de borde.
    if not bordes:
        errores.append("Define al menos una condición de borde (lado de entrada).")
    for bd in bordes:
        if bd["hs"] <= 0:
            errores.append(f"Hs del borde {bd['lado']} debe ser > 0.")
        if not 0 <= bd["dir"] <= 360:
            avisos.append(f"La dirección del borde {bd['lado']} ({bd['dir']}°) "
                          f"está fuera de 0–360°.")
        if bd["per"] <= 0:
            errores.append(f"El periodo del borde {bd['lado']} debe ser > 0.")

    return errores, avisos


def construir_swn(nombre, malla, batimetria, bordes, salidas=("Hs", "Tp", "Dir"),
                  estacionario=True, tiempo=None, friccion=True, setup=True,
                  viento=False, cuadruples=False):
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
    """
    m, b = _completar(malla, batimetria)

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
         f"READINP BOTTOM {b['fac']} '{b['archivo']}' {b['idla']} 0 FREE",
         "$",
         "$*********** Condiciones de borde ***********",
         "BOU SHAPE JONSWAP 3.3 PEAK DSPR DEGREES"]

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
    for var in salidas:
        if var in _QUANT:
            L.append(f"BLOCK 'COMPGRID' NOHEADER '{_ARCHIVO[var]}' {_QUANT[var]}")

    L.append("$")
    if estacionario:
        L.append("COMPUTE")
    else:
        t = tiempo or {}
        L.append(f"COMPUTE NONSTAT {t.get('inicio','')} {t.get('paso','')} "
                 f"{t.get('fin','')}")
    L += ["STOP", ""]
    return "\n".join(L)


def escribir_caso(carpeta, nombre_archivo, **kwargs):
    """
    Escribe un .swn en `carpeta` con `construir_swn(**kwargs)` y devuelve su ruta.
    El nombre del archivo se normaliza a extensión .swn.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = (carpeta / nombre_archivo).with_suffix(".swn")
    ruta.write_text(construir_swn(**kwargs), encoding="utf-8")
    return ruta


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
