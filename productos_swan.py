"""
Productos-mapa para corridas SWAN (campos espaciales 2D).

Análogo a productos.py, pero para mapas en vez de curvas. Cada producto declara
su fuente de datos (un dominio 'large'/'n1', o el espectro del punto) y las
variables requeridas; el tablero inspecciona la corrida y arma solo lo que los
datos permiten.
"""

import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

import productos_particion


def _vectores_direccion(dir_grados):
    """Componentes (u, v) de la dirección, según la convención de los .m."""
    d = np.where(dir_grados >= 180, dir_grados - 360, dir_grados)
    rad = np.deg2rad(d)
    return np.cos(rad), np.sin(rad)


def _mapa_campo(ax, ds, var, cmap="viridis", norm=None, con_direccion=False,
                con_isobatas=True):
    """Dibuja un campo escalar sobre la malla UTM, con isóbatas y, opcional, dirección."""
    x, y = ds["x"].values, ds["y"].values
    campo = ds[var].values

    estilo = {"norm": norm} if norm is not None else {}
    malla = ax.pcolormesh(x, y, campo, shading="nearest", cmap=cmap, **estilo)
    etiqueta = f"{ds[var].attrs.get('long_name', var)} [{ds[var].attrs.get('units', '')}]"
    ax.figure.colorbar(malla, ax=ax, label=etiqueta, shrink=0.85)

    if con_isobatas and "depth" in ds:
        prof = np.where(ds["depth"].values > 0, ds["depth"].values, np.nan)
        ax.contour(x, y, prof, levels=6, colors="white", linewidths=0.4, alpha=0.5)

    if con_direccion and "Dir" in ds:
        u, v = _vectores_direccion(ds["Dir"].values)
        qx, qy = np.meshgrid(x, y)
        paso = max(1, min(len(x), len(y)) // 12)
        ax.quiver(qx[::paso, ::paso], qy[::paso, ::paso],
                  u[::paso, ::paso], v[::paso, ::paso],
                  color="black", scale=22, width=0.004)

    ax.set_aspect("equal")
    ax.set_xlabel("Este UTM [m]")
    ax.set_ylabel("Norte UTM [m]")


def _mapa_hs(ax, ds, meta):
    """Mapa de Hs con batimetría y dirección del oleaje."""
    _mapa_campo(ax, ds, "Hs", cmap="viridis", con_direccion=True)
    ax.set_title(f"Hs — {ds.attrs.get('titulo', '')}\n"
                 f"{meta.get('condicion', '')} "
                 f"(borde {meta.get('Hs_borde', '?')} m, Dp {meta.get('Dp_borde', '?')}°)",
                 fontsize=9)


def _mapa_setup(ax, ds, meta):
    """Mapa de set-up por oleaje (diverge en torno a 0: set-down / set-up)."""
    valores = ds["Setup"].values
    norm = TwoSlopeNorm(vcenter=0.0,
                        vmin=min(float(np.nanmin(valores)), -1e-6),
                        vmax=max(float(np.nanmax(valores)), 1e-6))
    _mapa_campo(ax, ds, "Setup", cmap="RdBu_r", norm=norm, con_isobatas=True)
    ax.set_title(f"Set-up por oleaje — {ds.attrs.get('titulo', '')}", fontsize=9)


def _espectro_direccional(ax, ds_spec, meta):
    """Espectro 2D S(f, dir) en eje polar (frecuencia radial, dirección angular)."""
    theta = np.deg2rad(ds_spec["dir"].values)
    r = ds_spec["freq"].values
    densidad = ds_spec["Efth"].values
    malla_t, malla_r = np.meshgrid(theta, r)
    pm = ax.pcolormesh(malla_t, malla_r, densidad, shading="auto", cmap="viridis")
    ax.figure.colorbar(pm, ax=ax, label="S(f,θ) [m²/Hz/°]", shrink=0.7, pad=0.1)

    # Acotar el radio a la banda que concentra ~99,5% de la energía (swell).
    marginal = np.nansum(densidad, axis=1)
    acumulada = np.cumsum(marginal) / marginal.sum()
    idx = min(int(np.searchsorted(acumulada, 0.995)), len(r) - 1)
    ax.set_ylim(0, float(r[idx]))
    ax.set_rlabel_position(135)
    ax.set_title("Espectro direccional S(f,θ)\n(punto SWAN, dir. cartesiana)",
                 fontsize=9, pad=8)


# Registro de productos-mapa. 'fuente': 'dominio' (large/n1) o 'espectro'.
PRODUCTOS_SWAN = [
    {"nombre": "Mapa de Hs (grande)", "fuente": "dominio", "dominio": "large",
     "requiere": ["Hs"], "proyeccion": None, "dibujar": _mapa_hs},
    {"nombre": "Mapa de Hs (N1)", "fuente": "dominio", "dominio": "n1",
     "requiere": ["Hs"], "proyeccion": None, "dibujar": _mapa_hs},
    {"nombre": "Mapa de set-up (N1)", "fuente": "dominio", "dominio": "n1",
     "requiere": ["Setup"], "proyeccion": None, "dibujar": _mapa_setup},
    {"nombre": "Espectro direccional", "fuente": "espectro",
     "requiere": [], "proyeccion": "polar", "dibujar": _espectro_direccional},
    {"nombre": "Espectro particionado", "fuente": "espectro",
     "requiere": [], "proyeccion": "polar", "dibujar": productos_particion.dibujar_polar},
]


def evaluar(corrida):
    """Inspecciona la corrida y devuelve qué productos-mapa se pueden generar."""
    dominios = corrida.get("dominios", {})
    espectro = corrida.get("espectro")
    informe = []
    for p in PRODUCTOS_SWAN:
        if p["fuente"] == "dominio":
            ds = dominios.get(p["dominio"])
            faltan = ([f"dominio {p['dominio']}"] if ds is None
                      else [v for v in p["requiere"] if v not in ds.data_vars])
            datos = ds
        else:                                     # espectro
            datos = espectro
            faltan = [] if espectro is not None else ["Espectro_Punto.txt"]
        informe.append({"nombre": p["nombre"], "disponible": not faltan,
                        "faltan": faltan, "proyeccion": p["proyeccion"],
                        "dibujar": p["dibujar"], "datos": datos})
    return informe


def imprimir_capacidades(informe):
    """Imprime qué mapas se pueden generar y cuáles no (con motivo)."""
    print("\n=== Capacidades del tablero SWAN ===")
    for it in informe:
        if it["disponible"]:
            print(f"  [ ok ] {it['nombre']}")
        else:
            print(f"  [ -- ] {it['nombre']}: faltan {', '.join(it['faltan'])}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from pathlib import Path
    import io_swan

    CARPETA = Path(
        r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python"
        r"\SWAN_Coronel\extremo_Tr100")
    corrida = io_swan.cargar_corrida(CARPETA)
    informe = evaluar(corrida)
    imprimir_capacidades(informe)

    disponibles = [it for it in informe if it["disponible"]]
    cols = 2
    filas = int(np.ceil(len(disponibles) / cols))
    fig = plt.figure(figsize=(cols * 7, filas * 6))
    for i, it in enumerate(disponibles):
        ax = fig.add_subplot(filas, cols, i + 1, projection=it["proyeccion"])
        it["dibujar"](ax, it["datos"], corrida["meta"])
    fig.tight_layout()
    salida = Path(__file__).with_name("swan_test_full.png")
    fig.savefig(salida, dpi=150)
    print("\nGuardado:", salida)
