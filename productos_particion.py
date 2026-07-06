"""
Productos de partición espectral: serie de Hs por familia (sea/swell) y espectro
polar coloreado por familia. Comparten el motor de particion_espectral y se
registran tanto en el tablero de curvas (productos.py) como en el de mapas SWAN
(productos_swan.py).
"""

import numpy as np

import particion_espectral

# Color por tipo de familia.
_COLOR = {"sea": "#d18616", "swell": "#1f6feb", "": "#999999"}


def calcular_serie(ds_efth):
    """Particiona la serie y devuelve el Dataset(time, familia) + nº de familias."""
    series = particion_espectral.particionar_serie(ds_efth)
    n = int(np.isfinite(series["Hs"]).any("time").sum())
    return {"series": series, "n_familias": n}


def dibujar_serie(ax, r):
    """Hs de cada familia en el tiempo, color por tipo, con la Hs total de fondo."""
    series = r["series"]
    t = series["time"].values
    hs = series["Hs"].values                          # (time, familia)
    total = np.sqrt(np.nansum(hs ** 2, axis=1))       # Hs total = raíz suma de m0
    ax.plot(t, total, color="#444", lw=1.4, label="Hs total")
    for k in range(series.sizes["familia"]):
        if not np.isfinite(hs[:, k]).any():
            continue
        tipos = series["tipo"].values[:, k]
        tipo = next((x for x in tipos if x), "")
        ax.plot(t, hs[:, k], color=_COLOR.get(tipo, "#999999"), lw=1.0,
                label=f"Familia {k} ({tipo or 's/d'})")
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Hs [m]")
    ax.set_title("Partición sea/swell — Hs por familia")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)


def tabla_familias(efth, freqs, dirs, viento=None):
    """
    Tabla (DataFrame) con una fila por familia del espectro de un paso: tipo,
    Hs, Tp, Dir. Exportable con `.to_csv(...)` desde quien la llame.
    """
    import pandas as pd
    familias = particion_espectral.particionar(efth, freqs, dirs, viento=viento)
    filas = [{"familia": k, "tipo": f["tipo"], "Hs": round(f["Hs"], 3),
              "Tp": round(f["Tp"], 2), "Dir": round(f["Dir"], 1)}
             for k, f in enumerate(familias)]
    return pd.DataFrame(filas, columns=["familia", "tipo", "Hs", "Tp", "Dir"])


def dibujar_polar(ax, espectro, meta=None):
    """
    Espectro S(f,θ) polar de un paso (el de mayor energía), con cada familia
    marcada por la dirección/frecuencia de su pico y color por tipo.
    """
    if "time" in espectro.dims:
        energia_t = espectro["Efth"].sum(dim=[d for d in espectro["Efth"].dims
                                               if d != "time"])
        esp = espectro.isel(time=int(energia_t.argmax()))
    else:
        esp = espectro
    freqs = esp["freq"].values
    dirs = esp["dir"].values
    densidad = np.nan_to_num(esp["Efth"].values)

    theta = np.deg2rad(dirs)
    malla_t, malla_r = np.meshgrid(theta, freqs)
    pm = ax.pcolormesh(malla_t, malla_r, densidad, shading="auto", cmap="viridis")
    ax.figure.colorbar(pm, ax=ax, label="S(f,θ) [m²/Hz/rad]", shrink=0.7, pad=0.1)

    familias = particion_espectral.particionar(densidad, freqs, dirs)
    for fam in familias:
        fp = 1.0 / fam["Tp"] if fam["Tp"] and fam["Tp"] > 0 else 0.0
        ax.plot(np.deg2rad(fam["Dir"]), fp, "o", ms=9,
                color=_COLOR.get(fam["tipo"], "#999999"),
                label=f"{fam['tipo']}: Hs={fam['Hs']:.1f} m, Tp={fam['Tp']:.0f} s")
    ax.set_title("Espectro particionado S(f,θ)", fontsize=9, pad=8)
    ax.legend(fontsize=7, loc="upper right", bbox_to_anchor=(1.35, 1.1))
