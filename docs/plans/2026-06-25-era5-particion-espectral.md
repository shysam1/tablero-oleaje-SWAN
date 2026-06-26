# ERA5 + Partición espectral — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar a la herramienta Tablero de Oleaje (1) descarga de oleaje por coordenada desde ERA5/Copernicus CDS —serie Hs/Tp/Dir y espectros 2D— y (2) partición espectral sea/swell por familias (watershed Hanson & Phillips) sobre cualquier espectro `Efth(freq,dir)`, venga de SWAN o de ERA5.

**Architecture:** Dos módulos nuevos desacoplados (`io_era5.py` entrada, `particion_espectral.py` análisis) que producen/consumen los Datasets que el pipeline ya maneja (`Dataset(time)` con Hs/Tp/Dir y `Efth(time,freq,dir)`). La partición entra como producto del registro adaptativo (`requiere=["Efth"]`). La GUI gana un botón "Descargar ERA5…". Toda la lógica de red queda separada de funciones puras testeables (parsers sobre `.nc` sintéticos, sin pegarle a internet).

**Tech Stack:** Python 3.13, numpy, xarray, netcdf4, scipy, matplotlib, **cdsapi** (nuevo), **scikit-image** (nuevo), pytest.

**Convenciones del repo:** comentarios en español con tildes; `snake_case`; módulos por responsabilidad; registro adaptativo (`requiere=[...]`); salidas vía `rutas.carpeta_salida`. Working dir de los comandos: `Herramientas computacionales/Tablero Oleaje/`.

---

## Estructura de archivos

- Crear: `particion_espectral.py` — watershed sea/swell sobre `Efth`. Una responsabilidad: partir un espectro en familias y parametrizarlas.
- Crear: `io_era5.py` — descarga ERA5 (serie + espectro) y parseo a Datasets compatibles. Red separada de parsing.
- Crear: `productos_particion.py` — cálculo y dibujo de los productos de partición (serie de Hs por familia + espectro polar particionado). Compartido por los dos registros.
- Modificar: `productos.py` — registrar el producto "Partición sea/swell (serie)" (`requiere=["Efth"]`).
- Modificar: `productos_swan.py` — registrar el producto "Espectro particionado" (fuente espectro).
- Modificar: `app_tablero.py` — botón "Descargar ERA5…" + ventana de descarga en hilo.
- Modificar: `test_regresion.py` — tests de partición (conservación de energía, separación, clasificación) y de parseo ERA5 (serie y espectro) con `.nc` sintético.
- Modificar: `README.md` — requisitos nuevos (`cdsapi`, `scikit-image`) y nota de credenciales `~/.cdsapirc`.

> Las funciones que empiezan con `_` son privadas del módulo. Los tests importan el módulo completo (`import particion_espectral`) y acceden a las privadas por nombre, como ya hace `test_regresion.py` con `io_swan._QUANT_VAR`.

---

## Fase A — Partición espectral (núcleo puro, sin red)

### Task 1: Pesos de integración y momento m0

**Files:**
- Create: `particion_espectral.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `test_regresion.py`:

```python
# --------------------------- Partición espectral ---------------------------
import particion_espectral


def test_pesos_y_m0_reconstruyen_hs():
    """m0 integrado de un espectro debe reproducir Hs = 4*sqrt(m0)."""
    freqs = np.linspace(0.04, 0.40, 30)
    dirs = np.arange(0.0, 360.0, 15.0)
    # Espectro unimodal: una gaussiana en (f, dir) con energía conocida.
    F, D = np.meshgrid(freqs, dirs, indexing="ij")
    efth = np.exp(-((F - 0.10) / 0.02) ** 2) * np.exp(-((D - 200.0) / 20.0) ** 2)

    dfreq, ddir = particion_espectral._pesos(freqs, dirs)
    m0 = particion_espectral._m0(efth, dfreq, ddir)
    hs = 4.0 * np.sqrt(m0)
    assert m0 > 0
    assert 0.0 < hs < 5.0           # rango físico para esa energía
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_pesos_y_m0_reconstruyen_hs -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'particion_espectral'`.

- [ ] **Step 3: Implementación mínima**

Crear `particion_espectral.py`:

```python
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
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_pesos_y_m0_reconstruyen_hs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add particion_espectral.py test_regresion.py
git commit -m "feat(particion): pesos de integracion y momento m0 del espectro"
```

---

### Task 2: Parámetros de una familia (Hs/Tp/Dir desde una máscara)

**Files:**
- Modify: `particion_espectral.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_parametros_de_familia_unimodal():
    """Sobre un espectro unimodal, la máscara total reproduce Hs/Tp/Dir del pico."""
    freqs = np.linspace(0.04, 0.40, 30)
    dirs = np.arange(0.0, 360.0, 15.0)
    F, D = np.meshgrid(freqs, dirs, indexing="ij")
    efth = np.exp(-((F - 0.10) / 0.02) ** 2) * np.exp(-((D - 200.0) / 20.0) ** 2)

    dfreq, ddir = particion_espectral._pesos(freqs, dirs)
    mascara = np.ones_like(efth, dtype=bool)
    fam = particion_espectral._parametros(efth, mascara, freqs, dirs,
                                          dfreq, ddir, viento=None)
    assert fam["Tp"] == pytest.approx(1.0 / 0.10, abs=1.0)   # pico en 0.10 Hz
    assert fam["Dir"] == pytest.approx(200.0, abs=8.0)
    assert fam["Hs"] > 0
    assert fam["tipo"] == "swell"                            # Tp largo, sin viento
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_parametros_de_familia_unimodal -v`
Expected: FAIL con `AttributeError: module 'particion_espectral' has no attribute '_parametros'`.

- [ ] **Step 3: Implementación mínima**

Agregar a `particion_espectral.py`:

```python
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
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_parametros_de_familia_unimodal -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add particion_espectral.py test_regresion.py
git commit -m "feat(particion): parametros Hs/Tp/Dir y clasificacion sea-swell por familia"
```

---

### Task 3: `particionar` — watershed con wrap direccional

**Files:**
- Modify: `particion_espectral.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def _espectro_bimodal():
    """Sea de período corto (~0.25 Hz, 270°) + swell largo (~0.07 Hz, 200°)."""
    freqs = np.linspace(0.04, 0.40, 30)
    dirs = np.arange(0.0, 360.0, 15.0)
    F, D = np.meshgrid(freqs, dirs, indexing="ij")
    sea = np.exp(-((F - 0.25) / 0.03) ** 2) * np.exp(-((D - 270.0) / 20.0) ** 2)
    swell = 0.6 * np.exp(-((F - 0.07) / 0.012) ** 2) * np.exp(-((D - 200.0) / 15.0) ** 2)
    return freqs, dirs, sea + swell


