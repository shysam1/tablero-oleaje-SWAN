"""
Carga de corridas SWAN (campos espaciales 2D) a Datasets de xarray.

Lee una carpeta de corrida SWAN (.swn + salidas BLOCK .txt + batimetría .bot) y
construye un Dataset 2D por dominio (grande + anidados) con coordenadas UTM
reales. Replica las convenciones de los scripts MATLAB del usuario (reshape +
flipud, valores de relleno a NaN, offsets UTM), de modo que los campos coinciden
con lo ya validado en MATLAB.

A diferencia de io_oleaje (serie temporal en un punto), aquí cada variable es un
campo sobre la malla (dimensiones y, x) para una única condición (p. ej. TR100).

El módulo es GENÉRICO: autodetecta los dominios y campos de cualquier carpeta de
corrida estacionaria (no sólo el caso Coronel). Clasifica los .swn por su CGRID
(padre = origen local 0,0; anidados por su xpc,ypc), reconoce la variable de
cada salida .txt por su nombre y la asigna al dominio cuyo tamaño de malla
coincide. El offset UTM del dominio grande se pasa como parámetro (por defecto,
el de la corrida Coronel del usuario).
"""

from pathlib import Path
import re
import sys

import numpy as np
import xarray as xr

# Offset UTM del nodo (0,0) del dominio grande (por defecto, corrida Coronel).
UTM_LARGE_DEFAULT = (620494.0, 5876451.0)

# Valor de relleno (excepción de SWAN) por variable. None = todo valor < 0.
EXCEPCION = {"Hs": None, "Tp": -9.0, "Dir": -999.0, "Setup": -9.0}

ATRIBUTOS = {
    "Hs": {"long_name": "Altura significativa", "units": "m"},
    "Tp": {"long_name": "Periodo peak", "units": "s"},
    "Dir": {"long_name": "Dirección media", "units": "deg"},
    "Setup": {"long_name": "Set-up por oleaje", "units": "m"},
    "depth": {"long_name": "Profundidad", "units": "m"},
}

# Cantidad SWAN (último argumento del comando BLOCK) → variable física. Es la
# fuente robusta: el .swn declara qué archivo lleva qué cantidad, sin depender
# del nombre del archivo.
_QUANT_VAR = {"HS": "Hs", "HSIG": "Hs", "HSIGN": "Hs",
              "TPS": "Tp", "RTP": "Tp", "PER": "Tp", "TM01": "Tp", "TM02": "Tp",
              "DIR": "Dir", "PDIR": "Dir", "TDIR": "Dir",
              "SETUP": "Setup", "WATLEV": "Setup"}

# Patrón en el nombre del archivo → variable. Fallback si el .swn no declara el
# BLOCK (orden: setup antes que tp, para que 'SetUp' no se confunda).
_PATRON_VAR = (("setup", "Setup"), ("hs", "Hs"), ("tp", "Tp"), ("dir", "Dir"))


def _mapa_salidas(swns):
    """
    Mapa {nombre_archivo: variable} leído de los comandos BLOCK de los .swn.
    Formato: BLOCK 'sname' [NOHEADER] 'archivo' CANTIDAD [...]. La cantidad es
    el token que coincide con una cantidad SWAN conocida.
    """
    mapa = {}
    for swn in swns:
        for linea in Path(swn).read_text().splitlines():
            toks = linea.split()
            if not toks or toks[0].upper() != "BLOCK":
                continue
            comillas = re.findall(r"'([^']*)'", linea)
            if not comillas:
                continue
            cantidad = next((t.upper() for t in toks if t.upper() in _QUANT_VAR),
                            None)
            if cantidad:
                mapa[comillas[-1]] = _QUANT_VAR[cantidad]
    return mapa


def _leer_cgrid(ruta_swn):
    """
    Extrae la geometría de malla del comando CGRID de un .swn, incluyendo el
    origen LOCAL (xpc, ypc) necesario para ubicar un dominio anidado.
    """
    for linea in Path(ruta_swn).read_text().splitlines():
        partes = linea.split()
        if partes and partes[0].upper() == "CGRID":
            x0, y0 = float(partes[1]), float(partes[2])
            xlenc, ylenc = float(partes[4]), float(partes[5])
            mxc, myc = int(partes[6]), int(partes[7])
            return {"nx": mxc + 1, "ny": myc + 1,
                    "dx": xlenc / mxc, "dy": ylenc / myc,
                    "x0_local": x0, "y0_local": y0}
    raise ValueError(f"No se encontró CGRID en {ruta_swn}")


def _var_de_nombre(nombre):
    """Deduce la variable física de una salida por el nombre del archivo."""
    n = nombre.lower()
    for clave, var in _PATRON_VAR:
        if clave in n:
            return var
    return None


