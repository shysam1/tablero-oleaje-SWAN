"""
Animación de corridas SWAN no estacionarias (campos que evolucionan en el tiempo).

Toma la salida de io_swan_nonst (Datasets time, y, x) y genera videos del evento
de marejada: un mapa que se actualiza paso a paso con escala de color GLOBAL fija
(para que los frames sean comparables) y el sello de tiempo de cada instante.

Dos productos:
  - animar_campo: un solo campo sobre un dominio (p. ej. Hs en el Golfo).
  - animar_multipanel: tablero sincronizado (mapa del Golfo + zoom de la bahía +
    serie temporal en un punto con cursor que avanza).

Registro adaptativo: cada panel declara lo que necesita; sólo se dibujan los que
los datos permiten (el anidado no estacionario es numéricamente inestable, así
que sus campos Tp/Dir/Set-up casi siempre faltan y se omiten).

Escritor: MP4 vía ffmpeg si está disponible; si no, GIF con Pillow (sin
dependencias externas).
"""

from pathlib import Path
import shutil
import sys
import warnings

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.gridspec import GridSpec

from io_swan_nonst import cargar_corrida_nonst
import rutas

# Apariencia por variable: mapa de color, mínimo de escala y etiqueta.
ESCALAS = {
    "Hs":    {"cmap": "turbo",   "vmin": 0.0,  "label": "Hs [m]"},
    "Tp":    {"cmap": "viridis", "vmin": 0.0,  "label": "Tp [s]"},
    "Dir":   {"cmap": "twilight", "vmin": 0.0, "label": "Dirección [°]"},
    "Setup": {"cmap": "RdBu_r",  "vmin": None, "label": "Set-up [m]"},
}

# Punto de ejemplo para la serie temporal de la corrida Coronel (boya, UTM
# aprox.). Para otra corrida se pasa otro punto, o se deja la autodetección.
PUNTO_CORONEL = (663494.0, 5898451.0, "Bahía de Coronel (~boya)")


def _hay_datos(da):
    """True si el campo tiene al menos un valor no NaN (registro adaptativo)."""
    return da is not None and bool(da.notnull().any())


def _nido_util(ds, umbral=0.3, min_frac=0.05):
    """
    True si el dominio anidado aporta señal temporal real: Hs por encima de
    `umbral` en al menos una fracción `min_frac` de los frames. Evita dibujar un
    panel casi siempre vacío cuando el nido es numéricamente inestable (como el
    no estacionario de Coronel, con oleaje sólo en el primer paso).
    """
    if ds is None or "Hs" not in ds:
        return False
    with np.errstate(invalid="ignore"):
        maxf = ds["Hs"].max(("y", "x")).values
    con_senal = int(np.nansum(maxf > umbral))
    return con_senal >= max(2, min_frac * len(maxf))


def _escala(da, vmin):
    """Escala de color global fija sobre todo el evento (vmin dado, vmax → arriba)."""
    if vmin is None:                       # campos con signo (set-up): simétrico
        m = float(np.nanmax(np.abs(da.values)))
        m = np.ceil(m * 10) / 10 if m > 0 else 1.0
        return -m, m
    vmax = float(np.nanmax(da.values))
    return vmin, np.ceil(vmax) if vmax > 1 else np.ceil(vmax * 10) / 10


def _componentes_dir(dir_deg):
    """Vectores unitarios de la dirección (misma convención que el MATLAB del curso)."""
    d = np.where(dir_deg >= 180, dir_deg - 360, dir_deg)
    return np.cos(np.deg2rad(d)), np.sin(np.deg2rad(d))


def _fecha_txt(t):
    """datetime64 → 'dd-mm-YYYY HH:MM' legible."""
    return np.datetime_as_string(t, unit="m").replace("T", "  ")


