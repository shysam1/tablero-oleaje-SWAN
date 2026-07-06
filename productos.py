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
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from scipy import stats

import particion_espectral
import productos_particion

# np.trapz fue renombrado a np.trapezoid en numpy reciente; soportamos ambos.
_integrar = getattr(np, "trapezoid", None) or np.trapz

AZUL = "#1f6feb"

# Umbrales del registro adaptativo (misma lógica que Gumbel para productos multi-anuales).
_MIN_ANIOS_CLIMA = 2
_MIN_DIAS_SERIE_MENSUAL = 365
# Span mínimo (~2 años) además de años calendario: evita jul-2024→jul-2025 (2 años
# en el eje pero solo ~12 meses de registro y máximos anuales parciales).
_MIN_DIAS_MULTI_ANUAL = 730


def _span_dias(ds):
    """Duración de la serie en días (último − primer instante)."""
    t = ds["time"].values
    if t.size < 2:
        return 0.0
    return float((t[-1] - t[0]) / np.timedelta64(1, "D"))


def _n_anios(ds):
    """Número de años distintos con dato (tamaño de la serie de máximos anuales)."""
    return int(ds["Hs"].groupby("time.year").max().sizes.get("year", 0))


def datos_suficientes_multi_anual(ds):
    """Productos anuales/extremos: span ≥ ~2 años y ≥ 2 años calendario con dato."""
    return (_span_dias(ds) >= _MIN_DIAS_MULTI_ANUAL
            and _n_anios(ds) >= _MIN_ANIOS_CLIMA)


_MOTIVO_MULTI_ANUAL = (
    f"≥ {_MIN_ANIOS_CLIMA} años de registro y span ≥ {_MIN_DIAS_MULTI_ANUAL} días "
    "(climatología, régimen extremo y Gumbel)")


def _serie_usa_media_mensual(ds):
    return _span_dias(ds) >= _MIN_DIAS_SERIE_MENSUAL


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


# --- Serie temporal de Hs (nativa o media mensual según duración) ---
def _calc_serie(ds):
    if _serie_usa_media_mensual(ds):
        mensual = ds["Hs"].resample(time="1MS").mean()
        return {"t": mensual["time"].values, "hs": mensual.values, "modo": "mensual"}
    return {"t": ds["time"].values, "hs": ds["Hs"].values, "modo": "nativa"}


def _dib_serie(ax, r):
    ax.plot(r["t"], r["hs"], lw=0.8, color=AZUL)
    if r["modo"] == "nativa":
        ax.set_title("Serie temporal de Hs")
        ax.set_xlabel("Fecha")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        for lb in ax.get_xticklabels():
            lb.set_rotation(25)
            lb.set_ha("right")
    else:
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
    hs = hs[np.isfinite(hs)]
    if hs.size == 0:
        raise ValueError("No hay Hs finitos para la curva de excedencia.")
    prob = np.arange(1, hs.size + 1) / hs.size * 100
    crudo = ds["Hs"].values
    percentiles = {p: float(np.nanpercentile(crudo, p)) for p in (50, 90, 99)}
    return {"hs": hs, "prob": prob, "percentiles": percentiles}