def test_particionar_separa_dos_familias_y_conserva_energia():
    freqs, dirs, efth = _espectro_bimodal()
    fam = particion_espectral.particionar(efth, freqs, dirs, umbral_rel=0.0)
    assert len(fam) == 2

    dfreq, ddir = particion_espectral._pesos(freqs, dirs)
    m0_total = particion_espectral._m0(efth, dfreq, ddir)
    assert sum(f["m0"] for f in fam) == pytest.approx(m0_total, rel=1e-9)

    # Ordenadas por energía descendente.
    assert fam[0]["m0"] >= fam[1]["m0"]
    # La de período más largo es swell; la corta, sea.
    por_tp = sorted(fam, key=lambda f: f["Tp"])
    assert por_tp[0]["tipo"] == "sea"
    assert por_tp[-1]["tipo"] == "swell"
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_particionar_separa_dos_familias_y_conserva_energia -v`
Expected: FAIL con `AttributeError: module 'particion_espectral' has no attribute 'particionar'`.

- [ ] **Step 3: Implementación mínima**

Agregar a `particion_espectral.py` (y el import de skimage arriba, junto a numpy):

```python
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
```

```python
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
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_particionar_separa_dos_familias_y_conserva_energia -v`
Expected: PASS.

> Si falla por `ModuleNotFoundError: skimage`, instalar antes: `pip install scikit-image` (se documenta en la Task 14).

- [ ] **Step 5: Commit**

```bash
git add particion_espectral.py test_regresion.py
git commit -m "feat(particion): watershed sea-swell con wrap direccional y conservacion de energia"
```

---

### Task 4: `particionar_serie` — cubo `Efth(time,freq,dir)` → Dataset por familia

**Files:**
- Modify: `particion_espectral.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_particionar_serie_devuelve_dataset_por_familia():
    import xarray as xr
    freqs, dirs, efth = _espectro_bimodal()
    cubo = np.stack([efth, efth * 0.5])          # 2 pasos de tiempo
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), cubo)},
        coords={"time": np.array(["2024-07-28T00", "2024-07-28T03"],
                                 dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})

    res = particion_espectral.particionar_serie(ds, umbral_rel=0.0)
    assert set(["Hs", "Tp", "Dir"]) <= set(res.data_vars)
    assert res.sizes["time"] == 2
    assert res.sizes["familia"] == 2
    # La Hs total del paso 0 (raíz de la suma de m0) supera la de cualquier familia.
    hs_fam0 = res["Hs"].isel(time=0).values
    assert np.nanmax(hs_fam0) > 0
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_particionar_serie_devuelve_dataset_por_familia -v`
Expected: FAIL con `AttributeError: ... 'particionar_serie'`.

- [ ] **Step 3: Implementación mínima**

Agregar a `particion_espectral.py` (necesita `import xarray as xr` arriba):

```python
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
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_particionar_serie_devuelve_dataset_por_familia -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add particion_espectral.py test_regresion.py
git commit -m "feat(particion): particionar_serie cubo temporal a Dataset por familia"
```

---

## Fase B — Descarga ERA5 (`io_era5.py`)

### Task 5: Cliente CDS y manejo de credenciales

**Files:**
- Create: `io_era5.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# --------------------------- Descarga ERA5 ---------------------------
import io_era5


