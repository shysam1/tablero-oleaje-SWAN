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
import json
import re
import sys

import numpy as np
import xarray as xr

# Offset UTM del nodo (0,0) del dominio grande (por defecto, corrida Coronel).
UTM_LARGE_DEFAULT = (620494.0, 5876451.0)
META_CASO = "tablero_swan.json"

# Valor de relleno (excepción de SWAN) por variable. None = todo valor < 0.
EXCEPCION = {"Hs": None, "Tp": -9.0, "Dir": -999.0, "Setup": -9.0,
             "Tm01": -9.0, "Tm02": -9.0, "Tmean": -9.0,
             "WaterLevel": -9.0, "Dp": -999.0, "Dtransport": -999.0}

ATRIBUTOS = {
    "Hs": {"long_name": "Altura significativa", "units": "m"},
    "Tp": {"long_name": "Periodo peak", "units": "s"},
    "Dir": {"long_name": "Dirección media", "units": "deg"},
    "Setup": {"long_name": "Set-up por oleaje", "units": "m"},
    "depth": {"long_name": "Profundidad", "units": "m"},
    "Tm01": {"long_name": "Periodo medio Tm01", "units": "s"},
    "Tm02": {"long_name": "Periodo medio Tm02", "units": "s"},
    "Tmean": {"long_name": "Periodo medio PER (definición SWAN)", "units": "s"},
    "WaterLevel": {"long_name": "Nivel de agua", "units": "m"},
    "Dp": {"long_name": "Dirección peak", "units": "deg"},
    "Dtransport": {"long_name": "Dirección del transporte de energía", "units": "deg"},
}

# Cantidad SWAN (último argumento del comando BLOCK) → variable física. Es la
# fuente robusta: el .swn declara qué archivo lleva qué cantidad, sin depender
# del nombre del archivo.
_QUANT_VAR = {"HS": "Hs", "HSIG": "Hs", "HSIGN": "Hs",
              "TPS": "Tp", "RTP": "Tp", "PER": "Tmean", "TM01": "Tm01", "TM02": "Tm02",
              "DIR": "Dir", "PDIR": "Dp", "TDIR": "Dtransport",
              "SETUP": "Setup", "WATLEV": "WaterLevel"}

# Patrón en el nombre del archivo → variable. Fallback si el .swn no declara el
# BLOCK (orden: setup antes que tp, para que 'SetUp' no se confunda).
_PATRON_VAR = (("setup", "Setup"), ("hs", "Hs"), ("tp", "Tp"), ("dir", "Dir"))


def _lineas_swn(ruta):
    """Lee comandos completos, sin comentarios, incluidos los continuados con &."""
    try:
        texto = Path(ruta).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        texto = Path(ruta).read_text(encoding="cp1252")
    pendiente = ""
    for linea in texto.splitlines():
        linea = linea.split("$", 1)[0].strip()
        if not linea:
            continue
        pendiente += " " + linea.rstrip("&").strip()
        if not linea.endswith("&"):
            yield pendiente.strip()
            pendiente = ""
    if pendiente:
        yield pendiente.strip()


def _convencion_direccion(swn):
    for linea in _lineas_swn(swn):
        partes = linea.upper().split()
        if partes[0] == "SET":
            if any(t.startswith("NAUT") for t in partes):
                return "nautica"
            if any(t.startswith("CART") for t in partes):
                return "cartesiana"
    return "cartesiana"


