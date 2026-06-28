"""
Carga de corridas SWAN NO estacionarias (campos espaciales que evolucionan en
el tiempo) a Datasets de xarray.

A diferencia de io_swan (un campo 2D por condición, p. ej. TR100), aquí cada
variable física está guardada como N matrices timestamped dentro de un único
`.mat` (`<Prefijo>_YYYYMMDD_HHMMSS`), una por paso de tiempo del evento. Este
módulo las apila en un DataArray (time, y, x) con coordenada temporal real,
listo para animar.

El módulo es GENÉRICO: autodetecta los dominios y campos de cualquier carpeta de
corrida no estacionaria (no sólo el caso Coronel). Para ello:
  - clasifica los .swn por su comando CGRID: el de origen local (0,0) es el
    dominio padre (grande); los de origen ≠ 0 son anidados;
  - asigna cada .mat y .bot al dominio cuyo tamaño de malla coincide con el del
    campo (no depende del nombre del archivo);
  - reconoce las variables por el prefijo del nombre (Hsig→Hs, TPsmoo→Tp, …).

Lo único que no vive en los archivos SWAN es el offset UTM absoluto del dominio
grande (sus mallas trabajan en coordenadas locales): se pasa como parámetro
`utm_large` (por defecto, el de la corrida Coronel del usuario).

Replica la convención de los scripts MATLAB del usuario: orientación por
`flipud`, relleno de excepciones a NaN. Reutiliza las tablas de relleno y de
atributos de io_swan para mantenerse sincronizado con lo ya validado.
"""

from pathlib import Path
from datetime import datetime
import re
import sys

import numpy as np
import scipy.io as sio
import xarray as xr

from io_swan import EXCEPCION, ATRIBUTOS

# Offset UTM del nodo (0,0) del dominio grande. Sin valor por defecto distinto,
# este es el de la corrida Coronel; para otra corrida se pasa a cargar_corrida.
UTM_LARGE_DEFAULT = (620494.0, 5876451.0)

# Prefijo del nombre de variable en los .mat de SWAN → variable física.
PREFIJO_VAR = {"Hsig": "Hs", "TPsmoo": "Tp", "Dir": "Dir", "Setup": "Setup"}

# Patrón del sello de tiempo al final del nombre de variable: ..._YYYYMMDD_HHMMSS
_PATRON_TS = re.compile(r"_(\d{8})_(\d{6})$")

# Sello de tiempo de los bloques del espectro SWAN: YYYYMMDD.HHMMSS
_PATRON_TS_ESPEC = re.compile(r"\s*(\d{8})\.(\d{6})")


def _leer_cgrid(ruta_swn):
    """
    Extrae la geometría de malla del comando CGRID de un .swn, incluyendo el
    origen LOCAL (xpc, ypc) necesario para ubicar un dominio anidado.
    """
    for linea in Path(ruta_swn).read_text().splitlines():
        partes = linea.split()
        if partes and partes[0].upper() == "CGRID":
            # CGRID xpc ypc alpc xlenc ylenc mxc myc … → se necesitan 8 tokens.
            if len(partes) < 8:
                raise ValueError(
                    f"CGRID incompleto en {Path(ruta_swn).name}: {linea.strip()!r}")
            x0, y0 = float(partes[1]), float(partes[2])
            xlenc, ylenc = float(partes[4]), float(partes[5])
            mxc, myc = int(partes[6]), int(partes[7])
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


def _orientar(mat, excepcion):
    """
    Lleva una matriz cruda del .mat a la orientación geográfica y aplica el
    relleno a NaN, con la misma convención que MATLAB (`flipud`) y io_swan.
    """
    # Los .mat ya traen NaN en las celdas de tierra; el cast y las comparaciones
    # sobre esos NaN son esperados, no un error numérico, de ahí el errstate.
    with np.errstate(invalid="ignore"):
        campo = np.flipud(np.asarray(mat, dtype=float))
        if excepcion is None:
            campo[campo < 0] = np.nan      # Hs: cualquier negativo es relleno
        else:
            campo[np.isclose(campo, excepcion)] = np.nan
    return campo


def _parse_ts(nombre):
    """Convierte '<Prefijo>_YYYYMMDD_HHMMSS' en datetime, o None si no calza."""
    m = _PATRON_TS.search(nombre)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")


