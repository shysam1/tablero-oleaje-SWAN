"""
Deriva una condición de borde SWAN (Hs, Tp, Dir) a partir de una serie de oleaje
(ERA5 o .mat/.csv/.nc propio). Tres modos: periodo de retorno (Gumbel), máximo
observado y oleaje reinante. Motor puro: recibe un Dataset(time) con Hs (y, según
el modo, Tp/Dir) y devuelve un dict, sin tocar la GUI.

El Dir se entrega en la misma convención de la serie (náutica: de dónde viene el
oleaje); el .swn generado por swan_builder emite SET NAUTICAL para interpretarlo
igual.
"""

import numpy as np
from scipy import stats


def _indice_peak(ds):
    """Índice temporal del mayor Hs de la serie."""
    return int(ds["Hs"].argmax("time"))


def _tp_dir_en(ds, i):
    """Tp y Dir en el paso i (None si la variable no está en la serie)."""
    per = float(ds["Tp"].isel(time=i)) if "Tp" in ds.data_vars else None
    dirr = float(ds["Dir"].isel(time=i)) if "Dir" in ds.data_vars else None
    return per, dirr


def condicion_borde(ds, modo, periodo_retorno=100):
    """
    Devuelve {hs, per, dir, descripcion} para el borde SWAN.

    modo 'maximo': Hs/Tp/Dir del instante de mayor Hs.
    modo 'retorno': Hs de periodo de retorno por ajuste Gumbel; Tp/Dir del peak.
    modo 'reinante': mediana de Hs/Tp + sector direccional dominante.
    Las claves per/dir valen None si la serie no trae esa variable.
    """
    if modo == "maximo":
        i = _indice_peak(ds)
        per, dirr = _tp_dir_en(ds, i)
        fecha = str(ds["time"].isel(time=i).values)[:10]
        return {"hs": float(ds["Hs"].isel(time=i)), "per": per, "dir": dirr,
                "descripcion": f"Máximo observado ({fecha})"}

    if modo == "retorno":
        maximos = ds["Hs"].groupby("time.year").max().values
        n = maximos.size
        if n < 2:
            raise ValueError(
                "Se necesitan al menos 2 años de datos para el ajuste de Gumbel "
                f"(la serie tiene {n}).")
        loc, scale = stats.gumbel_r.fit(maximos)
        hs = float(stats.gumbel_r.ppf(1 - 1.0 / periodo_retorno, loc, scale))
        i = _indice_peak(ds)
        per, dirr = _tp_dir_en(ds, i)
        desc = f"Periodo de retorno T={periodo_retorno} años"
        if n < 10:
            desc += f" (solo {n} años: ajuste poco fiable)"
        return {"hs": hs, "per": per, "dir": dirr, "descripcion": desc}

    if modo == "reinante":
        hs = float(ds["Hs"].median())
        per = float(ds["Tp"].median()) if "Tp" in ds.data_vars else None
        dirr = None
        if "Dir" in ds.data_vars:
            d = np.asarray(ds["Dir"].values, float) % 360.0
            sectores = np.floor(d / 22.5).astype(int) % 16      # 16 sectores de 22.5°
            dominante = int(np.bincount(sectores, minlength=16).argmax())
            dirr = dominante * 22.5 + 11.25                     # centro del sector
        return {"hs": hs, "per": per, "dir": dirr,
                "descripcion": "Oleaje reinante (p50)"}

    raise ValueError(f"Modo de condición desconocido: {modo!r}")
