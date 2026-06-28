"""
Miniaturas PNG (base64) para la UI web: malla, batimetría e imágenes existentes.
"""

import base64
import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

from io_batimetria import epsg_utm, leer_bot_como_grilla

FUENTE_ETOPO_KM = 1.85


def _malla_corners_latlon(malla):
    mxc, myc = int(malla["mxc"]), int(malla["myc"])
    xlenc, ylenc = float(malla["xlenc"]), float(malla["ylenc"])
    xpc, ypc = float(malla["xpc"]), float(malla["ypc"])
    zona = malla.get("zona_utm", "19S")
    a_geo = Transformer.from_crs(epsg_utm(zona), 4326, always_xy=True)
    corners = [(xpc, ypc), (xpc + xlenc, ypc), (xpc + xlenc, ypc + ylenc), (xpc, ypc + ylenc)]
    lons, lats = zip(*(a_geo.transform(x, y) for x, y in corners))
    return list(lons) + [lons[0]], list(lats) + [lats[0]], zona, mxc, myc


def imagen_a_base64(ruta, max_bytes=8_000_000):
    """Lee un PNG/JPG y devuelve data-URL o None si no existe."""
    p = Path(ruta)
    if not p.is_file():
        return None
    if p.stat().st_size > max_bytes:
        return None
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _fig_a_base64(fig, dpi=120):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def preview_malla(malla, lat_centro=None, lon_centro=None):
    """Rectángulo del dominio en lat/lon."""
    lons, lats, zona, mxc, myc = _malla_corners_latlon(malla)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.fill(lons, lats, alpha=0.25, color="#007aff", edgecolor="#007aff", lw=2)
    if lat_centro is not None and lon_centro is not None:
        ax.plot(float(lon_centro), float(lat_centro), "r*", ms=12, label="Centro")
        ax.legend(fontsize=8)
    ax.set_xlabel("Longitud [°]")
    ax.set_ylabel("Latitud [°]")
    ax.set_title(f"Dominio {mxc}×{myc} celdas · zona {zona}")
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal", adjustable="datalim")
    return _fig_a_base64(fig)


def preview_malla_anidada(malla_grande, malla_nido):
    """Dominio grande + nido superpuestos en lat/lon."""
    lg, ltg, zona, mgx, mgy = _malla_corners_latlon(malla_grande)
    ln, ltn, _, mnx, mny = _malla_corners_latlon(malla_nido)
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    ax.fill(lg, ltg, alpha=0.2, color="#007aff", edgecolor="#007aff", lw=2, label="Grande")
    ax.fill(ln, ltn, alpha=0.35, color="#30b0c7", edgecolor="#0d8a9e", lw=2, label="Nido")
    ax.set_xlabel("Longitud [°]")
    ax.set_ylabel("Latitud [°]")
    ax.set_title(f"Anidamiento · {mgx}×{mgy} → {mnx}×{mny} · {zona}")
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal", adjustable="datalim")
    return _fig_a_base64(fig)


def preview_batimetria(ruta_bot, malla):
    """Mapa de profundidad con tierra marcada + histograma."""
    depth = leer_bot_como_grilla(ruta_bot, malla)
    mar = depth[depth > 0]
    tierra = depth <= 0
    pct_tierra = float(np.mean(tierra) * 100)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.5, 3.4))
    display = np.where(depth > 0, depth, np.nan)
    im = ax1.imshow(display, origin="lower", cmap="terrain_r", aspect="auto")
    if tierra.any():
        ax1.contour(tierra.astype(float), levels=[0.5], colors="#c93400", linewidths=0.8)
    ax1.set_title("Profundidad [m] (rojo = tierra/emersión)")
    plt.colorbar(im, ax=ax1, fraction=0.046, label="m")
    if mar.size:
        ax2.hist(mar.ravel(), bins=min(30, max(5, mar.size // 10)),
                 color="#30b0c7", edgecolor="white")
    ax2.set_xlabel("Profundidad [m]")
    ax2.set_ylabel("Nodos")
    ax2.set_title(f"Solo mar · {pct_tierra:.0f}% tierra")
    fig.tight_layout()
    return _fig_a_base64(fig)