def _dibujar_mapa(ax, ds, var, escala, con_dir=False, paso_q=3):
    """
    Dibuja el primer frame de un campo y devuelve los artistas a actualizar:
    (quadmesh, quiver|None). Pinta también la línea de costa con la batimetría.
    """
    vmin, vmax = escala
    cfg = ESCALAS[var]
    campo0 = ds[var].isel(time=0)
    qm = ax.pcolormesh(ds["x"], ds["y"], campo0, cmap=cfg["cmap"],
                       vmin=vmin, vmax=vmax, shading="nearest")
    if "depth" in ds:                      # contorno de costa (profundidad 0)
        ax.contour(ds["x"], ds["y"], ds["depth"], levels=[0],
                   colors="k", linewidths=0.6)
    qv = None
    if con_dir and _hay_datos(ds.get("Dir")):
        u0, v0 = _componentes_dir(ds["Dir"].isel(time=0).values)
        xs, ys = ds["x"].values[::paso_q], ds["y"].values[::paso_q]
        qv = ax.quiver(xs, ys, u0[::paso_q, ::paso_q], v0[::paso_q, ::paso_q],
                       color=[0.25, 0.25, 0.25], scale=28, width=0.004)
    ax.set_aspect("equal")
    ax.set_xlabel("Este UTM [m]")
    ax.set_ylabel("Norte UTM [m]")
    return qm, qv


def _serie_en_punto(da, x_utm, y_utm):
    """Serie temporal en el punto de agua más cercano a (x_utm, y_utm)."""
    p = da.sel(x=x_utm, y=y_utm, method="nearest")
    if bool(p.notnull().any()):
        return p
    # Fallback: celda válida (no NaN en todo el evento) más próxima al punto.
    valido = da.notnull().all("time")
    xx, yy = np.meshgrid(da["x"].values, da["y"].values)
    dist = np.hypot(xx - x_utm, yy - y_utm)
    dist[~valido.values] = np.inf
    j, i = np.unravel_index(np.argmin(dist), dist.shape)
    return da.isel(y=j, x=i)


def _punto_auto(da):
    """
    Elige automáticamente un punto representativo para la serie temporal: la
    celda con mayor variabilidad de Hs durante el evento (donde más se nota el
    temporal), entre las celdas con dato en todo el período.
    """
    valido = da.notnull().all("time")
    # std sobre celdas de tierra (todo NaN) avisa "ddof<=0"; es inocuo porque
    # esas celdas se descartan con .where(valido).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        var = da.std("time", skipna=True).where(valido).values
        if not np.isfinite(var).any():     # sin celdas siempre-válidas
            var = da.mean("time", skipna=True).values
        j, i = np.unravel_index(np.nanargmax(var), var.shape)
    return float(da["x"].values[i]), float(da["y"].values[j]), "punto de control"


def _writer(formato, fps):
    """Elige escritor: MP4 (ffmpeg) o GIF (Pillow). 'auto' prefiere MP4."""
    ff = shutil.which("ffmpeg")
    if ff:
        plt.rcParams["animation.ffmpeg_path"] = ff
    quiere_mp4 = formato in ("auto", "mp4")
    if quiere_mp4 and animation.FFMpegWriter.isAvailable():
        return animation.FFMpegWriter(fps=fps, bitrate=2400), ".mp4"
    if formato == "mp4":
        print("  [aviso] ffmpeg no disponible; se usará GIF.")
    return animation.PillowWriter(fps=fps), ".gif"


def animar_campo(corrida, var="Hs", dominio="large", salida=None,
                 fps=12, formato="auto", paso=1, progreso=None):
    """Anima un solo campo sobre un dominio. Devuelve la ruta del archivo."""
    ds = corrida["dominios"][dominio].isel(time=slice(None, None, paso))
    if not _hay_datos(ds.get(var)):
        raise ValueError(f"{var} en {dominio} no tiene datos válidos para animar")
    escala = _escala(ds[var], ESCALAS[var]["vmin"])
    con_dir = var == "Hs"

    fig, ax = plt.subplots(figsize=(6.4, 7.2))
    qm, qv = _dibujar_mapa(ax, ds, var, escala, con_dir=con_dir)
    cb = fig.colorbar(qm, ax=ax)
    cb.set_label(ESCALAS[var]["label"])
    sup = fig.suptitle("", fontsize=12)
    tiempos = ds["time"].values

    def actualizar(i):
        qm.set_array(ds[var].isel(time=i).values.ravel())
        if qv is not None:
            u, v = _componentes_dir(ds["Dir"].isel(time=i).values)
            qv.set_UVC(u[::3, ::3], v[::3, ::3])
        sup.set_text(f"{ds.attrs.get('titulo', dominio)} — {var}\n"
                     f"{_fecha_txt(tiempos[i])}")
        return [qm]

    anim = animation.FuncAnimation(fig, actualizar, frames=ds.sizes["time"],
                                   interval=1000 / fps, blit=False)
    return _guardar(anim, fig, salida, formato, fps,
                    defecto=f"video_{var}_{dominio}", progreso=progreso)