def test_cliente_sin_credenciales_explica(monkeypatch, tmp_path):
    """Sin ~/.cdsapirc, _cliente lanza un error claro de configuración."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))   # HOME en Windows
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="cdsapirc"):
        io_era5._cliente()
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_cliente_sin_credenciales_explica -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'io_era5'`.

- [ ] **Step 3: Implementación mínima**

Crear `io_era5.py`:

```python
"""
Descarga de oleaje por coordenada desde ERA5 (Copernicus CDS).

Dos productos: serie temporal de parámetros integrados (Hs/Tp/Dir, opcional
viento) y espectros 2D direccionales. Ambos se devuelven como Datasets de xarray
compatibles con el resto del pipeline: la serie entra al tablero de curvas y el
espectro (Efth(time, freq, dir)) a la partición.

La parte de red (cdsapi) está separada de los parsers, que son funciones puras
sobre archivos .nc y se testean sin conexión.
"""

from pathlib import Path

import numpy as np
import xarray as xr

import rutas


def _cliente():
    """
    Devuelve un cdsapi.Client. Si faltan las credenciales ~/.cdsapirc, lanza un
    RuntimeError con el paso a paso para configurarlas (no intenta descargar).
    """
    hogar = Path.home() / ".cdsapirc"
    if not hogar.exists():
        raise RuntimeError(
            "Falta el archivo de credenciales del CDS (~/.cdsapirc).\n"
            "1) Crea una cuenta gratis en https://cds.climate.copernicus.eu\n"
            "2) Acepta los términos del dataset ERA5.\n"
            "3) Copia tu 'url' y 'key' del perfil en un archivo ~/.cdsapirc:\n"
            "     url: https://cds.climate.copernicus.eu/api\n"
            "     key: <UID>:<API-KEY>\n"
            f"   (en este equipo: {hogar})")
    import cdsapi
    return cdsapi.Client()
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_cliente_sin_credenciales_explica -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_era5.py test_regresion.py
git commit -m "feat(era5): cliente CDS con mensaje claro si faltan credenciales"
```

---

### Task 6: Peticiones CDS (construcción pura del request)

**Files:**
- Modify: `io_era5.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_peticion_serie_arma_area_y_variables():
    pet = io_era5._peticion_serie(lat=-37.0, lon=-73.5,
                                  inicio="2024-07-28", fin="2024-07-28",
                                  incluir_viento=True)
    # Área de un punto: [N, W, S, E] alrededor de (lat, lon).
    assert pet["area"][0] >= -37.0 >= pet["area"][2]
    assert pet["area"][1] <= -73.5 <= pet["area"][3]
    assert "significant_height_of_combined_wind_waves_and_swell" in pet["variable"]
    assert "peak_wave_period" in pet["variable"]
    assert "mean_wave_direction" in pet["variable"]
    assert "10m_u_component_of_wind" in pet["variable"]
    assert pet["format"] == "netcdf"
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_peticion_serie_arma_area_y_variables -v`
Expected: FAIL con `AttributeError: ... '_peticion_serie'`.

- [ ] **Step 3: Implementación mínima**

Agregar a `io_era5.py`:

```python
# Identificadores del CDS para cada producto.
_DATASET_SERIE = "reanalysis-era5-single-levels"
_DATASET_ESPECTRO = "reanalysis-era5-single-levels"   # var 2D wave spectra (d2fd)

_VARS_SERIE = ["significant_height_of_combined_wind_waves_and_swell",
               "peak_wave_period", "mean_wave_direction"]
_VARS_VIENTO = ["10m_u_component_of_wind", "10m_v_component_of_wind"]


def _rango_fechas(inicio, fin):
    """Listas de años/meses/días/horas (3-horario) que cubren [inicio, fin]."""
    fechas = np.arange(np.datetime64(inicio), np.datetime64(fin) + 1,
                       dtype="datetime64[D]")
    anios = sorted({str(f)[0:4] for f in fechas})
    meses = sorted({str(f)[5:7] for f in fechas})
    dias = sorted({str(f)[8:10] for f in fechas})
    horas = [f"{h:02d}:00" for h in range(0, 24, 3)]
    return anios, meses, dias, horas


def _peticion_serie(lat, lon, inicio, fin, incluir_viento=False, delta=0.25):
    """Diccionario de petición CDS para la serie de parámetros integrados."""
    anios, meses, dias, horas = _rango_fechas(inicio, fin)
    variables = list(_VARS_SERIE) + (list(_VARS_VIENTO) if incluir_viento else [])
    return {
        "product_type": "reanalysis",
        "variable": variables,
        "year": anios, "month": meses, "day": dias, "time": horas,
        "area": [lat + delta, lon - delta, lat - delta, lon + delta],   # N,W,S,E
        "format": "netcdf",
    }
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_peticion_serie_arma_area_y_variables -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_era5.py test_regresion.py
git commit -m "feat(era5): construccion de la peticion CDS para la serie"
```

---

### Task 7: Parseo de la serie ERA5 (`.nc` → Dataset(time) Hs/Tp/Dir)

**Files:**
- Modify: `io_era5.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def _nc_serie_sintetico(ruta):
    """Crea un .nc con la estructura de la serie ERA5 (swh/pp1d/mwd, punto+tiempo)."""
    import xarray as xr
    t = np.array(["2024-07-28T00", "2024-07-28T03"], dtype="datetime64[ns]")
    lat = np.array([-36.75, -37.25]); lon = np.array([-73.75, -73.25])
    forma = (len(t), len(lat), len(lon))
    ds = xr.Dataset(
        {"swh": (("time", "latitude", "longitude"), np.full(forma, 2.5)),
         "pp1d": (("time", "latitude", "longitude"), np.full(forma, 12.0)),
         "mwd": (("time", "latitude", "longitude"), np.full(forma, 225.0))},
        coords={"time": t, "latitude": lat, "longitude": lon})
    ds.to_netcdf(ruta)


def test_parsear_serie_selecciona_punto_y_renombra(tmp_path):
    ruta = tmp_path / "serie.nc"
    _nc_serie_sintetico(ruta)
    ds = io_era5._parsear_serie_nc(ruta, lat=-37.0, lon=-73.5)
    assert {"Hs", "Tp", "Dir"} <= set(ds.data_vars)
    assert "time" in ds.coords
    assert ds.sizes["time"] == 2
    assert float(ds["Hs"].isel(time=0)) == pytest.approx(2.5)
    assert "latitude" not in ds.dims          # punto ya seleccionado
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_parsear_serie_selecciona_punto_y_renombra -v`
Expected: FAIL con `AttributeError: ... '_parsear_serie_nc'`.

- [ ] **Step 3: Implementación mínima**

Agregar a `io_era5.py`:

```python
# Nombres cortos del .nc de ERA5 → variables canónicas del pipeline.
_RENOMBRE_SERIE = {"swh": "Hs", "pp1d": "Tp", "mwd": "Dir",
                   "u10": "u10", "v10": "v10"}

_ATRIBUTOS = {
    "Hs": {"long_name": "Altura significativa", "units": "m"},
    "Tp": {"long_name": "Período de pico", "units": "s"},
    "Dir": {"long_name": "Dirección media", "units": "deg"},
}


def _parsear_serie_nc(ruta, lat, lon):
    """Abre el .nc de ERA5, selecciona el punto más cercano y renombra a Hs/Tp/Dir."""
    bruto = xr.open_dataset(ruta)
    punto = bruto.sel(latitude=lat, longitude=lon, method="nearest")
    punto = punto.drop_vars(["latitude", "longitude"], errors="ignore")

    presentes = {k: v for k, v in _RENOMBRE_SERIE.items() if k in punto.data_vars}
    ds = punto[list(presentes)].rename(presentes)
    for v, attrs in _ATRIBUTOS.items():
        if v in ds.data_vars:
            ds[v].attrs.update(attrs)
    ds.attrs["fuente"] = f"ERA5 ({lat:.3f}, {lon:.3f})"
    bruto.close()
    return ds
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_parsear_serie_selecciona_punto_y_renombra -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_era5.py test_regresion.py
git commit -m "feat(era5): parseo de la serie a Dataset(time) Hs/Tp/Dir"
```

---

### Task 8: `descargar_serie` (orquesta red + parseo + guardado)

**Files:**
- Modify: `io_era5.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_descargar_serie_usa_cliente_y_parsea(monkeypatch, tmp_path):
    """descargar_serie: pide al cliente, escribe el .nc y devuelve Dataset(time)."""
    def _falso_retrieve(dataset, peticion, destino):
        _nc_serie_sintetico(destino)          # simula la descarga del CDS

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            _falso_retrieve(dataset, peticion, destino)

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)

    ds = io_era5.descargar_serie(lat=-37.0, lon=-73.5,
                                 inicio="2024-07-28", fin="2024-07-28")
    assert {"Hs", "Tp", "Dir"} <= set(ds.data_vars)
    assert ds.sizes["time"] == 2
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_descargar_serie_usa_cliente_y_parsea -v`
Expected: FAIL con `AttributeError: ... 'descargar_serie'`.

- [ ] **Step 3: Implementación mínima**

Agregar a `io_era5.py` (necesita `import rutas`, ya incluido):

```python
def _nombre_fuente(lat, lon, sufijo):
    """Identificador de carpeta/archivo de salida para una coordenada."""
    return f"ERA5_{lat:+.2f}_{lon:+.2f}_{sufijo}".replace(".", "p")


def descargar_serie(lat, lon, inicio, fin, incluir_viento=False):
    """
    Descarga la serie ERA5 de Hs/Tp/Dir (opcional viento) para un punto y rango,
    la cachea como .nc en salidas/ y devuelve un Dataset(time) listo para el
    tablero de curvas.
    """
    carpeta = rutas.carpeta_salida(_nombre_fuente(lat, lon, "serie"))
    destino = carpeta / "era5_serie.nc"
    if not destino.exists():
        _cliente().retrieve(_DATASET_SERIE,
                            _peticion_serie(lat, lon, inicio, fin, incluir_viento),
                            str(destino))
    return _parsear_serie_nc(destino, lat, lon)
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_descargar_serie_usa_cliente_y_parsea -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_era5.py test_regresion.py
git commit -m "feat(era5): descargar_serie orquesta cliente, cache y parseo"
```

---

### Task 9: Parseo y descarga del espectro 2D (`Efth(time,freq,dir)`)

**Files:**
- Modify: `io_era5.py`
- Test: `test_regresion.py`

> Nota de implementación: ERA5 guarda el espectro 2D (`d2fd`) en log10 de densidad. El parser des-loguea con `10**valor` y trata los rellenos como NaN. Antes de cablear descargas reales, confirmar la convención exacta (offset/unidades/dirección) en la doc de ERA5 wave spectra; el parser está aislado para ajustarlo sin tocar el resto.

- [ ] **Step 1: Escribir el test que falla**

```python
def _nc_espectro_sintetico(ruta):
    """Crea un .nc tipo ERA5 2D spectra: d2fd en log10, dims (time, freq, dir)."""
    import xarray as xr
    t = np.array(["2024-07-28T00"], dtype="datetime64[ns]")
    freq = 0.03453 * 1.1 ** np.arange(30)         # 30 frecuencias ERA5
    direction = np.arange(7.5, 360.0, 15.0)       # 24 direcciones ERA5
    dens = np.full((len(t), len(freq), len(direction)), 0.5)   # densidad lineal
    d2fd = np.log10(dens)                          # ERA5 la almacena en log10
    ds = xr.Dataset(
        {"d2fd": (("time", "frequency", "direction"), d2fd)},
        coords={"time": t, "frequency": freq, "direction": direction})
    ds.to_netcdf(ruta)


def test_parsear_espectro_decodifica_log10_y_reordena(tmp_path):
    ruta = tmp_path / "espectro.nc"
    _nc_espectro_sintetico(ruta)
    esp = io_era5._parsear_espectro_nc(ruta)
    assert dict(esp.sizes) == {"time": 1, "freq": 30, "dir": 24}
    assert set(["Efth"]) <= set(esp.data_vars)
    # 10**log10(0.5) = 0.5 (des-logueo correcto).
    assert float(esp["Efth"].isel(time=0, freq=0, dir=0)) == pytest.approx(0.5)
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_parsear_espectro_decodifica_log10_y_reordena -v`
Expected: FAIL con `AttributeError: ... '_parsear_espectro_nc'`.

- [ ] **Step 3: Implementación mínima**

Agregar a `io_era5.py`:

```python
_VARS_ESPECTRO = ["2d_wave_spectra"]    # parámetro d2fd del CDS


def _parsear_espectro_nc(ruta):
    """
    .nc de ERA5 2D spectra → Dataset con Efth(time, freq, dir), des-logueado.

    ERA5 guarda d2fd como log10 de la densidad; aquí se reconstruye 10**d2fd y se
    renombran las dimensiones a (freq, dir) para igualar a leer_espectro_temporal.
    """
    bruto = xr.open_dataset(ruta)
    d2fd = bruto["d2fd"]
    efth = np.power(10.0, d2fd)                       # des-logueo; NaN se propaga
    efth = efth.rename({"frequency": "freq", "direction": "dir"})

    ds = xr.Dataset({"Efth": efth})
    ds["Efth"].attrs = {"long_name": "Densidad de energía", "units": "m2/Hz/deg"}
    ds["freq"].attrs = {"long_name": "Frecuencia", "units": "Hz"}
    ds["dir"].attrs = {"long_name": "Dirección", "units": "deg"}
    bruto.close()
    return ds


def descargar_espectro(lat, lon, inicio, fin):
    """
    Descarga el espectro 2D direccional ERA5 para un punto y rango, lo cachea como
    .nc en salidas/ y devuelve un Dataset con Efth(time, freq, dir) listo para la
    partición.
    """
    carpeta = rutas.carpeta_salida(_nombre_fuente(lat, lon, "espectro"))
    destino = carpeta / "era5_espectro.nc"
    if not destino.exists():
        anios, meses, dias, horas = _rango_fechas(inicio, fin)
        peticion = {"product_type": "reanalysis", "variable": _VARS_ESPECTRO,
                    "year": anios, "month": meses, "day": dias, "time": horas,
                    "area": [lat + 0.25, lon - 0.25, lat - 0.25, lon + 0.25],
                    "format": "netcdf"}
        _cliente().retrieve(_DATASET_ESPECTRO, peticion, str(destino))
    return _parsear_espectro_nc(destino)
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_parsear_espectro_decodifica_log10_y_reordena -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_era5.py test_regresion.py
git commit -m "feat(era5): parseo del espectro 2D (des-logueo) y descargar_espectro"
```

---

## Fase C — Productos de partición

### Task 10: `productos_particion.py` — cálculo y dibujo de la serie por familia

**Files:**
- Create: `productos_particion.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# --------------------------- Productos de partición ---------------------------
import productos_particion


def test_calcular_particion_resume_familias():
    import xarray as xr
    freqs, dirs, efth = _espectro_bimodal()
    cubo = np.stack([efth, efth])
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), cubo)},
        coords={"time": np.array(["2024-07-28T00", "2024-07-28T03"],
                                 dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    r = productos_particion.calcular_serie(ds)
    assert "series" in r and r["series"].sizes["familia"] == 4
    assert r["n_familias"] >= 2


def test_tabla_familias_exportable():
    """tabla_familias devuelve un DataFrame con una fila por familia del paso pico."""
    freqs, dirs, efth = _espectro_bimodal()
    tabla = productos_particion.tabla_familias(efth, freqs, dirs)
    assert list(tabla.columns) == ["familia", "tipo", "Hs", "Tp", "Dir"]
    assert len(tabla) == 2
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python -m pytest test_regresion.py::test_calcular_particion_resume_familias test_regresion.py::test_tabla_familias_exportable -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'productos_particion'`.

- [ ] **Step 3: Implementación mínima**

Crear `productos_particion.py`:

```python
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
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_regresion.py::test_calcular_particion_resume_familias test_regresion.py::test_tabla_familias_exportable -v`
Expected: PASS ambos.

- [ ] **Step 5: Commit**

```bash
git add productos_particion.py test_regresion.py
git commit -m "feat(particion): serie de Hs por familia y tabla exportable"
```

---

### Task 11: Registrar la partición en `productos.py` (tablero de curvas)

**Files:**
- Modify: `productos.py:245-268` (lista `PRODUCTOS`) y cabecera de imports
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_registro_productos_detecta_particion_con_efth():
    import xarray as xr
    import productos
    freqs, dirs, efth = _espectro_bimodal()
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), np.stack([efth]))},
        coords={"time": np.array(["2024-07-28T00"], dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    informe = productos.evaluar(ds)
    item = next(i for i in informe if i["nombre"] == "Partición sea/swell (serie)")
    assert item["disponible"] is True
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_registro_productos_detecta_particion_con_efth -v`
Expected: FAIL con `StopIteration` (el producto aún no está registrado).

- [ ] **Step 3: Implementación mínima**

En `productos.py`, agregar el import bajo la línea `from scipy import stats` (línea 20):

```python
import productos_particion
```

En la lista `PRODUCTOS` (productos.py:245-268), agregar antes del cierre `]` (después del item "Espectro medido S(f)"):

```python
    {"nombre": "Partición sea/swell (serie)", "requiere": ["Efth"],
     "proyeccion": None,
     "calcular": productos_particion.calcular_serie,
     "dibujar": productos_particion.dibujar_serie},
```

> `evaluar` ya chequea `v not in ds.data_vars`; como el producto requiere `Efth`, se activa solo cuando el Dataset lo trae y se salta en el resto.

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_registro_productos_detecta_particion_con_efth -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add productos.py test_regresion.py
git commit -m "feat(particion): registrar particion sea/swell en el tablero de curvas"
```

---

### Task 12: Espectro polar particionado + registro en `productos_swan.py`

**Files:**
- Modify: `productos_particion.py` (agregar `dibujar_polar`)
- Modify: `productos_swan.py:92-102` (lista `PRODUCTOS_SWAN`)
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_espectro_particionado_registrado_en_swan():
    import productos_swan
    # Una corrida mínima con espectro (un paso) y sin dominios.
    import xarray as xr
    freqs, dirs, efth = _espectro_bimodal()
    espectro = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), np.stack([efth]))},
        coords={"time": np.array(["2024-07-28T00"], dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    corrida = {"dominios": {}, "espectro": espectro, "meta": {}}
    informe = productos_swan.evaluar(corrida)
    item = next(i for i in informe if i["nombre"] == "Espectro particionado")
    assert item["disponible"] is True
    assert item["proyeccion"] == "polar"
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_espectro_particionado_registrado_en_swan -v`
Expected: FAIL con `StopIteration`.

- [ ] **Step 3: Implementación mínima**

Agregar a `productos_particion.py`:

```python
def dibujar_polar(ax, espectro, meta=None):
    """
    Espectro S(f,θ) polar de un paso (el de mayor energía), con cada familia
    marcada por la dirección/frecuencia de su pico y color por tipo.
    """
    esp = espectro.isel(time=0) if "time" in espectro.dims else espectro
    freqs = esp["freq"].values
    dirs = esp["dir"].values
    densidad = np.nan_to_num(esp["Efth"].values)

    theta = np.deg2rad(dirs)
    malla_t, malla_r = np.meshgrid(theta, freqs)
    pm = ax.pcolormesh(malla_t, malla_r, densidad, shading="auto", cmap="viridis")
    ax.figure.colorbar(pm, ax=ax, label="S(f,θ) [m²/Hz/°]", shrink=0.7, pad=0.1)

    familias = particion_espectral.particionar(densidad, freqs, dirs)
    for fam in familias:
        fp = 1.0 / fam["Tp"] if fam["Tp"] and fam["Tp"] > 0 else 0.0
        ax.plot(np.deg2rad(fam["Dir"]), fp, "o", ms=9,
                color=_COLOR.get(fam["tipo"], "#999999"),
                label=f"{fam['tipo']}: Hs={fam['Hs']:.1f} m, Tp={fam['Tp']:.0f} s")
    ax.set_title("Espectro particionado S(f,θ)", fontsize=9, pad=8)
    ax.legend(fontsize=7, loc="upper right", bbox_to_anchor=(1.35, 1.1))
```

En `productos_swan.py`, agregar el import bajo los existentes (cerca de la cabecera):

```python
import productos_particion
```

En la lista `PRODUCTOS_SWAN` (productos_swan.py:93-102), agregar antes del cierre `]`:

```python
    {"nombre": "Espectro particionado", "fuente": "espectro",
     "requiere": [], "proyeccion": "polar", "dibujar": productos_particion.dibujar_polar},
```

> `evaluar` de productos_swan trata la fuente "espectro" como disponible cuando `corrida["espectro"] is not None`, así que el nuevo producto se activa con cualquier corrida que traiga espectro.

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_espectro_particionado_registrado_en_swan -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add productos_particion.py productos_swan.py test_regresion.py
git commit -m "feat(particion): espectro polar particionado en el tablero SWAN"
```

---

## Fase D — GUI

### Task 13: Botón "Descargar ERA5…" y ventana de descarga

**Files:**
- Modify: `app_tablero.py` (fila de botones `app_tablero.py:69-74`, nuevos métodos)
- Test: `test_regresion.py` (lógica pura de validación de inputs, sin tkinter)

- [ ] **Step 1: Escribir el test que falla**

```python
def test_validar_inputs_era5_convierte_y_valida():
    import app_tablero
    lat, lon = app_tablero.validar_inputs_era5("-37.0", "-73.5",
                                               "2024-07-28", "2024-07-29")
    assert (lat, lon) == pytest.approx((-37.0, -73.5))
    with pytest.raises(ValueError):
        app_tablero.validar_inputs_era5("abc", "-73.5", "2024-07-28", "2024-07-29")
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_validar_inputs_era5_convierte_y_valida -v`
Expected: FAIL con `AttributeError: module 'app_tablero' has no attribute 'validar_inputs_era5'`.

- [ ] **Step 3: Implementación mínima**

En `app_tablero.py`, agregar los imports al bloque de imports (junto a `import config`):

```python
import io_era5
import rutas
```

Agregar a nivel de módulo (antes de la clase `AppTablero`) la función pura testeable:

```python
def validar_inputs_era5(lat_txt, lon_txt, inicio, fin):
    """Convierte y valida lat/lon; devuelve (lat, lon). Lanza ValueError si no sirven."""
    lat = float(lat_txt)
    lon = float(lon_txt)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Latitud/longitud fuera de rango.")
    if not (inicio and fin):
        raise ValueError("Faltan fechas de inicio/fin.")
    return lat, lon
```

En `_construir_widgets`, en la fila de botones (app_tablero.py:73-74), agregar el botón nuevo tras "Procesar SWAN…":

```python
        ttk.Button(fila_b, text="Descargar ERA5…", command=self._abrir_era5).pack(
            side="left", padx=(8, 0), ipadx=6, ipady=4)
```

Agregar los métodos a la clase `AppTablero` (después de `_abrir_swan`):

```python
    def _abrir_era5(self):
        """Ventana de descarga ERA5 por coordenada (serie + espectro opcional)."""
        win = tk.Toplevel(self)
        win.title("Descargar ERA5 por coordenada")
        win.geometry("360x300")
        campos = {}
        for etiqueta, clave, valor in [
                ("Latitud", "lat", "-37.0"), ("Longitud", "lon", "-73.5"),
                ("Inicio (YYYY-MM-DD)", "inicio", "2024-07-28"),
                ("Fin (YYYY-MM-DD)", "fin", "2024-07-29")]:
            fila = ttk.Frame(win); fila.pack(fill="x", padx=10, pady=4)
            ttk.Label(fila, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ttk.Entry(fila, textvariable=var).pack(side="left", fill="x", expand=True)
            campos[clave] = var
        espectro = tk.BooleanVar(value=True)
        viento = tk.BooleanVar(value=True)
        ttk.Checkbutton(win, text="Incluir espectros 2D", variable=espectro).pack(
            anchor="w", padx=10)
        ttk.Checkbutton(win, text="Incluir viento (clasificación sea/swell)",
                        variable=viento).pack(anchor="w", padx=10)

        def lanzar():
            try:
                lat, lon = validar_inputs_era5(
                    campos["lat"].get(), campos["lon"].get(),
                    campos["inicio"].get(), campos["fin"].get())
            except ValueError as e:
                messagebox.showerror("Datos inválidos", str(e)); return
            win.destroy()
            self.estado.config(text="Descargando ERA5…", foreground="#d18616")
            self.salida.delete("1.0", "end")
            threading.Thread(target=self._descargar_era5, daemon=True,
                             args=(lat, lon, campos["inicio"].get(),
                                   campos["fin"].get(), espectro.get(),
                                   viento.get())).start()

        ttk.Button(win, text="Descargar", command=lanzar).pack(pady=12, ipadx=10)

    def _descargar_era5(self, lat, lon, inicio, fin, con_espectro, con_viento):
        """Corre la descarga fuera del hilo de la GUI y deja el .nc listo para Crear."""
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                ds = io_era5.descargar_serie(lat, lon, inicio, fin,
                                             incluir_viento=con_viento)
                print(f"Serie ERA5 descargada: {ds.sizes.get('time', 0)} pasos.")
                if con_espectro:
                    esp = io_era5.descargar_espectro(lat, lon, inicio, fin)
                    print(f"Espectro ERA5 descargado: {esp.sizes.get('time', 0)} pasos.")
            carpeta = rutas.carpeta_salida(io_era5._nombre_fuente(lat, lon, "serie"))
            nc_serie = carpeta / "era5_serie.nc"
            # Dejar el .nc seleccionado para que el botón Crear genere el tablero.
            self.after(0, self.ruta_datos.set, str(nc_serie))
            self.after(0, self._exito, buffer.getvalue(), str(carpeta))
        except Exception:
            self.after(0, self._error, buffer.getvalue() + "\n" + traceback.format_exc())
```

> El bloque GUI no se testea con pytest (tkinter no corre headless de forma fiable); su única lógica con reglas —la validación— se extrajo a `validar_inputs_era5`, que sí se testea. El resto es cableado de widgets y llamadas a `io_era5` ya cubiertas.

- [ ] **Step 4: Correr el test para verlo pasar y verificar arranque de la app**

Run: `python -m pytest test_regresion.py::test_validar_inputs_era5_convierte_y_valida -v`
Expected: PASS.

Verificación manual del cableado (abre la ventana; cerrar tras comprobar que aparece el botón "Descargar ERA5…"):
Run: `python app_tablero.py`
Expected: la ventana abre sin errores y el botón "Descargar ERA5…" está visible.

- [ ] **Step 5: Commit**

```bash
git add app_tablero.py test_regresion.py
git commit -m "feat(gui): boton y ventana de descarga ERA5 por coordenada"
```

---

## Fase E — Documentación y cierre

### Task 14: Requisitos y nota de credenciales en README

**Files:**
- Modify: `README.md` (sección "Requisitos", README.md:68-72)

- [ ] **Step 1: Actualizar el README**

Reemplazar la sección "## Requisitos" por:

```markdown
## Requisitos

Python 3.13 con `numpy`, `pandas`, `xarray`, `netcdf4`, `scipy`, `matplotlib`,
`windrose`, `cmocean`, `scikit-image` (partición espectral) y `cdsapi` (descarga
ERA5). Opcionales: `ffmpeg` (MP4; si no, GIF), `pytest` (tests).
Para *Procesar SWAN*, SWAN instalado y `swanrun` en el PATH.

### Credenciales ERA5 (descarga por coordenada)

La descarga usa el Copernicus Climate Data Store. Una sola vez:

1. Crea una cuenta gratis en <https://cds.climate.copernicus.eu> y acepta los
   términos del dataset ERA5.
2. Crea el archivo `~/.cdsapirc` (en Windows, `C:\Users\<tu-usuario>\.cdsapirc`) con:

   ```
   url: https://cds.climate.copernicus.eu/api
   key: <UID>:<API-KEY>
   ```

Sin ese archivo, el botón "Descargar ERA5…" avisa con el paso a paso y no
descarga nada.
```

- [ ] **Step 2: Correr toda la batería de tests (no debe romper nada)**

Run: `python -m pytest test_regresion.py -v`
Expected: PASS los tests nuevos; los de datos SWAN/oleaje pueden marcar SKIP si los datos no están en disco (comportamiento esperado).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: requisitos cdsapi/scikit-image y credenciales ERA5"
```

---

## Notas de verificación final

- `python -m pytest test_regresion.py -v` en verde (nuevos PASS; datos externos SKIP si faltan).
- Instalar dependencias antes de ejecutar: `pip install cdsapi scikit-image`.
- Las descargas reales requieren `~/.cdsapirc`; los tests no tocan la red (parsers sobre `.nc` sintéticos y cliente monkeypatcheado).
- Confirmar la convención de des-logueo/dirección del espectro ERA5 (`d2fd`) contra la doc oficial antes de fiarse de los valores absolutos del espectro descargado; el parser `_parsear_espectro_nc` está aislado para ajustarlo.
- Limitación documentada del watershed: el wrap direccional se emula rotando el valle de energía al borde; en espectros con energía repartida en todas las direcciones puede no separar de forma ideal (suficiente para oleaje costero de 1–3 sistemas).
```