def _leer_campo(ruta_txt, nx, ny, excepcion):
    """
    Lee una salida BLOCK de SWAN (lista plana de valores) y la reesculpe a la
    malla (ny, nx) con la misma convención que MATLAB: reshape + flipud.
    """
    valores = np.array(Path(ruta_txt).read_text().split(), dtype=float)
    if valores.size != nx * ny:
        raise ValueError(f"{Path(ruta_txt).name}: {valores.size} valores; "
                         f"se esperaban {nx * ny} ({ny}x{nx})")
    campo = np.flipud(valores.reshape(ny, nx))
    if excepcion is None:
        campo[campo < 0] = np.nan
    else:
        campo[np.isclose(campo, excepcion)] = np.nan
    return campo


def _meta_condicion(ruta_swn):
    """Extrae Hs/Tp/Dp de la marejada desde el encabezado comentado del .swn."""
    texto = Path(ruta_swn).read_text()
    meta = {}
    for clave, patron in (("Hs_borde", r"Hs\s*=\s*([\d.]+)"),
                          ("Tp_borde", r"Tp\s*=\s*([\d.]+)"),
                          ("Dp_borde", r"Dp\s*=\s*([\d.]+)")):
        encontrado = re.search(patron, texto)
        if encontrado:
            meta[clave] = float(encontrado.group(1))
    return meta


def leer_espectro_swan(carpeta, archivo=None):
    """
    Lee un espectro 2D de SWAN (SPEC2D) y devuelve un Dataset S(freq, dir).

    Formato: bloques AFREQ (frecuencias), CDIR (direcciones), QUANT y FACTOR,
    seguidos de una matriz nfreq x ndir de enteros. La densidad de energía es
    entero x factor; el valor de excepción pasa a NaN. Si no se da `archivo`, se
    busca cualquiera cuyo nombre contenga 'spectro'/'spec'.
    """
    ruta = Path(carpeta)
    if ruta.is_dir():
        candidatos = ([ruta / archivo] if archivo else
                      sorted(ruta.glob("*spectro*")) + sorted(ruta.glob("*[sS]pec*")))
        ruta = next((c for c in candidatos if c.exists()), None)
    if ruta is None or not ruta.exists():
        return None
    lineas = ruta.read_text().splitlines()

    def _bloque(i, n):
        vals = []
        while len(vals) < n:
            vals.append(float(lineas[i].split()[0]))
            i += 1
        return np.array(vals), i

    freqs = dirs = matriz = None
    factor, excepcion = 1.0, -99.0
    i, ntot = 0, len(lineas)
    while i < ntot:
        tokens = lineas[i].split()
        clave = tokens[0] if tokens else ""
        if clave in ("AFREQ", "RFREQ"):
            freqs, i = _bloque(i + 2, int(lineas[i + 1].split()[0]))
        elif clave in ("CDIR", "NDIR"):
            dirs, i = _bloque(i + 2, int(lineas[i + 1].split()[0]))
        elif "exception" in lineas[i]:
            excepcion = float(tokens[0])
            i += 1
        elif clave == "FACTOR":
            factor = float(lineas[i + 1].split()[0])
            i += 2
            matriz = np.array([list(map(float, lineas[i + r].split()))
                               for r in range(len(freqs))])
            i += len(freqs)
        else:
            i += 1

    if matriz is None:
        return None
    densidad = matriz * factor
    densidad[np.isclose(matriz, excepcion)] = np.nan
    ds = xr.Dataset({"Efth": (("freq", "dir"), densidad)},
                    coords={"freq": freqs, "dir": dirs})
    ds["Efth"].attrs = {"long_name": "Densidad de energía", "units": "m2/Hz/deg"}
    ds["freq"].attrs = {"long_name": "Frecuencia", "units": "Hz"}
    ds["dir"].attrs = {"long_name": "Dirección (cartesiana)", "units": "deg"}
    return ds


def _asignar_campos(candidatos):
    """
    De una lista de (variable, ruta) ya filtrada por tamaño de malla, asigna una
    sola ruta por variable. Si hay varias salidas para la misma variable (p. ej.
    una corrida repetida con archivos viejos sin borrar), antes ganaba la última
    en silencio; ahora se avisa y se conserva la MÁS RECIENTE, para no usar un
    resultado obsoleto sin que el usuario lo sepa.
    """
    por_var = {}
    for var, ruta in candidatos:
        por_var.setdefault(var, []).append(ruta)
    campos = {}
    for var, rutas_var in por_var.items():
        if len(rutas_var) > 1:
            elegido = max(rutas_var, key=lambda r: Path(r).stat().st_mtime)
            otros = ", ".join(sorted(Path(r).name for r in rutas_var
                                     if r != elegido))
            print(f"  [aviso] {len(rutas_var)} archivos para '{var}' con el mismo "
                  f"tamaño de malla; se usa el más reciente ({Path(elegido).name}) "
                  f"y se ignoran: {otros}")
            campos[var] = elegido
        else:
            campos[var] = rutas_var[0]
    return campos