def animar_multipanel(corrida, salida=None, fps=12, formato="auto", paso=1,
                      punto=None, progreso=None):
    """
    Tablero sincronizado del evento. Paneles (sólo los que los datos permiten):
      - mapa Hs del dominio grande con dirección (principal),
      - mapa Hs del dominio anidado, si tiene datos (escala propia),
      - serie temporal de Hs en un punto con cursor del instante.

    punto: (x_utm, y_utm, nombre) para la serie; si es None, se autodetecta el
    punto de mayor variabilidad de Hs (genérico para cualquier corrida).
    """
    dom = corrida["dominios"]
    large = dom["large"].isel(time=slice(None, None, paso))
    n1 = dom.get("n1")
    if n1 is not None:
        n1 = n1.isel(time=slice(None, None, paso))
    hay_n1 = n1 is not None and _nido_util(n1)

    esc_large = _escala(large["Hs"], 0.0)
    tiempos = large["time"].values

    # Serie temporal de Hs (del dominio grande, robusto). Punto dado o autodetectado.
    if punto is None:
        punto = _punto_auto(large["Hs"])
    xs, ys, nombre_pto = punto
    serie = _serie_en_punto(large["Hs"], xs, ys)

    fig = plt.figure(figsize=(12.5, 7.6))
    gs = GridSpec(2, 2, width_ratios=[1.35, 1.0], height_ratios=[1.0, 0.65],
                  figure=fig, hspace=0.28, wspace=0.22)
    ax_g = fig.add_subplot(gs[:, 0])               # mapa principal (2 filas)
    # Si el nido aporta, va arriba a la derecha y la serie abajo; si no, se omite
    # y la serie temporal ocupa todo el lado derecho.
    ax_n = fig.add_subplot(gs[0, 1]) if hay_n1 else None
    ax_s = fig.add_subplot(gs[1, 1] if hay_n1 else gs[:, 1])  # serie temporal

    # Panel principal: Hs Golfo + dirección.
    qm_g, qv_g = _dibujar_mapa(ax_g, large, "Hs", esc_large, con_dir=True, paso_q=3)
    ax_g.set_title(large.attrs.get("titulo", "Golfo de Arauco"), fontsize=11)
    cb = fig.colorbar(qm_g, ax=ax_g, fraction=0.046, pad=0.02)
    cb.set_label("Hs [m]")

    # Panel anidado: Hs con su PROPIA escala global (su Hs máx ≪ el del Golfo,
    # así el detalle de la bahía es legible en vez de quedar saturado en azul).
    qm_n = None
    if ax_n is not None:
        esc_n1 = _escala(n1["Hs"], 0.0)
        qm_n, _ = _dibujar_mapa(ax_n, n1, "Hs", esc_n1, con_dir=False)
        ax_n.set_title(n1.attrs.get("titulo", "Dominio anidado"), fontsize=10)
        ax_n.tick_params(labelsize=8)
        cbn = fig.colorbar(qm_n, ax=ax_n, fraction=0.046, pad=0.02)
        cbn.set_label("Hs [m]", fontsize=8)
        cbn.ax.tick_params(labelsize=7)

    # Panel serie temporal con cursor.
    ax_s.plot(tiempos, serie.values, color="#1f4e79", lw=1.4)
    ax_s.set_title(f"Hs en {nombre_pto}", fontsize=10)
    ax_s.set_ylabel("Hs [m]")
    ax_s.set_xlabel("Fecha")
    ax_s.grid(alpha=0.3)
    ax_s.tick_params(axis="x", labelrotation=20, labelsize=8)
    cursor = ax_s.axvline(tiempos[0], color="crimson", lw=1.3)
    marca, = ax_s.plot([tiempos[0]], [float(serie.isel(time=0))],
                       "o", color="crimson", ms=6)

    sup = fig.suptitle("", fontsize=13, y=0.99)

    def actualizar(i):
        qm_g.set_array(large["Hs"].isel(time=i).values.ravel())
        # La flecha de dirección sólo existe si el dominio grande trae Dir con
        # datos válidos (_dibujar_mapa devuelve qv_g=None si no). Sin esta guarda,
        # actualizar el quiver inexistente reventaba la animación.
        if qv_g is not None:
            u, v = _componentes_dir(large["Dir"].isel(time=i).values)
            qv_g.set_UVC(u[::3, ::3], v[::3, ::3])
        if qm_n is not None:
            qm_n.set_array(n1["Hs"].isel(time=i).values.ravel())
        cursor.set_xdata([tiempos[i], tiempos[i]])
        marca.set_data([tiempos[i]], [float(serie.isel(time=i))])
        sup.set_text(f"Evento de marejada — {_fecha_txt(tiempos[i])}")
        return [qm_g]

    anim = animation.FuncAnimation(fig, actualizar, frames=large.sizes["time"],
                                   interval=1000 / fps, blit=False)
    return _guardar(anim, fig, salida, formato, fps, defecto="video_multipanel",
                    progreso=progreso)