def _dib_excedencia(ax, r):
    ax.plot(r["prob"], r["hs"], color=AZUL)
    colores_pct = {"50": "#6e7781", "90": "#bf8700", "99": "#d1242f"}
    for p, hs in r["percentiles"].items():
        prob_exc = 100.0 - p
        ax.axhline(hs, color=colores_pct[str(p)], ls="--", lw=0.9, alpha=0.85)
        ax.plot(prob_exc, hs, "o", color=colores_pct[str(p)], ms=4, zorder=3)
        ax.annotate(f"P{p} = {hs:.2f} m", xy=(prob_exc, hs),
                    xytext=(4, 4), textcoords="offset points", fontsize=7)
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
    if not datos_suficientes_multi_anual(ds):
        dias = int(_span_dias(ds))
        n = _n_anios(ds)
        raise ValueError(
            f"El ajuste de Gumbel necesita ≥ {_MIN_ANIOS_CLIMA} años de registro "
            f"y span ≥ {_MIN_DIAS_MULTI_ANUAL} días (hay {n} año(s), span {dias} d).")
    maximos = np.sort(ds["Hs"].groupby("time.year").max().values)
    n = maximos.size
    if n < 2:
        raise ValueError(
            f"El ajuste de Gumbel necesita ≥ 2 años de máximos anuales (hay {n}).")

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
    hs = hs[np.isfinite(hs)]
    if hs.size == 0 or np.all(hs <= 0):
        raise ValueError("No hay Hs positivos para el ajuste de Rayleigh.")
    sigma = np.sqrt(np.mean(hs ** 2) / 2)
    if sigma <= 0:
        raise ValueError("La escala de Rayleigh es cero.")
    x = np.linspace(0, max(hs.max(), 0.01), 200)
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
    n_total = max(int(np.isfinite(r["hs"]).sum()), 1)

    fondo = np.zeros(n_sec)
    for i in range(len(clases) - 1):
        mask = (r["hs"] >= clases[i]) & (r["hs"] < clases[i + 1])
        conteo, _ = np.histogram(r["dir"][mask], bins=bordes)
        frec = conteo / n_total * 100
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
    if not np.isfinite(tp) or tp <= 0:
        raise ValueError("Tp medio inválido para reconstruir JONSWAP.")
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


def _dim_frecuencia(da):
    """Nombre de la dimensión de frecuencia en una DataArray (freq/frequency/f)."""
    for nombre in ("freq", "frequency", "f"):
        if nombre in da.dims:
            return nombre
    raise ValueError("no se encontró dimensión de frecuencia")


def _sf_desde_efth(ds):
    """Integra Efth(freq, dir) o Efth(time, freq, dir) → S(f) [m²/Hz]."""
    efth = ds["Efth"]
    freqs = efth["freq"].values
    dirs = efth["dir"].values
    _, ddir = particion_espectral._pesos(freqs, dirs)
    sf = (efth * ddir).sum(dim="dir")
    if "time" in sf.dims:
        sf_vals = sf.mean("time").values
        nota = "promedio temporal (Efth)"
    else:
        sf_vals = sf.values
        nota = "integral direccional (Efth)"
    return freqs, np.asarray(sf_vals, float), nota


def _sf_desde_variable(ds):
    """Lee Sf directamente (1D o media temporal)."""
    sf_var = ds["Sf"]
    dim_f = _dim_frecuencia(sf_var)
    freqs = sf_var[dim_f].values
    if "time" in sf_var.dims:
        valores = sf_var.mean("time").values
        nota = "promedio temporal (Sf)"
    else:
        valores = sf_var.values
        nota = "medido (Sf)"
    return freqs, np.asarray(valores, float), nota


def _aplicable_espectro_medido(ds):
    return "Sf" in ds.data_vars or "Efth" in ds.data_vars


_MOTIVO_ESPECTRO_MEDIDO = "variable Sf o Efth (densidad espectral direccional)"


def _calc_espectro_medido(ds):
    if "Sf" in ds.data_vars:
        f, s, fuente = _sf_desde_variable(ds)
    else:
        f, s, fuente = _sf_desde_efth(ds)
    s = np.nan_to_num(s, nan=0.0)
    if not np.isfinite(s).any() or float(np.nanmax(s)) <= 0.0:
        raise ValueError("el espectro no tiene energía finita")
    # Hs desde m0 para anotar en el panel
    dfreq, _ = particion_espectral._pesos(f, np.array([0.0, 1.0]))
    m0 = float(np.sum(s * dfreq))
    hs = 4.0 * np.sqrt(m0) if m0 > 0 else np.nan
    fp = float(f[int(np.argmax(s))]) if s.size else np.nan
    tp = 1.0 / fp if fp > 0 else np.nan
    return {"f": f, "S": s, "hs": hs, "tp": tp, "fuente": fuente}


