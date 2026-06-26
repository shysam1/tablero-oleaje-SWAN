"""
Registro de productos (cálculos + paneles) del tablero de oleaje.

Cada producto declara qué variables necesita, cómo se calcula y cómo se dibuja.
El pipeline inspecciona el Dataset y, mediante 'evaluar', decide qué productos
puede generar. Lo que no puede (por faltar datos) se reporta de forma explícita.

Estructura de un producto:
    nombre      -> texto descriptivo
    requiere    -> lista de variables necesarias
    proyeccion  -> None o 'polar' (tipo de eje que necesita el panel)
    calcular    -> función ds -> dict de resultados (None si no implementado)
    dibujar     -> función (ax, resultados) -> None
"""

import sys

import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

# np.trapz fue renombrado a np.trapezoid en numpy reciente; soportamos ambos.
_integrar = getattr(np, "trapezoid", None) or np.trapz

AZUL = "#1f6feb"


# --- Resumen estadístico (panel de tabla) ---
def _calc_resumen(ds):
    filas = []
    for v in ("Hs", "Tp", "Dir"):
        if v in ds.data_vars:
            da = ds[v]
            filas.append((v, float(da.mean()), float(da.std()),
                          float(da.min()), float(da.max())))
    return {"filas": filas, "n": int(ds.sizes.get("time", 0))}


def _dib_resumen(ax, r):
    ax.axis("off")
    celdas = [[v, f"{m:.2f}", f"{s:.2f}", f"{mn:.2f}", f"{mx:.2f}"]
              for (v, m, s, mn, mx) in r["filas"]]
    tabla = ax.table(cellText=celdas,
                     colLabels=["Var", "Media", "Desv", "Mín", "Máx"],
                     loc="center", cellLoc="center")
    tabla.auto_set_font_size(False)
    tabla.set_fontsize(9)
    tabla.scale(1, 1.5)
    ax.set_title(f"Resumen estadístico (N = {r['n']})")


# --- Serie temporal de Hs (media mensual) ---
def _calc_serie(ds):
    mensual = ds["Hs"].resample(time="1MS").mean()
    return {"t": mensual["time"].values, "hs": mensual.values}


def _dib_serie(ax, r):
    ax.plot(r["t"], r["hs"], lw=0.8, color=AZUL)
    ax.set_title("Serie temporal de Hs (media mensual)")
    ax.set_xlabel("Año")
    ax.set_ylabel("Hs [m]")
    ax.grid(alpha=0.3)


# --- Climatología mensual de Hs ---
def _calc_clima(ds):
    media = ds["Hs"].groupby("time.month").mean()
    desv = ds["Hs"].groupby("time.month").std()
    return {"mes": media["month"].values, "media": media.values, "desv": desv.values}


def _dib_clima(ax, r):
    ax.bar(r["mes"], r["media"], yerr=r["desv"], color=AZUL, alpha=0.85, capsize=3)
    ax.set_title("Climatología mensual de Hs")
    ax.set_xlabel("Mes")
    ax.set_ylabel("Hs media [m]")
    ax.set_xticks(range(1, 13))
    ax.grid(alpha=0.3, axis="y")


# --- Curva de excedencia de Hs ---
def _calc_excedencia(ds):
    hs = np.sort(ds["Hs"].values)[::-1]
    prob = np.arange(1, hs.size + 1) / hs.size * 100   # % de tiempo excedido
    return {"hs": hs, "prob": prob}


def _dib_excedencia(ax, r):
    ax.plot(r["prob"], r["hs"], color=AZUL)
    ax.set_title("Curva de excedencia de Hs")
    ax.set_xlabel("Probabilidad de excedencia [%]")
    ax.set_ylabel("Hs [m]")
    ax.grid(alpha=0.3)


# --- Régimen extremo: máximo anual de Hs ---
def _calc_extremos(ds):
    maximos = ds["Hs"].groupby("time.year").max()    # un máximo por año
    return {"anio": maximos["year"].values,
            "hs_max": maximos.values,
            "media": float(maximos.mean())}


def _dib_extremos(ax, r):
    ax.bar(r["anio"], r["hs_max"], color=AZUL, alpha=0.85)
    ax.axhline(r["media"], color="#d1242f", ls="--", lw=1.2,
               label=f"Media de máximos = {r['media']:.2f} m")
    ax.set_title("Régimen extremo: máximo anual de Hs")
    ax.set_xlabel("Año")
    ax.set_ylabel("Hs máx [m]")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")