def _dibujar_espectro_polar(ax, esp, t_idx, vmax):
    """Dibuja S(f,θ) en ejes polares (θ cartesiana SWAN, r = frecuencia)."""
    th = np.deg2rad(esp["dir"].values)
    r = esp["freq"].values
    TH, R = np.meshgrid(th, r)             # (nfreq, ndir)
    C = esp["Efth"].isel(time=t_idx).values
    pcm = ax.pcolormesh(TH, R, C, cmap="turbo", vmin=0, vmax=vmax, shading="auto")
    ax.set_rlabel_position(135)
    ax.set_xlabel("Dirección (cartesiana) [°] · radio = frecuencia [Hz]", fontsize=9)
    return pcm


def animar_espectro(corrida, salida=None, fps=12, formato="auto", progreso=None):
    """
    Anima el espectro 2D S(f,θ) del punto a lo largo del evento, con escala de
    color global fija. Si sólo un paso tiene energía (los demás ZERO/NODATA, como
    en el nido inestable de Coronel), animar no aporta: genera una figura polar
    estática de ese espectro. Devuelve la ruta (video o PNG), o None si no hay
    espectro / no hay energía en ningún paso.
    """
    esp = corrida.get("espectro")
    if esp is None:
        return None
    with np.errstate(invalid="ignore"):
        etot = esp["Efth"].sum(("freq", "dir"), skipna=True).values
    idx = np.where(etot > 0)[0]
    if idx.size == 0:
        print("  [espectro] sin energía en ningún paso; se omite")
        return None
    vmax = float(np.nanmax(esp["Efth"].values))

    # Radio útil: recorta el anillo de altas frecuencias sin energía.
    with np.errstate(invalid="ignore"):
        e_freq = esp["Efth"].isel(time=idx).sum("dir").max("time").values
    sig = e_freq > 0.01 * np.nanmax(e_freq)
    rmax = float(esp["freq"].values[sig].max()) * 1.4 if sig.any() \
        else float(esp["freq"].max())

    def _decorar(fig, ax, pcm, i):
        ax.set_rmax(rmax)
        cb = fig.colorbar(pcm, ax=ax, pad=0.1, fraction=0.046)
        cb.set_label("Densidad de energía [m²/Hz/°]")
        fecha = _fecha_txt(esp["time"].values[i])
        fig.suptitle(f"Espectro S(f,θ) en el punto\n{fecha}", fontsize=12)

    if idx.size < 2:                       # un solo paso con energía → estático
        i = int(idx[0])
        fig = plt.figure(figsize=(6.6, 6.6))
        ax = fig.add_subplot(111, projection="polar")
        pcm = _dibujar_espectro_polar(ax, esp, i, vmax)
        _decorar(fig, ax, pcm, i)
        if salida is None:
            salida = Path.cwd() / "espectro_punto"
        salida = Path(salida).with_suffix(".png")
        salida.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(salida, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  [espectro] sólo 1 paso con energía → figura estática "
              f"{salida.name}")
        return salida

    # ≥2 pasos con energía: animación recortada al tramo activo.
    i0, i1 = int(idx[0]), int(idx[-1])
    sub = esp.isel(time=slice(i0, i1 + 1))
    fig = plt.figure(figsize=(6.6, 6.6))
    ax = fig.add_subplot(111, projection="polar")
    pcm = _dibujar_espectro_polar(ax, sub, 0, vmax)
    ax.set_rmax(rmax)
    cb = fig.colorbar(pcm, ax=ax, pad=0.1, fraction=0.046)
    cb.set_label("Densidad de energía [m²/Hz/°]")
    sup = fig.suptitle("", fontsize=12)
    tiempos = sub["time"].values

    def actualizar(k):
        pcm.set_array(sub["Efth"].isel(time=k).values.ravel())
        sup.set_text(f"Espectro S(f,θ) en el punto\n{_fecha_txt(tiempos[k])}")
        return [pcm]

    anim = animation.FuncAnimation(fig, actualizar, frames=sub.sizes["time"],
                                   interval=1000 / fps, blit=False)
    return _guardar(anim, fig, salida, formato, fps, defecto="video_espectro",
                    progreso=progreso)