def _dib_espectro_medido(ax, r):
    ax.plot(r["f"], r["S"], color=AZUL)
    ax.fill_between(r["f"], r["S"], alpha=0.2, color=AZUL)
    titulo = "Espectro medido S(f)"
    if np.isfinite(r.get("hs", np.nan)):
        titulo += f"\n(Hs ≈ {r['hs']:.2f} m"
        if np.isfinite(r.get("tp", np.nan)):
            titulo += f", Tp ≈ {r['tp']:.1f} s"
        titulo += f"; {r['fuente']})"
    else:
        titulo += f"\n({r['fuente']})"
    ax.set_title(titulo)
    ax.set_xlabel("Frecuencia [Hz]")
    ax.set_ylabel("S(f) [m²/Hz]")
    ax.grid(alpha=0.3)


# Registro central de productos. El orden define el orden en el tablero.
PRODUCTOS = [
    {"nombre": "Resumen estadístico", "requiere": [], "proyeccion": None,
     "calcular": _calc_resumen, "dibujar": _dib_resumen},
    {"nombre": "Serie temporal de Hs", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_serie, "dibujar": _dib_serie},
    {"nombre": "Climatología mensual", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_clima, "dibujar": _dib_clima,
     "aplicable": datos_suficientes_multi_anual,
     "motivo_inaplicable": _MOTIVO_MULTI_ANUAL},
    {"nombre": "Curva de excedencia", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_excedencia, "dibujar": _dib_excedencia},
    {"nombre": "Régimen extremo (máx. anual)", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_extremos, "dibujar": _dib_extremos,
     "aplicable": datos_suficientes_multi_anual,
     "motivo_inaplicable": _MOTIVO_MULTI_ANUAL},
    {"nombre": "Períodos de retorno (Gumbel)", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_retorno, "dibujar": _dib_retorno,
     "aplicable": datos_suficientes_multi_anual,
     "motivo_inaplicable": _MOTIVO_MULTI_ANUAL},
    {"nombre": "Distribución de Hs (Rayleigh)", "requiere": ["Hs"], "proyeccion": None,
     "calcular": _calc_rayleigh, "dibujar": _dib_rayleigh},
    {"nombre": "Histograma conjunto Hs–Tp", "requiere": ["Hs", "Tp"], "proyeccion": None,
     "calcular": _calc_hstp, "dibujar": _dib_hstp},
    {"nombre": "Rosa de oleaje", "requiere": ["Hs", "Dir"], "proyeccion": "polar",
     "calcular": _calc_rosa, "dibujar": _dib_rosa},
    {"nombre": "Espectro JONSWAP (reconstruido)", "requiere": ["Hs", "Tp"], "proyeccion": None,
     "calcular": _calc_jonswap, "dibujar": _dib_jonswap},
    {"nombre": "Espectro medido S(f)", "requiere": [], "proyeccion": None,
     "aplicable": _aplicable_espectro_medido,
     "motivo_inaplicable": _MOTIVO_ESPECTRO_MEDIDO,
     "calcular": _calc_espectro_medido, "dibujar": _dib_espectro_medido},
    {"nombre": "Partición sea/swell (serie)", "requiere": ["Efth"],
     "proyeccion": None,
     "calcular": productos_particion.calcular_serie,
     "dibujar": productos_particion.dibujar_serie},
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
        # Algunos productos requieren además una condición sobre los datos (p. ej.
        # Gumbel necesita ≥2 años); si no se cumple, se reporta como "falta" para
        # que el motivo aparezca en el informe y no se intente calcular (evita el
        # overflow del ajuste degenerado).
        aplicable_fn = p.get("aplicable")
        if not faltan and aplicable_fn is not None and not aplicable_fn(ds):
            faltan = [p.get("motivo_inaplicable", "datos insuficientes")]
        disponible = (not faltan) and (p["calcular"] is not None)
        resultado = None
        if disponible:
            try:
                resultado = p["calcular"](ds)
            except (ValueError, ZeroDivisionError, FloatingPointError):
                disponible = False
                faltan = [p.get("motivo_inaplicable", "datos insuficientes")]
        informe.append({
            "nombre": p["nombre"], "disponible": disponible, "faltan": faltan,
            "proyeccion": p["proyeccion"], "dibujar": p["dibujar"],
            "resultado": resultado,
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