# --- Períodos de retorno: ajuste de Gumbel a los máximos anuales ---
def _calc_retorno(ds, periodos=(2, 5, 10, 25, 50, 100)):
    maximos = np.sort(ds["Hs"].groupby("time.year").max().values)
    n = maximos.size

    # Ajuste de Gumbel (valores extremos tipo I) por máxima verosimilitud.
    loc, scale = stats.gumbel_r.fit(maximos)

    # Posición de ploteo de Gringorten -> período de retorno empírico [años].
    m = np.arange(1, n + 1)                       # rango ascendente
    prob_no_exc = (m - 0.44) / (n + 0.12)         # prob. de no excedencia
    t_emp = 1.0 / (1.0 - prob_no_exc)

    # Curva teórica de Gumbel y valores de diseño.
    t_curva = np.logspace(np.log10(1.1), np.log10(200), 200)
    hs_curva = stats.gumbel_r.ppf(1 - 1 / t_curva, loc, scale)
    diseno = {t: float(stats.gumbel_r.ppf(1 - 1 / t, loc, scale)) for t in periodos}

    return {"t_emp": t_emp, "hs_emp": maximos, "t_curva": t_curva,
            "hs_curva": hs_curva, "diseno": diseno, "loc": loc, "scale": scale}


def _dib_retorno(ax, r):
    ax.semilogx(r["t_curva"], r["hs_curva"], color=AZUL, label="Ajuste Gumbel")
    ax.scatter(r["t_emp"], r["hs_emp"], s=18, color="#d1242f", zorder=3,
               label="Máximos anuales (Gringorten)")
    for t in (50, 100):                           # marcar el oleaje de diseño
        hs = r["diseno"][t]
        ax.plot([t], [hs], "ks", ms=5)
        ax.annotate(f"T={t} a: {hs:.2f} m", xy=(t, hs),
                    xytext=(6, -10), textcoords="offset points", fontsize=8)
    ax.set_title("Períodos de retorno de Hs (Gumbel)")
    ax.set_xlabel("Período de retorno [años]")
    ax.set_ylabel("Hs [m]")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)


# --- Distribución de Hs con ajuste de Rayleigh ---
def _calc_rayleigh(ds):
    hs = ds["Hs"].values
    sigma = np.sqrt(np.mean(hs ** 2) / 2)              # escala de Rayleigh
    x = np.linspace(0, hs.max(), 200)
    pdf = (x / sigma ** 2) * np.exp(-x ** 2 / (2 * sigma ** 2))
    return {"hs": hs, "x": x, "pdf": pdf, "sigma": sigma}


def _dib_rayleigh(ax, r):
    ax.hist(r["hs"], bins=40, density=True, color="#9ecbff",
            edgecolor="white", linewidth=0.3)
    ax.plot(r["x"], r["pdf"], color="#d1242f", lw=2,
            label=f"Rayleigh (σ = {r['sigma']:.2f})")
    ax.set_title("Distribución de Hs")
    ax.set_xlabel("Hs [m]")
    ax.set_ylabel("Densidad")
    ax.legend()
    ax.grid(alpha=0.3)


# --- Histograma conjunto Hs-Tp ---
def _calc_hstp(ds):
    return {"hs": ds["Hs"].values, "tp": ds["Tp"].values}


def _dib_hstp(ax, r):
    h = ax.hist2d(r["tp"], r["hs"], bins=40, cmap="viridis", cmin=1)
    ax.figure.colorbar(h[3], ax=ax, label="N° de registros")
    ax.set_title("Histograma conjunto Hs–Tp")
    ax.set_xlabel("Tp [s]")
    ax.set_ylabel("Hs [m]")


# --- Rosa de oleaje (eje polar) ---
def _calc_rosa(ds):
    return {"dir": ds["Dir"].values, "hs": ds["Hs"].values}


def _dib_rosa(ax, r):
    n_sec = 16
    bordes = np.linspace(0, 360, n_sec + 1)
    clases = [0, 1, 2, 3, 4, np.inf]
    colores = plt.cm.viridis(np.linspace(0, 1, len(clases) - 1))
    ancho = 2 * np.pi / n_sec
    centros = np.deg2rad((bordes[:-1] + bordes[1:]) / 2)

    fondo = np.zeros(n_sec)
    for i in range(len(clases) - 1):
        mask = (r["hs"] >= clases[i]) & (r["hs"] < clases[i + 1])
        conteo, _ = np.histogram(r["dir"][mask], bins=bordes)
        frec = conteo / r["hs"].size * 100               # % de ocurrencia
        etiqueta = (f"{clases[i]:.0f}–{clases[i + 1]:.0f} m"
                    if np.isfinite(clases[i + 1]) else f"> {clases[i]:.0f} m")
        ax.bar(centros, frec, width=ancho, bottom=fondo, color=colores[i],
               edgecolor="white", linewidth=0.3, label=etiqueta)
        fondo += frec

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_title("Rosa de oleaje (procedencia)", pad=15)
    ax.legend(loc="upper right", bbox_to_anchor=(1.30, 1.10),
              fontsize=7, title="Hs")