def _guardar(anim, fig, salida, formato, fps, defecto, progreso=None):
    """Guarda la animación eligiendo escritor y extensión; cierra la figura.
    progreso: callback(frame_actual, total) para reportar avance (GUI)."""
    writer, ext = _writer(formato, fps)
    if salida is None:
        salida = Path.cwd() / defecto
    salida = Path(salida)
    if salida.suffix.lower() not in (".mp4", ".gif"):
        salida = salida.with_suffix(ext)
    salida.parent.mkdir(parents=True, exist_ok=True)
    anim.save(salida, writer=writer, dpi=130, progress_callback=progreso)
    plt.close(fig)
    return salida


def generar_videos(carpeta, salida_dir=None, fps=12, formato="auto", paso=1,
                   multipanel=True, campos=None, utm_large=None, titulos=None,
                   punto=None, progreso=None, espectro=True):
    """
    Orquestador: carga la corrida y genera el/los video(s) disponibles.

    multipanel=True → tablero sincronizado (producto principal).
    campos   → lista de (var, dominio) para videos por-campo adicionales.
    utm_large→ offset UTM del dominio grande (otra corrida ≠ Coronel).
    titulos  → rótulos por dominio; punto → (x,y,nombre) de la serie temporal.
    Devuelve la lista de rutas generadas.
    """
    carpeta = Path(carpeta)
    salida_dir = Path(salida_dir) if salida_dir else rutas.carpeta_salida(carpeta.name)
    kw = {} if utm_large is None else {"utm_large": utm_large}
    corrida = cargar_corrida_nonst(carpeta, titulos=titulos, **kw)
    generados = []

    if multipanel:
        ruta = animar_multipanel(corrida, salida=salida_dir / "video_multipanel",
                                 fps=fps, formato=formato, paso=paso, punto=punto,
                                 progreso=progreso)
        print(f"  multipanel -> {ruta.name}")
        generados.append(ruta)

    for var, dominio in (campos or []):
        ds = corrida["dominios"].get(dominio)
        if ds is None or not _hay_datos(ds.get(var)):
            print(f"  [omitido] {var} en {dominio}: sin datos válidos")
            continue
        ruta = animar_campo(corrida, var=var, dominio=dominio,
                            salida=salida_dir / f"video_{var}_{dominio}",
                            fps=fps, formato=formato, paso=paso)
        print(f"  {var}/{dominio} -> {ruta.name}")
        generados.append(ruta)

    if espectro:
        ruta = animar_espectro(corrida, salida=salida_dir / "espectro_punto",
                               fps=fps, formato=formato, progreso=progreso)
        if ruta is not None:
            generados.append(ruta)
    return generados


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

    print("Generando videos del evento no estacionario...")
    rutas = generar_videos(CARPETA, fps=12, formato="auto",
                           campos=[("Hs", "large")],
                           titulos=TITULOS, punto=PUNTO_CORONEL)
    print("Listo:")
    for r in rutas:
        print("  ", r)