def leer_mat_temporal(ruta_mat, nx, ny, excepcion):
    """
    Apila las variables timestamped de un .mat en un cubo (nt, ny, nx).

    Devuelve (tiempos, cubo): los tiempos como lista de datetime ordenada y el
    cubo numpy ya orientado (flipud) y con NaN en los rellenos. El prefijo del
    nombre es irrelevante para el orden: éste se fija por el sello de tiempo.
    """
    mat = sio.loadmat(ruta_mat)
    entradas = []
    for nombre, arr in mat.items():
        if nombre.startswith("__"):
            continue
        ts = _parse_ts(nombre)
        if ts is not None:
            entradas.append((ts, arr))
    if not entradas:
        raise ValueError(f"{Path(ruta_mat).name}: sin variables timestamped")

    entradas.sort(key=lambda e: e[0])
    forma = np.asarray(entradas[0][1]).shape
    if forma != (ny, nx):
        raise ValueError(f"{Path(ruta_mat).name}: campos {forma}; "
                         f"se esperaban ({ny}, {nx})")

    tiempos = [ts for ts, _ in entradas]
    cubo = np.stack([_orientar(arr, excepcion) for _, arr in entradas])
    return tiempos, cubo


def leer_espectro_temporal(ruta):
    """
    Lee un espectro 2D de SWAN dependiente del tiempo (SPEC2D, comando TIME) y
    devuelve un Dataset S(time, freq, dir).

    El archivo es ASCII SWAN (cabecera 'SWAN 1'), no un .mat de MATLAB, aunque a
    veces lleve esa extensión. Encabezado con AFREQ/CDIR/QUANT; luego, por cada
    fecha (`YYYYMMDD.HHMMSS`), un bloque FACTOR+matriz (densidad = entero×factor),
    o ZERO (sin energía) o NODATA (sin dato). Devuelve None si no existe.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    lineas = ruta.read_text().splitlines()
    if not lineas or not lineas[0].upper().startswith("SWAN"):
        return None

    def _vals(i, n):                       # lee n valores escalares desde la línea i
        out = []
        while len(out) < n:
            if i >= len(lineas):
                raise ValueError(
                    f"{ruta.name}: espectro truncado (se esperaban {n} valores).")
            out.append(float(lineas[i].split()[0]))
            i += 1
        return np.array(out), i

    # --- Encabezado: frecuencias, direcciones y valor de excepción ---
    freqs = dirs = None
    excepcion = -99.0
    i = 0
    while i < len(lineas):
        clave = lineas[i].split()[0] if lineas[i].split() else ""
        if clave in ("AFREQ", "RFREQ"):
            if i + 1 >= len(lineas):
                raise ValueError(f"{ruta.name}: encabezado {clave} incompleto.")
            freqs, i = _vals(i + 2, int(lineas[i + 1].split()[0]))
        elif clave in ("CDIR", "NDIR"):
            if i + 1 >= len(lineas):
                raise ValueError(f"{ruta.name}: encabezado {clave} incompleto.")
            dirs, i = _vals(i + 2, int(lineas[i + 1].split()[0]))
        elif "exception value" in lineas[i]:
            excepcion = float(lineas[i].split()[0])
            i += 1
        elif _PATRON_TS_ESPEC.match(lineas[i]):
            break                          # empieza la serie temporal
        else:
            i += 1

    if freqs is None or dirs is None:
        # Sin AFREQ/CDIR no se puede dimensionar la matriz: archivo no es un
        # SPEC2D válido (o está truncado en el encabezado).
        return None
    nf, nd = len(freqs), len(dirs)
    tiempos, cubos = [], []
    while i < len(lineas):
        m = _PATRON_TS_ESPEC.match(lineas[i])
        if not m:
            i += 1
            continue
        tiempos.append(datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
        etiqueta = lineas[i + 1].strip() if i + 1 < len(lineas) else ""
        if etiqueta == "FACTOR":
            factor = float(lineas[i + 2].split()[0])
            base = i + 3
            if base + nf > len(lineas):
                raise ValueError(
                    f"{ruta.name}: matriz espectral truncada en {m.group(1)}."
                    f"{m.group(2)} (faltan filas; se esperaban {nf}).")
            filas = []
            for r in range(nf):
                fila = list(map(float, lineas[base + r].split()))
                if len(fila) != nd:
                    raise ValueError(
                        f"{ruta.name}: fila {r} del espectro tiene {len(fila)} "
                        f"valores; se esperaban {nd}.")
                filas.append(fila)
            mat = np.array(filas)
            with np.errstate(invalid="ignore"):
                dens = mat * factor
                dens[np.isclose(mat, excepcion)] = np.nan
            cubos.append(dens)
            i = base + nf
        elif etiqueta == "ZERO":
            cubos.append(np.zeros((nf, nd)))
            i += 2
        else:                              # NODATA u otra: sin dato
            cubos.append(np.full((nf, nd), np.nan))
            i += 2

    if not cubos:
        raise ValueError(f"{ruta.name}: no contiene bloques temporales de espectro.")
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), np.stack(cubos))},
        coords={"time": np.array(tiempos, dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    ds["Efth"].attrs = {"long_name": "Densidad de energía", "units": "m2/Hz/deg"}
    ds["freq"].attrs = {"long_name": "Frecuencia", "units": "Hz"}
    ds["dir"].attrs = {"long_name": "Dirección (cartesiana)", "units": "deg"}
    return ds


def es_corrida_nonst(carpeta):
    """
    True si la carpeta es una corrida SWAN NO estacionaria: tiene un .swn con
    sufijo NonSt, o algún .mat con variables timestamped (campos por paso).
    Sirve para que la GUI distinga el modo video del modo mapa estacionario.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return False
    if any(carpeta.glob("*NonSt.swn")):
        return True
    for ruta in carpeta.glob("*.mat"):
        try:
            info = sio.whosmat(str(ruta))
        except Exception:
            continue
        if info and _PATRON_TS.search(info[0][0]):
            return True
    return False


