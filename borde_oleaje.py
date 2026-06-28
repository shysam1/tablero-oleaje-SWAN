"""
Deriva una condición de borde SWAN (Hs, Tp, Dir) a partir de una serie de oleaje
(ERA5 o .mat/.csv/.nc propio). Tres modos: periodo de retorno (Gumbel), máximo
observado y oleaje reinante. Motor puro: recibe un Dataset(time) con Hs (y, según
el modo, Tp/Dir) y devuelve un dict, sin tocar la GUI.

El Dir se entrega en la misma convención de la serie (náutica: de dónde viene el
oleaje); el .swn generado por swan_builder emite SET NAUTICAL para interpretarlo
igual.
"""

import math

import numpy as np
from scipy import stats

import productos


def _float_finito(val):
    """Convierte a float o None si el valor no es finito."""
    if val is None:
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _indice_peak(ds):
    """Índice temporal del mayor Hs de la serie."""
    hs = ds["Hs"]
    if hs.isnull().all():
        raise ValueError("No hay Hs válidos para localizar el pico.")
    return int(hs.fillna(-np.inf).argmax("time"))


def _tp_dir_en(ds, i):
    """Tp y Dir en el paso i (None si la variable no está o el valor no es finito)."""
    per = _float_finito(ds["Tp"].isel(time=i)) if "Tp" in ds.data_vars else None
    dirr = _float_finito(ds["Dir"].isel(time=i)) if "Dir" in ds.data_vars else None
    return per, dirr


def condicion_borde(ds, modo, periodo_retorno=100):
    """
    Devuelve {hs, per, dir, descripcion} para el borde SWAN.

    modo 'maximo': Hs/Tp/Dir del instante de mayor Hs.
    modo 'retorno': Hs de periodo de retorno por ajuste Gumbel; Tp/Dir del peak.
    modo 'reinante': mediana de Hs/Tp + sector direccional dominante.
    Las claves per/dir valen None si la serie no trae esa variable.
    """
    n = int(ds.sizes.get("time", 0))
    if n == 0:
        raise ValueError("La serie no tiene pasos temporales.")
    if bool(ds["Hs"].isnull().all()):
        raise ValueError("La serie no tiene valores válidos de Hs.")

    if modo == "maximo":
        i = _indice_peak(ds)
        per, dirr = _tp_dir_en(ds, i)
        fecha = str(ds["time"].isel(time=i).values)[:10]
        return {"hs": float(ds["Hs"].isel(time=i)), "per": per, "dir": dirr,
                "descripcion": f"Máximo observado ({fecha})"}

    if modo == "retorno":
        tr = float(periodo_retorno)
        if not math.isfinite(tr) or tr <= 1:
            raise ValueError(
                "El periodo de retorno debe ser un número finito mayor que 1 año.")
        if not productos.datos_suficientes_multi_anual(ds):
            dias = int(productos._span_dias(ds))
            n = productos._n_anios(ds)
            raise ValueError(
                "Se necesitan al menos 2 años de registro y span ≥ 730 días para "
                f"el ajuste de Gumbel (hay {n} año(s), span {dias} d).")
        maximos = ds["Hs"].groupby("time.year").max().values
        n = maximos.size
        if n < 2:
            raise ValueError(
                "Se necesitan al menos 2 años de datos para el ajuste de Gumbel "
                f"(la serie tiene {n}).")
        loc, scale = stats.gumbel_r.fit(maximos)
        hs = float(stats.gumbel_r.ppf(1 - 1.0 / tr, loc, scale))
        if not math.isfinite(hs) or hs <= 0:
            raise ValueError(
                "El ajuste de Gumbel no produjo un Hs válido para el periodo "
                f"de retorno T={tr:g} años. Revisa la calidad de la serie.")
        i = _indice_peak(ds)
        per, dirr = _tp_dir_en(ds, i)
        desc = f"Periodo de retorno T={tr:g} años"
        if n < 10:
            desc += f" (solo {n} años: ajuste poco fiable)"
        return {"hs": hs, "per": per, "dir": dirr, "descripcion": desc}

    if modo == "reinante":
        hs = _float_finito(ds["Hs"].median())
        if hs is None or hs <= 0:
            raise ValueError("La mediana de Hs no es un valor válido.")
        per = _float_finito(ds["Tp"].median()) if "Tp" in ds.data_vars else None
        dirr = None
        if "Dir" in ds.data_vars:
            d = np.asarray(ds["Dir"].values, float)
            d = d[np.isfinite(d)] % 360.0
            if d.size == 0:
                dirr = None
            else:
                sectores = np.floor(d / 22.5).astype(int) % 16
                dominante = int(np.bincount(sectores, minlength=16).argmax())
                dirr = dominante * 22.5 + 11.25
        return {"hs": hs, "per": per, "dir": dirr,
                "descripcion": "Oleaje reinante (p50)"}

    raise ValueError(f"Modo de condición desconocido: {modo!r}")
