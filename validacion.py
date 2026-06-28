"""
Chequeos físicos automáticos sobre el Dataset de oleaje.

No modifica los datos: solo informa cuántos registros incumplen cada regla física
o de consistencia temporal. Cada chequeo declara qué variables necesita; si faltan,
se reporta como "no aplicable" en vez de fallar. Mismo patrón de registro que
productos.py: el pipeline se adapta a lo que el Dataset contiene.
"""

import sys

import numpy as np
import pandas as pd

G = 9.81                 # aceleración de gravedad [m/s2]
PERALTE_ROTURA = 1.0 / 7.0   # límite de peralte de ola en aguas profundas


def _chequeo_hs(ds):
    """Hs debe ser no negativa y físicamente plausible (< 20 m)."""
    da = ds["Hs"]
    n = int(((da < 0) | (da > 20) | da.isnull()).sum())
    return n, "Hs fuera de 0–20 m o faltante (NaN)"


def _chequeo_tp(ds):
    """Tp en un rango realista de oleaje (2–30 s)."""
    da = ds["Tp"]
    n = int(((da < 2) | (da > 30) | da.isnull()).sum())
    return n, "Tp fuera de 2–30 s o faltante (NaN)"


def _chequeo_dir(ds):
    """Dirección como rumbo de procedencia, en [0, 360] (360° ≡ 0°)."""
    da = ds["Dir"]
    n = int(((da < 0) | (da > 360) | da.isnull()).sum())
    return n, "Dir fuera de [0, 360] o faltante (NaN)"


def _chequeo_peralte(ds):
    """
    Peralte en aguas profundas Hs/L0 por debajo del límite de rotura (~1/7),
    con L0 = g·Tp²/(2π). Valores mayores son físicamente sospechosos.
    """
    L0 = G * ds["Tp"] ** 2 / (2 * np.pi)
    peralte = ds["Hs"] / L0
    n = int(((peralte > PERALTE_ROTURA) | ds["Hs"].isnull() | ds["Tp"].isnull()).sum())
    return n, "Peralte Hs/L0 > 1/7 (aguas profundas) o dato faltante"


def _chequeo_tiempo(ds):
    """Consistencia temporal: detecta huecos y registros duplicados."""
    if "time" not in ds.dims and "time" not in ds.coords:
        return 0, "sin coordenada temporal"
    t = pd.to_datetime(ds["time"].values)
    # Con 0 o 1 paso no hay intervalos que comparar: mode() vendría vacío y
    # mode()[0] reventaría con IndexError. No hay nada que evaluar.
    if len(t) < 2:
        return 0, f"serie de {len(t)} paso(s): sin intervalos que evaluar"
    dif = t[1:] - t[:-1]
    paso = pd.Series(dif).mode()[0]          # paso de muestreo más frecuente
    duplicados = int((dif == pd.Timedelta(0)).sum())
    huecos = int((dif > paso).sum())
    return huecos + duplicados, f"{huecos} huecos y {duplicados} duplicados (paso {paso})"


# Registro de chequeos: cada uno declara las variables que requiere.
CHEQUEOS = [
    {"nombre": "Hs en rango plausible",       "requiere": ["Hs"],        "funcion": _chequeo_hs},
    {"nombre": "Tp en rango plausible",       "requiere": ["Tp"],        "funcion": _chequeo_tp},
    {"nombre": "Dir en [0, 360]",             "requiere": ["Dir"],       "funcion": _chequeo_dir},
    {"nombre": "Peralte en aguas profundas",  "requiere": ["Hs", "Tp"],  "funcion": _chequeo_peralte},
    {"nombre": "Continuidad temporal",        "requiere": [],            "funcion": _chequeo_tiempo},
]


def validar(ds):
    """
    Ejecuta los chequeos aplicables y devuelve una lista de resultados.

    Cada resultado es un dict con: nombre, aplicable, n_falla, n_total, detalle.
    Si faltan variables, el chequeo se marca como no aplicable (no se ejecuta).
    """
    n_total = int(ds.sizes.get("time", 0))
    resultados = []
    for chk in CHEQUEOS:
        faltan = [v for v in chk["requiere"] if v not in ds.data_vars]
        if faltan:
            resultados.append({
                "nombre": chk["nombre"], "aplicable": False, "n_falla": None,
                "n_total": n_total, "detalle": f"faltan datos: {', '.join(faltan)}",
            })
            continue
        n_falla, detalle = chk["funcion"](ds)
        resultados.append({
            "nombre": chk["nombre"], "aplicable": True, "n_falla": n_falla,
            "n_total": n_total, "detalle": detalle,
        })
    return resultados


def imprimir_reporte(resultados):
    """Imprime el reporte de validación en consola, legible y compacto."""
    print("\n=== Validación física ===")
    for r in resultados:
        if not r["aplicable"]:
            print(f"  [n/a ] {r['nombre']}: {r['detalle']}")
        elif r["n_falla"] == 0:
            print(f"  [ ok ] {r['nombre']}: sin incidencias")
        else:
            pct = 100 * r["n_falla"] / r["n_total"] if r["n_total"] else 0
            print(f"  [ !! ] {r['nombre']}: {r['n_falla']} de {r['n_total']} "
                  f"({pct:.2f}%) — {r['detalle']}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from pathlib import Path
    import io_oleaje

    ds = io_oleaje.cargar(Path(__file__).with_name("oleaje_talcahuano.nc"))
    imprimir_reporte(validar(ds))
    ds.close()