def _mapa_salidas(swns):
    """
    Mapa {nombre_archivo: variable} leído de los comandos BLOCK de los .swn.
    Formato: BLOCK 'sname' [NOHEADER] 'archivo' CANTIDAD [...]. La cantidad es
    el token que coincide con una cantidad SWAN conocida.
    """
    mapa = {}
    propietarios = {}
    for swn in swns:
        for linea in _lineas_swn(swn):
            toks = linea.split()
            if not toks or toks[0].upper() != "BLOCK":
                continue
            comillas = re.findall(r"'([^']*)'", linea)
            if not comillas:
                continue
            cantidad = next((t.upper() for t in toks if t.upper() in _QUANT_VAR),
                            None)
            if cantidad:
                nombre = comillas[-1]
                if nombre in propietarios and propietarios[nombre] != Path(swn):
                    raise ValueError(
                        f"Los casos {propietarios[nombre].name} y {Path(swn).name} "
                        f"escriben ambos '{nombre}'. Usa salidas distintas por dominio "
                        "y vuelve a ejecutar la corrida; los resultados pudieron sobrescribirse.")
                propietarios[nombre] = Path(swn)
                mapa[comillas[-1]] = _QUANT_VAR[cantidad]
    return mapa


def _leer_cgrid(ruta_swn):
    """
    Extrae la geometría de malla del comando CGRID de un .swn, incluyendo el
    origen LOCAL (xpc, ypc) necesario para ubicar un dominio anidado.
    """
    lineas = list(_lineas_swn(ruta_swn))
    if any(re.match(r"COORD\w*\s+SPHE", l, re.I) for l in lineas):
        raise ValueError("El visor SWAN admite mallas cartesianas; no mallas esféricas.")
    for linea in lineas:
        partes = linea.split()
        if partes and partes[0].upper() == "CGRID":
            if len(partes) > 1 and partes[1].upper().startswith("REG"):
                partes.pop(1)
            # CGRID xpc ypc alpc xlenc ylenc mxc myc … → se necesitan 8 tokens.
            if len(partes) < 8:
                raise ValueError(
                    f"CGRID incompleto en {Path(ruta_swn).name}: {linea.strip()!r}")
            try:
                x0, y0, angulo = map(float, partes[1:4])
            except ValueError as exc:
                raise ValueError("El visor SWAN admite CGRID regular rectangular.") from exc
            xlenc, ylenc = float(partes[4]), float(partes[5])
            mxc, myc = int(partes[6]), int(partes[7])
            if not np.isfinite([x0, y0, angulo, xlenc, ylenc]).all():
                raise ValueError("CGRID contiene valores no finitos.")
            if not np.isclose(angulo % 360, 0):
                raise ValueError("El visor SWAN aún no admite mallas rotadas (alpc distinto de 0).")
            if xlenc <= 0 or ylenc <= 0:
                raise ValueError("CGRID necesita extensiones positivas.")
            # mxc/myc son el nº de celdas: con 0 la malla es degenerada y dx/dy
            # dividirían por cero.
            if mxc <= 0 or myc <= 0:
                raise ValueError(
                    f"CGRID con mxc/myc no positivos ({mxc}, {myc}) en "
                    f"{Path(ruta_swn).name}; deben ser ≥ 1.")
            return {"nx": mxc + 1, "ny": myc + 1,
                    "dx": xlenc / mxc, "dy": ylenc / myc,
                    "x0_local": x0, "y0_local": y0}
    raise ValueError(f"No se encontró CGRID en {ruta_swn}")


def _dominio_grande_swn(carpeta):
    """Devuelve (ruta.swn, geo CGRID) del dominio padre / más grande."""
    carpeta = Path(carpeta)
    swns = sorted(carpeta.glob("*.swn"))
    if not swns:
        raise ValueError(f"No hay .swn en {carpeta}")
    geos = {s: _leer_cgrid(s) for s in swns}
    padres = [s for s in geos if not any(
        re.match(r"BOU\w*\s+NEST", linea, re.I) for linea in _lineas_swn(s))]
    # La cantidad de nodos puede ser mayor en un nido fino: manda el área física.
    padre = max(padres or list(geos), key=lambda s:
                (geos[s]["nx"] - 1) * geos[s]["dx"] *
                (geos[s]["ny"] - 1) * geos[s]["dy"])
    return padre, geos[padre]