def _inventario_mat(carpeta):
    """
    Inventaría los .mat de la carpeta sin cargarlos enteros (usa whosmat).

    Devuelve una lista de (ruta, variable, (ny, nx)). Los .mat en formato MATLAB
    v7.3 (p. ej. Espectro_Punto.mat) no los abre scipy y se omiten.
    """
    items = []
    for ruta in sorted(carpeta.glob("*.mat")):
        try:
            info = sio.whosmat(str(ruta))
        except Exception:
            continue                       # v7.3 u otro formato: diferido
        if not info:
            continue
        nombre0, shape, _ = info[0]
        var = PREFIJO_VAR.get(_PATRON_TS.sub("", nombre0))
        if var and len(shape) == 2:
            items.append((ruta, var, tuple(shape)))
    return items


def _asignar_campos(candidatos):
    """
    De una lista de (variable, ruta) ya filtrada por tamaño de malla, asigna una
    sola ruta por variable. Si hay varios .mat para la misma variable (corrida
    repetida con archivos viejos sin borrar), antes ganaba el último en silencio;
    ahora se avisa y se conserva el MÁS RECIENTE, para no apilar una serie
    temporal obsoleta sin que el usuario lo sepa.
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
    Autodetecta los dominios de la corrida desde los .swn y reparte los .mat/.bot
    por tamaño de malla. Devuelve {nombre: cfg} con geo, utm, campos y bot.
    """
    swns = sorted(carpeta.glob("*.swn"))
    if not swns:
        raise ValueError(f"No hay .swn en {carpeta}")
    geos = {s: _leer_cgrid(s) for s in swns}

    # Dominio padre: origen local (0,0); si ninguno, el de mayor malla.
    padres = [s for s, g in geos.items()
              if g["x0_local"] == 0 and g["y0_local"] == 0]
    padre = padres[0] if padres else max(geos, key=lambda s: geos[s]["nx"] * geos[s]["ny"])

    inv = _inventario_mat(carpeta)
    bots = list(carpeta.glob("*.bot"))

    def cfg_de(geo, utm, nombre, titulo):
        ny, nx = geo["ny"], geo["nx"]
        campos = _asignar_campos([(var, ruta) for ruta, var, forma in inv
                                  if forma == (ny, nx)])
        bot = next((b for b in bots
                    if len(Path(b).read_text().split()) == nx * ny), None)
        return {"geo": geo, "utm": utm, "campos": campos, "bot": bot,
                "titulo": titulos.get(nombre, titulo)}

    dominios = {"large": cfg_de(geos[padre], utm_large, "large",
                                "Dominio grande")}
    i = 1
    for s, g in geos.items():
        if s == padre:
            continue
        utm = (utm_large[0] + g["x0_local"], utm_large[1] + g["y0_local"])
        nombre = f"n{i}"
        dominios[nombre] = cfg_de(g, utm, nombre, f"Dominio anidado {nombre}")
        i += 1
    return dominios