def _detectar_dominios(carpeta, utm_large, titulos):
    """
    Autodetecta los dominios desde los .swn y reparte las salidas .txt por
    variable (nombre) y dominio (tamaño de campo). Devuelve {nombre: cfg}.
    """
    swns = sorted(carpeta.glob("*.swn"))
    if not swns:
        raise ValueError(f"No hay .swn en {carpeta}")
    geos = {s: _leer_cgrid(s) for s in swns}

    padres = [s for s, g in geos.items()
              if g["x0_local"] == 0 and g["y0_local"] == 0]
    padre = padres[0] if padres else max(geos, key=lambda s: geos[s]["nx"] * geos[s]["ny"])

    # Variable de cada salida: primero por el BLOCK del .swn (robusto), si no por
    # el nombre del archivo. Inventario: (ruta, variable, nº de valores). Se
    # excluye el espectro y cualquier .txt que no sea un campo.
    mapa_block = _mapa_salidas(swns)
    inv = []
    for txt in sorted(carpeta.glob("*.txt")):
        var = mapa_block.get(txt.name) or _var_de_nombre(txt.name)
        if var is None or "spec" in txt.name.lower():
            continue
        try:
            n = len(txt.read_text().split())
        except Exception:
            continue
        inv.append((txt, var, n))
    bots = list(carpeta.glob("*.bot"))

    def cfg_de(geo, utm, swn, nombre, titulo):
        ny, nx = geo["ny"], geo["nx"]
        campos = _asignar_campos([(var, ruta) for ruta, var, n in inv
                                  if n == nx * ny])
        bot = next((b for b in bots
                    if len(Path(b).read_text().split()) == nx * ny), None)
        return {"geo": geo, "utm": utm, "campos": campos, "bot": bot,
                "swn": swn, "titulo": titulos.get(nombre, titulo)}

    dominios = {"large": cfg_de(geos[padre], utm_large, padre, "large",
                                "Dominio grande")}
    i = 1
    for s, g in geos.items():
        if s == padre:
            continue
        utm = (utm_large[0] + g["x0_local"], utm_large[1] + g["y0_local"])
        nombre = f"n{i}"
        dominios[nombre] = cfg_de(g, utm, s, nombre, f"Dominio anidado {nombre}")
        i += 1
    return dominios


def _construir_dataset(cfg):
    """Construye el Dataset 2D (UTM) de un dominio a partir de su cfg."""
    geo, (x0, y0) = cfg["geo"], cfg["utm"]
    nx, ny = geo["nx"], geo["ny"]
    x = x0 + np.arange(nx) * geo["dx"]
    y = y0 + np.arange(ny) * geo["dy"]

    data_vars = {}
    for var, ruta in cfg["campos"].items():
        data_vars[var] = (("y", "x"), _leer_campo(ruta, nx, ny, EXCEPCION[var]))

    if cfg["bot"] is not None:
        bat = np.array(Path(cfg["bot"]).read_text().split(), dtype=float)
        if bat.size == nx * ny:
            data_vars["depth"] = (("y", "x"), np.flipud(bat.reshape(ny, nx)))

    ds = xr.Dataset(data_vars, coords={"x": x, "y": y})
    for v in ds.data_vars:
        ds[v].attrs.update(ATRIBUTOS.get(v, {}))
    ds["x"].attrs.update({"long_name": "Este UTM", "units": "m"})
    ds["y"].attrs.update({"long_name": "Norte UTM", "units": "m"})
    ds.attrs.update({"titulo": cfg["titulo"]})
    return ds


def cargar_corrida(carpeta, utm_large=UTM_LARGE_DEFAULT, titulos=None):
    """
    Carga una corrida SWAN completa desde su carpeta.

    Parámetros:
      utm_large: offset UTM del nodo (0,0) del dominio grande (otra corrida).
      titulos:   dict opcional {nombre_dominio: título} para rotular los mapas.

    Devuelve un dict con: 'dominios' (Datasets large/n1… disponibles), 'espectro'
    (S(f,θ) si existe) y 'meta' (condición de borde Hs/Tp/Dp + nombre = carpeta).
    """
    carpeta = Path(carpeta)
    cfgs = _detectar_dominios(carpeta, utm_large, titulos or {})

    meta = _meta_condicion(cfgs["large"]["swn"])
    meta["condicion"] = carpeta.name

    dominios = {nombre: _construir_dataset(cfg) for nombre, cfg in cfgs.items()
                if cfg["campos"]}
    for ds in dominios.values():
        ds.attrs.update(meta)
    return {"dominios": dominios, "espectro": leer_espectro_swan(carpeta),
            "meta": meta}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    CARPETA = Path(
        r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python"
        r"\SWAN_Coronel\extremo_Tr100")
    TITULOS = {"large": "Dominio grande (Golfo de Arauco)",
               "n1": "Dominio anidado N1 (Bahía de Coronel)"}

    corrida = cargar_corrida(CARPETA, titulos=TITULOS)
    print("Condición:", corrida["meta"])
    for nombre, ds in corrida["dominios"].items():
        print("=" * 55)
        print(f"{nombre}  ->  malla {dict(ds.sizes)}")
        for v in ds.data_vars:
            da = ds[v]
            print(f"  {v:6s} min={float(da.min()):8.3f}  "
                  f"max={float(da.max()):8.3f}  NaN={int(da.isnull().sum())}")