def _utm_dominio(geo, geo_padre, utm_large):
    """Traslada todos los dominios por el mismo offset, también con CGRID absoluto."""
    return (utm_large[0] + geo["x0_local"] - geo_padre["x0_local"],
            utm_large[1] + geo["y0_local"] - geo_padre["y0_local"])


def _bot_de_dominio(swn, bots, nx, ny):
    """Prefiere el fondo declarado; evita elegir otro dominio del mismo tamaño."""
    for linea in _lineas_swn(swn):
        if re.match(r"READ\w*\s+BOT", linea, re.I):
            archivos = re.findall(r"'([^']*)'", linea)
            if archivos:
                ruta = Path(swn).parent / archivos[0]
                return ruta if ruta.is_file() and len(ruta.read_text().split()) == nx * ny else None
    candidatos = [b for b in bots if len(Path(b).read_text().split()) == nx * ny]
    return candidatos[0] if len(candidatos) == 1 else None


def _parece_utm_absoluto(x, y):
    """CGRID con coordenadas UTM reales (p. ej. malla desde lat/lon), no local 0,0."""
    return abs(x) >= 50000 or abs(y) >= 500000


def guardar_meta_caso(carpeta, malla_g, *, zona_utm=None, lat_centro=None,
                      lon_centro=None):
    """
    Guarda offset UTM junto al caso SWAN para que «Ver corrida» lo recupere.
    malla_g: dict con xpc, ypc (y opcionalmente el resto de la malla).
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = {
        "version": 1,
        "utm_x": float(malla_g["xpc"]),
        "utm_y": float(malla_g["ypc"]),
    }
    if zona_utm:
        datos["zona_utm"] = str(zona_utm)
    if lat_centro is not None and lon_centro is not None:
        datos["lat_centro"] = float(lat_centro)
        datos["lon_centro"] = float(lon_centro)
    (carpeta / META_CASO).write_text(
        json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inferir_utm_desde_carpeta(carpeta):
    """
    Deduce utm_x/utm_y para mapas y video.

    Orden: tablero_swan.json → CGRID UTM del dominio grande → default Coronel.
    Devuelve dict con utm_x, utm_y, origen ('meta'|'cgrid'|'default'), mensaje
    y zona_utm si está disponible.
    """
    carpeta = Path(carpeta)
    meta_ruta = carpeta / META_CASO
    if meta_ruta.is_file():
        try:
            meta = json.loads(meta_ruta.read_text(encoding="utf-8"))
            ux = float(meta["utm_x"])
            uy = float(meta["utm_y"])
            zona = meta.get("zona_utm")
            msg = "Leído de tablero_swan.json (caso generado por el Tablero)."
            if zona:
                msg += f" Zona {zona}."
            return {"utm_x": ux, "utm_y": uy, "zona_utm": zona,
                    "origen": "meta", "mensaje": msg}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    try:
        padre, geo = _dominio_grande_swn(carpeta)
    except ValueError:
        ux, uy = UTM_LARGE_DEFAULT
        return {"utm_x": ux, "utm_y": uy, "zona_utm": None,
                "origen": "default",
                "mensaje": "Sin .swn en la carpeta; offset UTM por defecto (Coronel)."}

    x0, y0 = geo["x0_local"], geo["y0_local"]
    if x0 == 0 and y0 == 0:
        ux, uy = UTM_LARGE_DEFAULT
        return {"utm_x": ux, "utm_y": uy, "zona_utm": None,
                "origen": "default",
                "mensaje": (
                    "CGRID del dominio grande en (0, 0) — convención local. "
                    "Se usa el offset UTM por defecto (Coronel); cámbialo si tu "
                    "caso es de otra zona.")}

    if _parece_utm_absoluto(x0, y0):
        return {"utm_x": x0, "utm_y": y0, "zona_utm": None,
                "origen": "cgrid",
                "mensaje": (
                    f"Detectado en CGRID de {padre.name} "
                    f"({x0:.0f}, {y0:.0f} m).")}

    ux, uy = UTM_LARGE_DEFAULT
    return {"utm_x": ux, "utm_y": uy, "zona_utm": None,
            "origen": "default",
            "mensaje": "No se pudo inferir UTM; se usa el valor por defecto (Coronel)."}


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
    """Recupera los bordes constantes; usa comentarios sólo para archivos antiguos."""
    bordes = []
    for linea in _lineas_swn(ruta_swn):
        if re.match(r"BOU\w*\s+SIDE", linea, re.I):
            par = re.search(r"\bPAR\w*\s+(\S+)\s+(\S+)\s+(\S+)", linea, re.I)
            if par:
                try:
                    bordes.append(tuple(float(v) for v in par.groups()))
                except ValueError:
                    continue
    if bordes:
        return {clave: bordes[0][i] for i, clave in
                enumerate(("Hs_borde", "Tp_borde", "Dp_borde"))
                if all(np.isclose(b[i], bordes[0][i]) for b in bordes)}
    try:
        texto = Path(ruta_swn).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        texto = Path(ruta_swn).read_text(encoding="cp1252")
    meta = {}
    for clave, patron in (("Hs_borde", r"Hs\s*=\s*([\d.]+)"),
                          ("Tp_borde", r"Tp\s*=\s*([\d.]+)"),
                          ("Dp_borde", r"Dp\s*=\s*([\d.]+)")):
        encontrado = re.search(patron, texto)
        if encontrado:
            meta[clave] = float(encontrado.group(1))
    return meta


def _validar_cabecera_espectro(lineas, nombre):
    """Rechaza formatos que el visor de un punto no puede representar fielmente."""
    conversion = 180.0 / np.pi
    for i, linea in enumerate(lineas):
        partes = linea.split()
        clave = partes[0].upper() if partes else ""
        if clave in ("LOCATIONS", "LONLAT", "QUANT"):
            if i + 1 >= len(lineas):
                raise ValueError(f"{nombre}: encabezado {clave} truncado.")
            if int(lineas[i + 1].split()[0]) != 1:
                raise ValueError(f"{nombre}: el visor admite un punto y una cantidad por espectro.")
        if clave == "QUANT":
            if i + 4 >= len(lineas):
                raise ValueError(f"{nombre}: encabezado QUANT truncado.")
            cantidad = lineas[i + 2].split()[0].lower()
            unidad = lineas[i + 3].split()[0].lower()
            if cantidad != "vadens" or unidad not in ("m2/hz/degr", "m2/hz/rad"):
                raise ValueError(f"{nombre}: se requiere VaDens en m2/Hz/degr o m2/Hz/rad.")
            conversion = 1.0 if unidad.endswith("/rad") else 180.0 / np.pi
    return conversion


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
    conversion = _validar_cabecera_espectro(lineas, ruta.name)

    def _bloque(i, n):
        vals = []
        while len(vals) < n:
            if i >= len(lineas):
                raise ValueError(
                    f"{ruta.name}: espectro truncado (se esperaban {n} valores).")
            vals.append(float(lineas[i].split()[0]))
            i += 1
        return np.array(vals), i

    freqs = dirs = matriz = None
    convencion = "cartesiana"
    factor, excepcion = 1.0, -99.0
    i, ntot = 0, len(lineas)
    while i < ntot:
        tokens = lineas[i].split()
        clave = tokens[0] if tokens else ""
        if clave in ("AFREQ", "RFREQ"):
            if i + 1 >= ntot:
                raise ValueError(f"{ruta.name}: encabezado {clave} incompleto.")
            freqs, i = _bloque(i + 2, int(lineas[i + 1].split()[0]))
        elif clave in ("CDIR", "NDIR"):
            convencion = "nautica" if clave == "NDIR" else "cartesiana"
            if i + 1 >= ntot:
                raise ValueError(f"{ruta.name}: encabezado {clave} incompleto.")
            dirs, i = _bloque(i + 2, int(lineas[i + 1].split()[0]))
        elif "exception" in lineas[i]:
            excepcion = float(tokens[0])
            i += 1
        elif clave == "FACTOR":
            if i + 1 >= ntot:
                raise ValueError(f"{ruta.name}: encabezado FACTOR incompleto.")
            if freqs is None or dirs is None:
                raise ValueError(
                    f"{ruta.name}: FACTOR antes de declarar frecuencias/direcciones.")
            factor = float(lineas[i + 1].split()[0])
            i += 2
            if i + len(freqs) > len(lineas):
                raise ValueError(
                    f"{ruta.name}: matriz espectral truncada "
                    f"(faltan filas; se esperaban {len(freqs)}).")
            filas = []
            for r in range(len(freqs)):
                fila = list(map(float, lineas[i + r].split()))
                if len(fila) != len(dirs):
                    raise ValueError(
                        f"{ruta.name}: la fila {r} del espectro tiene {len(fila)} "
                        f"valores; se esperaban {len(dirs)}.")
                filas.append(fila)
            matriz = np.array(filas)
            i += len(freqs)
        else:
            i += 1

    if matriz is None:
        return None
    densidad = matriz * factor * conversion
    densidad[np.isclose(matriz, excepcion)] = np.nan
    ds = xr.Dataset({"Efth": (("freq", "dir"), densidad)},
                    coords={"freq": freqs, "dir": dirs})
    ds["Efth"].attrs = {"long_name": "Densidad de energía", "units": "m2/Hz/rad"}
    ds["freq"].attrs = {"long_name": "Frecuencia", "units": "Hz"}
    ds["dir"].attrs = {"long_name": f"Dirección ({convencion})", "units": "deg",
                       "convencion": convencion}
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
    padre, _ = _dominio_grande_swn(carpeta)

    # Variable de cada salida:
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
        declarados = _mapa_salidas([swn])
        campos = _asignar_campos([(var, ruta) for ruta, var, n in inv
                                  if n == nx * ny and
                                  (ruta.name in declarados if declarados else
                                   ruta.name not in mapa_block)])
        bot = _bot_de_dominio(swn, bots, nx, ny)
        return {"geo": geo, "utm": utm, "campos": campos, "bot": bot,
                "swn": swn, "convencion_dir": _convencion_direccion(swn),
                "titulo": titulos.get(nombre, titulo)}

    dominios = {"large": cfg_de(geos[padre], utm_large, padre, "large",
                                "Dominio grande")}
    i = 1
    for s, g in geos.items():
        if s == padre:
            continue
        utm = _utm_dominio(g, geos[padre], utm_large)
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
    if "Dir" in ds:
        ds["Dir"].attrs["convencion"] = cfg["convencion_dir"]
    ds["x"].attrs.update({"long_name": "Este UTM", "units": "m"})
    ds["y"].attrs.update({"long_name": "Norte UTM", "units": "m"})
    ds.attrs.update({"titulo": cfg["titulo"]})
    return ds


def cargar_corrida(carpeta, utm_large=None, titulos=None):
    """
    Carga una corrida SWAN completa desde su carpeta.

    Parámetros:
      utm_large: offset UTM del nodo (0,0) del dominio grande (otra corrida).
      titulos:   dict opcional {nombre_dominio: título} para rotular los mapas.

    Devuelve un dict con: 'dominios' (Datasets large/n1… disponibles), 'espectro'
    (S(f,θ) si existe) y 'meta' (condición de borde Hs/Tp/Dp + nombre = carpeta).
    """
    carpeta = Path(carpeta)
    if utm_large is None:
        meta_utm = inferir_utm_desde_carpeta(carpeta)
        utm_large = (meta_utm["utm_x"], meta_utm["utm_y"])
        if meta_utm["origen"] == "default":
            print(f"  [aviso] {meta_utm['mensaje']}")
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
    import argparse

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Inspecciona una corrida SWAN estacionaria.")
    ap.add_argument("carpeta", type=Path, help="Carpeta con el caso SWAN")
    CARPETA = ap.parse_args().carpeta
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