def _construir_dataset(cfg):
    """Arma el Dataset (time, y, x) en UTM de un dominio a partir de su cfg."""
    geo, (x0, y0) = cfg["geo"], cfg["utm"]
    nx, ny = geo["nx"], geo["ny"]
    x = x0 + np.arange(nx) * geo["dx"]
    y = y0 + np.arange(ny) * geo["dy"]

    # Registro adaptativo: se carga cada campo disponible; el anidado inestable
    # puede traer campos enteramente NaN, que se conservan y se reportan.
    data_vars, tiempos_ref = {}, None
    for var, ruta in cfg["campos"].items():
        tiempos, cubo = leer_mat_temporal(ruta, nx, ny, EXCEPCION[var])
        if tiempos_ref is None:
            tiempos_ref = tiempos
        elif tiempos != tiempos_ref:
            raise ValueError(f"{Path(ruta).name}: eje temporal distinto al "
                             f"de los demás campos del dominio")
        data_vars[var] = (("time", "y", "x"), cubo)

    # Batimetría: campo estático del input grid (sin dimensión temporal).
    if cfg["bot"] is not None:
        bat = np.array(Path(cfg["bot"]).read_text().split(), dtype=float)
        if bat.size == nx * ny:
            data_vars["depth"] = (("y", "x"), np.flipud(bat.reshape(ny, nx)))

    coords = {"x": x, "y": y}
    if tiempos_ref is not None:
        coords["time"] = np.array(tiempos_ref, dtype="datetime64[ns]")

    ds = xr.Dataset(data_vars, coords=coords)
    for v in ds.data_vars:
        ds[v].attrs.update(ATRIBUTOS.get(v, {}))
    ds["x"].attrs.update({"long_name": "Este UTM", "units": "m"})
    ds["y"].attrs.update({"long_name": "Norte UTM", "units": "m"})
    if "time" in ds.coords:
        ds["time"].attrs.update({"long_name": "Tiempo"})
    ds.attrs.update({"titulo": cfg["titulo"]})
    return ds


def cargar_corrida_nonst(carpeta, utm_large=UTM_LARGE_DEFAULT, titulos=None):
    """
    Carga una corrida SWAN no estacionaria completa desde su carpeta.

    Parámetros:
      utm_large: offset UTM del nodo (0,0) del dominio grande. Por defecto el de
                 la corrida Coronel; cámbialo para otra corrida.
      titulos:   dict opcional {nombre_dominio: título} para rotular los mapas.

    Devuelve un dict con 'dominios' (Datasets time,y,x, con su nombre) y 'meta'
    (rango temporal y número de pasos del evento).
    """
    carpeta = Path(carpeta)
    cfgs = _detectar_dominios(carpeta, utm_large, titulos or {})
    dominios = {nombre: _construir_dataset(cfg)
                for nombre, cfg in cfgs.items() if cfg.get("campos")}

    meta = {"condicion": carpeta.name}
    for ds in dominios.values():
        if "time" in ds.coords:
            t = ds["time"].values
            meta.update({"t_inicio": t[0], "t_fin": t[-1], "nt": int(t.size)})
            break
    for ds in dominios.values():
        ds.attrs.update(meta)

    # Espectro 2D temporal: archivo SWAN ASCII (cabecera 'SWAN'), puede venir con
    # extensión .mat. Se busca por nombre y se valida por cabecera.
    espectro = None
    for ruta in carpeta.glob("*spectro*"):
        espectro = leer_espectro_temporal(ruta)
        if espectro is not None:
            break

    return {"dominios": dominios, "espectro": espectro, "meta": meta}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    CARPETA = Path(
        r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python"
        r"\SWAN_Coronel\no_estacionario")
    TITULOS = {"large": "Dominio grande (Golfo de Arauco)",
               "n1": "Dominio anidado N1 (Bahía de Coronel)"}

    corrida = cargar_corrida_nonst(CARPETA, titulos=TITULOS)
    meta = corrida["meta"]
    print("Evento:", meta["condicion"])
    print(f"  {meta['nt']} pasos  |  {meta['t_inicio']}  ->  {meta['t_fin']}")

    for nombre, ds in corrida["dominios"].items():
        print("=" * 60)
        print(f"{nombre}  ({ds.attrs['titulo']})  ->  {dict(ds.sizes)}")
        if "time" in ds.coords:
            t = ds["time"].values
            dt_h = np.diff(t).astype("timedelta64[m]").astype(float) / 60.0
            print(f"  time monótona: {bool(np.all(np.diff(t) > np.timedelta64(0)))}"
                  f"  |  paso medio: {dt_h.mean():.2f} h")
        for v in ds.data_vars:
            da = ds[v]
            nan_pct = 100.0 * float(da.isnull().mean())
            with np.errstate(all="ignore"):
                vmin, vmax = float(da.min()), float(da.max())
            print(f"  {v:6s} min={vmin:8.3f}  max={vmax:8.3f}  NaN={nan_pct:5.1f}%")
