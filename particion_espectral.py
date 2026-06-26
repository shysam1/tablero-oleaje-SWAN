"""
Partición espectral sea/swell por familias (watershed de Hanson & Phillips).

Toma un espectro direccional Efth(freq, dir) —de SWAN o de ERA5— y lo separa en
familias de olas (1 windsea + N swells), reportando Hs/Tp/Dir y el tipo de cada
una. El módulo es agnóstico a la convención de dirección: opera en la que traiga
el espectro de entrada.

Integración por rectángulos (no trapecio) para que la energía de las familias
sume exactamente la del espectro total: cada celda aporta E·dfreq·ddir a la
cuenca a la que el watershed la asigna.
"""

import numpy as np
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
import xarray as xr

G = 9.81   # gravedad [m/s^2]


def _pesos(freqs, dirs):
    """
    Ancho de banda por frecuencia (dfreq, vector) y ancho angular de celda
    (ddir, escalar en radianes). Sirven para integrar el espectro por rectángulos.
    """
    freqs = np.asarray(freqs, float)
    dfreq = np.gradient(freqs)
    ddir = np.deg2rad(np.median(np.abs(np.diff(np.sort(np.asarray(dirs, float))))))
    return dfreq, ddir


def _m0(efth, dfreq, ddir):
    """Momento de orden 0: energía total integrada en frecuencia y dirección."""
    efth = np.nan_to_num(np.asarray(efth, float), nan=0.0)
    return float(np.sum(efth * dfreq[:, None]) * ddir)


def _clasificar(fp, dir_media, viento, f_corte=0.10):
    """
    Clasifica una familia como 'sea' o 'swell'.

    Con viento (u10, v10): criterio de wave age (Hanson & Phillips) — windsea si
    U10·cos(Δθ) > 1.3·c_p en la frecuencia de pico. Sin viento: aproximación por
    frecuencia de pico (sea si fp ≥ f_corte, swell si es más baja).
    """
    if viento is not None:
        u, v = viento
        u10 = float(np.hypot(u, v))
        dir_viento = np.rad2deg(np.arctan2(v, u)) % 360.0
        cp = G / (2.0 * np.pi * fp) if fp > 0 else np.inf
        delta = np.deg2rad(dir_media - dir_viento)
        return "sea" if u10 * np.cos(delta) > 1.3 * cp else "swell"
    return "sea" if fp >= f_corte else "swell"


def _parametros(efth, mascara, freqs, dirs, dfreq, ddir, viento):
    """Parámetros integrados de la familia definida por 'mascara' sobre 'efth'."""
    efth = np.nan_to_num(np.asarray(efth, float), nan=0.0)
    e = np.where(mascara, efth, 0.0)
    m0 = _m0(e, dfreq, ddir)
    hs = 4.0 * np.sqrt(m0)

    energia_por_freq = (e * dfreq[:, None]).sum(axis=1) * ddir
    fp = float(freqs[int(np.argmax(energia_por_freq))])
    tp = 1.0 / fp if fp > 0 else np.nan

    th = np.deg2rad(np.asarray(dirs, float))
    energia_por_dir = (e * dfreq[:, None]).sum(axis=0)
    dx = float(np.sum(energia_por_dir * np.cos(th)))
    dy = float(np.sum(energia_por_dir * np.sin(th)))
    dir_media = np.rad2deg(np.arctan2(dy, dx)) % 360.0

    return {"Hs": hs, "Tp": tp, "Dir": dir_media, "m0": m0,
            "tipo": _clasificar(fp, dir_media, viento), "mascara": mascara}


def particionar(efth, freqs, dirs, viento=None, umbral_rel=0.01):
    """
    Separa un espectro Efth(freq, dir) en familias (1 windsea + N swells).

    Devuelve una lista de dicts (Hs, Tp, Dir, m0, tipo, mascara) ordenada por
    energía descendente. Lista vacía si el espectro no tiene energía.

    El eje de dirección es cíclico: se rota el campo para dejar el valle de
    energía direccional en el borde antes del watershed, de modo que ninguna
    cresta quede partida por la discontinuidad 0/360°.
    'umbral_rel' es la fracción del máximo bajo la cual una celda se descarta
    (0.0 = usar toda la energía; conserva m0 exactamente).
    """
    efth = np.nan_to_num(np.asarray(efth, float), nan=0.0)
    dfreq, ddir = _pesos(freqs, dirs)
    if efth.max() <= 0.0:
        return []

    desfase = int(np.argmin(efth.sum(axis=0)))      # valle direccional → al borde
    campo = np.roll(efth, -desfase, axis=1)

    nivel = umbral_rel * campo.max()
    picos = peak_local_max(campo, min_distance=2, threshold_abs=nivel)
    if len(picos) == 0:
        picos = np.array([np.unravel_index(int(np.argmax(campo)), campo.shape)])

    marcadores = np.zeros(campo.shape, dtype=int)
    for k, (i, j) in enumerate(picos, start=1):
        marcadores[i, j] = k

    etiquetas = watershed(-campo, marcadores, mask=campo > nivel)
    etiquetas = np.roll(etiquetas, desfase, axis=1)   # de vuelta al sistema original

    familias = []
    for k in range(1, int(marcadores.max()) + 1):
        m = etiquetas == k
        if m.any():
            familias.append(_parametros(efth, m, freqs, dirs, dfreq, ddir, viento))
    familias.sort(key=lambda f: f["m0"], reverse=True)
    return familias


def particionar_serie(ds_efth, viento_serie=None, umbral_rel=0.01, max_familias=4):
    """
    Aplica 'particionar' a cada paso de un Dataset con Efth(time, freq, dir).

    Devuelve un Dataset(time, familia) con Hs/Tp/Dir/tipo por familia (rellena con
    NaN los pasos con menos familias). 'viento_serie', si se da, es un dict con
    arrays 'u10' y 'v10' por tiempo, para clasificar sea/swell con wave age.
    """
    freqs = ds_efth["freq"].values
    dirs = ds_efth["dir"].values
    tiempos = ds_efth["time"].values
    nt = len(tiempos)

    hs = np.full((nt, max_familias), np.nan)
    tp = np.full((nt, max_familias), np.nan)
    di = np.full((nt, max_familias), np.nan)
    tipo = np.full((nt, max_familias), "", dtype=object)

    for t in range(nt):
        viento = None
        if viento_serie is not None:
            viento = (float(viento_serie["u10"][t]), float(viento_serie["v10"][t]))
        familias = particionar(ds_efth["Efth"].isel(time=t).values,
                               freqs, dirs, viento=viento, umbral_rel=umbral_rel)
        for k, fam in enumerate(familias[:max_familias]):
            hs[t, k], tp[t, k], di[t, k] = fam["Hs"], fam["Tp"], fam["Dir"]
            tipo[t, k] = fam["tipo"]

    return xr.Dataset(
        {"Hs": (("time", "familia"), hs),
         "Tp": (("time", "familia"), tp),
         "Dir": (("time", "familia"), di),
         "tipo": (("time", "familia"), tipo)},
        coords={"time": tiempos, "familia": np.arange(max_familias)})