# --- Espectro JONSWAP reconstruido (estado de mar medio) ---
def _calc_jonswap(ds):
    hs = float(ds["Hs"].mean())
    tp = float(ds["Tp"].mean())
    fp = 1.0 / tp
    f = np.linspace(0.3 * fp, 3.0 * fp, 300)
    gamma = 3.3
    sigma = np.where(f <= fp, 0.07, 0.09)
    forma = (f ** -5 * np.exp(-1.25 * (fp / f) ** 4)
             * gamma ** np.exp(-((f - fp) ** 2) / (2 * sigma ** 2 * fp ** 2)))
    # Escalar la forma para reproducir el Hs objetivo: Hs = 4*sqrt(m0).
    escala = (hs / 4.0) ** 2 / _integrar(forma, f)
    return {"f": f, "S": escala * forma, "hs": hs, "tp": tp}


def _dib_jonswap(ax, r):
    ax.plot(r["f"], r["S"], color=AZUL)
    ax.fill_between(r["f"], r["S"], alpha=0.2, color=AZUL)
    ax.set_title(f"Espectro JONSWAP reconstruido\n"
                 f"(estado medio: Hs = {r['hs']:.2f} m, Tp = {r['tp']:.1f} s)")
    ax.set_xlabel("Frecuencia [Hz]")
    ax.set_ylabel("S(f) [m²·s]")
    ax.grid(alpha=0.3)


# Registro central de productos. El orden define el orden en el tablero.
PRODUCTOS = [
    {"nombre": "Resumen estadístico", "requiere": [], "proyeccion": None,
     "calcular": _calc_resumen, "dibujar": _dib_resumen},
    {"nombre": "Serie temporal de Hs", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_serie, "dibujar": _dib_serie},
    {"nombre": "Climatología mensual", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_clima, "dibujar": _dib_clima},
    {"nombre": "Curva de excedencia", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_excedencia, "dibujar": _dib_excedencia},
    {"nombre": "Régimen extremo (máx. anual)", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_extremos, "dibujar": _dib_extremos},
    {"nombre": "Períodos de retorno (Gumbel)", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_retorno, "dibujar": _dib_retorno},
    {"nombre": "Distribución de Hs (Rayleigh)", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_rayleigh, "dibujar": _dib_rayleigh},
    {"nombre": "Histograma conjunto Hs–Tp", "requiere": ["Hs", "Tp"], "proyeccion": None,
     "calcular": _calc_hstp, "dibujar": _dib_hstp},
    {"nombre": "Rosa de oleaje", "requiere": ["Hs", "Dir"], "proyeccion": "polar",
     "calcular": _calc_rosa, "dibujar": _dib_rosa},
    {"nombre": "Espectro JONSWAP (reconstruido)", "requiere": ["Hs", "Tp"], "proyeccion": None,
     "calcular": _calc_jonswap, "dibujar": _dib_jonswap},
    {"nombre": "Espectro medido S(f)", "requiere": ["Sf"], "proyeccion": None,
     "calcular": None, "dibujar": None},
]


def evaluar(ds):
    """
    Inspecciona el Dataset y devuelve, por cada producto, si está disponible.

    Para los disponibles, calcula el resultado de inmediato. Devuelve una lista
    de dicts: nombre, disponible, faltan, proyeccion, dibujar, resultado.
    """
    informe = []
    for p in PRODUCTOS:
        faltan = [v for v in p["requiere"] if v not in ds.data_vars]
        disponible = (not faltan) and (p["calcular"] is not None)
        informe.append({
            "nombre": p["nombre"], "disponible": disponible, "faltan": faltan,
            "proyeccion": p["proyeccion"], "dibujar": p["dibujar"],
            "resultado": p["calcular"](ds) if disponible else None,
        })
    return informe


def imprimir_capacidades(informe):
    """Imprime el reporte de capacidades (qué se puede y qué no, con motivo)."""
    print("\n=== Capacidades del pipeline ===")
    for it in informe:
        if it["disponible"]:
            print(f"  [ ok ] {it['nombre']}")
        else:
            motivo = (f"faltan datos: {', '.join(it['faltan'])}"
                      if it["faltan"] else "no implementado")
            print(f"  [ -- ] {it['nombre']}: {motivo}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from pathlib import Path
    import io_oleaje

    ds = io_oleaje.cargar(Path(__file__).with_name("oleaje_talcahuano.nc"))
    informe = evaluar(ds)
    imprimir_capacidades(informe)
    print(f"\nProductos disponibles: "
          f"{sum(it['disponible'] for it in informe)} de {len(informe)}")
    ds.close()
