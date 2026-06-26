# Batimetría automática → `.bot` — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generar el `.bot` de un caso SWAN automáticamente desde la malla de cómputo, descargando batimetría global (GEBCO/ETOPO) por coordenadas o usando un raster propio, con un botón en el formulario "Armar y correr".

**Architecture:** Un módulo motor puro `io_batimetria.py` (proyecta la malla UTM a lat/lon, muestrea un raster de batimetría e escribe el `.bot` con la convención de `io_swan`), más un campo "Zona UTM" y un botón en `gui_swan`. La descarga (red) se aísla de la lógica pura, que se testea con rasters sintéticos.

**Tech Stack:** Python 3.13, numpy, scipy (interpolación), pyproj (UTM↔lat/lon), xarray/netcdf4 (raster), tkinter, pytest.

**Convenciones del repo:** comentarios en español con tildes; `snake_case`; un módulo por responsabilidad; tests al final de `test_regresion.py`; `python -m pytest` (no `pytest`). Working dir: `Herramientas computacionales/Tablero Oleaje/`. Commits: añadir al final del mensaje, en su propia línea, `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`; NO push.

---

## Estructura de archivos

- Crear: `io_batimetria.py` — `epsg_utm`, `_normalizar_raster`, `_url_erddap`, `descargar_raster`, `leer_raster_local`, `generar_bot`.
- Modify: `gui_swan.py` — `import io_batimetria`; campo "Zona UTM" en `_pestana_nuevo`; botón "Generar batimetría…"; métodos `_generar_batimetria` y `_bati_worker`.
- Modify: `test_regresion.py` — tests del motor.

**Fases para subagentes:** Fase 1 = Tasks 1–4 (`io_batimetria.py`). Fase 2 = Task 5 (GUI).

**Convención del `.bot` (de `io_swan._construir_dataset`):** se lee como
`np.flipud(bat.reshape(ny, nx))` con `nx = mxc+1`, `ny = myc+1`, coords
`x = xpc + i·dx` (oeste→este), `y = ypc + j·dy` (sur→norte). Para escribir:
`bat = np.flipud(D).ravel()`, con `D[j,i]` = profundidad del nodo (x_i, y_j),
j sur→norte. SWAN: profundidad **positiva hacia abajo** ⇒ `depth = −elevation`.

---

## Task 1: `epsg_utm`

**Files:**
- Create: `io_batimetria.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `test_regresion.py`:

```python
# --------------------------- Batimetría automática ---------------------------
import io_batimetria


def test_epsg_utm_parsea_zona():
    assert io_batimetria.epsg_utm("19S") == 32719
    assert io_batimetria.epsg_utm("18S") == 32718
    assert io_batimetria.epsg_utm("19N") == 32619
    assert io_batimetria.epsg_utm(" 18s ") == 32718      # tolerante a espacios/caso
    with pytest.raises(ValueError):
        io_batimetria.epsg_utm("ABC")
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_epsg_utm_parsea_zona -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'io_batimetria'`.

- [ ] **Step 3: Implementación mínima**

Crear `io_batimetria.py`:

```python
"""
Genera la batimetría (.bot) de un caso SWAN a partir de la malla de cómputo.

Proyecta los nodos de la malla (UTM) a lat/lon, muestrea un raster de batimetría
(descargado de GEBCO/ETOPO por coordenadas, o uno local) e escribe el .bot con la
misma convención que lee io_swan (reshape + flipud). SWAN usa profundidad positiva
hacia abajo, así que depth = -elevation.

La parte de red (descarga) está aislada de la lógica pura, que se testea con
rasters sintéticos sin tocar internet.
"""

import re
from pathlib import Path

import numpy as np
import xarray as xr


def epsg_utm(zona):
    """
    EPSG de una zona UTM: '19S'->32719, '18S'->32718, '19N'->32619.
    Lanza ValueError si la cadena no es una zona válida.
    """
    texto = str(zona).strip().upper()
    m = re.fullmatch(r"(\d{1,2})\s*([NS])", texto)
    if not m:
        raise ValueError(f"Zona UTM inválida: {zona!r} (usa p. ej. '19S').")
    numero = int(m.group(1))
    if not 1 <= numero <= 60:
        raise ValueError(f"Huso UTM fuera de rango: {numero}")
    return (32700 if m.group(2) == "S" else 32600) + numero
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_epsg_utm_parsea_zona -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_batimetria.py test_regresion.py
git commit -m "feat(bati): epsg_utm parsea la zona UTM a codigo EPSG"
```

---

## Task 2: `_normalizar_raster`

**Files:**
- Modify: `io_batimetria.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_normalizar_raster_etopo_y_gebco():
    import xarray as xr
    lat = np.array([-32.9, -33.0, -33.1])      # descendente (como ETOPO)
    lon = np.array([-71.8, -71.7, -71.6])
    alt = np.arange(9).reshape(3, 3).astype(float)

    etopo = xr.Dataset({"altitude": (("latitude", "longitude"), alt)},
                       coords={"latitude": lat, "longitude": lon})
    out = io_batimetria._normalizar_raster(etopo)
    assert "elevation" in out.data_vars
    assert "lat" in out.dims and "lon" in out.dims
    assert float(out["lat"][0]) < float(out["lat"][-1])    # ordenado ascendente

    gebco = xr.Dataset({"elevation": (("lat", "lon"), alt)},
                       coords={"lat": lat[::-1], "lon": lon})
    out2 = io_batimetria._normalizar_raster(gebco)
    assert "elevation" in out2.data_vars and "lat" in out2.dims
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_normalizar_raster_etopo_y_gebco -v`
Expected: FAIL con `AttributeError: module 'io_batimetria' has no attribute '_normalizar_raster'`.

- [ ] **Step 3: Implementación**

Agregar a `io_batimetria.py`:

```python
_ALIAS_LAT = ("lat", "latitude", "y")
_ALIAS_LON = ("lon", "longitude", "x")
_ALIAS_ELEV = ("elevation", "altitude", "z")


def _normalizar_raster(ds):
    """
    Deja el raster con dimensiones 'lat'/'lon' (ascendentes) y la variable de
    elevación llamada 'elevation' (m, positivo hacia arriba), venga de ETOPO
    (altitude/latitude/longitude) o GEBCO (elevation/lat/lon).
    """
    ren = {}
    for cand in _ALIAS_LAT:
        if cand in ds.variables and cand != "lat":
            ren[cand] = "lat"
            break
    for cand in _ALIAS_LON:
        if cand in ds.variables and cand != "lon":
            ren[cand] = "lon"
            break
    var = next((v for v in _ALIAS_ELEV if v in ds.data_vars), None)
    if var is None:
        raise ValueError(
            f"El raster no tiene variable de elevación reconocible (busqué {_ALIAS_ELEV}).")
    if var != "elevation":
        ren[var] = "elevation"
    ds = ds.rename(ren)
    return ds[["elevation"]].sortby("lat").sortby("lon")
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_normalizar_raster_etopo_y_gebco -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_batimetria.py test_regresion.py
git commit -m "feat(bati): normalizar raster (ETOPO/GEBCO) a lat/lon/elevation"
```

---

## Task 3: `generar_bot` (con raster dado)

**Files:**
- Modify: `io_batimetria.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
def _raster_sintetico(elev_func):
    """Raster lat/lon (50×50) sobre Reñaca con elevation = elev_func(LAT, LON)."""
    import xarray as xr
    lat = np.linspace(-33.2, -32.8, 50)
    lon = np.linspace(-71.9, -71.4, 50)
    LAT, LON = np.meshgrid(lat, lon, indexing="ij")
    return xr.Dataset({"elevation": (("lat", "lon"), elev_func(LAT, LON))},
                      coords={"lat": lat, "lon": lon})


def test_generar_bot_signo_y_cantidad(tmp_path):
    raster = _raster_sintetico(lambda LAT, LON: np.full_like(LAT, -50.0))  # 50 m mar
    malla = {"xpc": 250000.0, "ypc": 6340000.0, "xlenc": 2000.0,
             "ylenc": 2000.0, "mxc": 5, "myc": 5}
    ruta, meta = io_batimetria.generar_bot(malla, "19S", tmp_path, raster=raster)
    bat = np.array(ruta.read_text().split(), dtype=float)
    assert bat.size == (5 + 1) * (5 + 1)                 # (mxc+1)·(myc+1)
    assert np.allclose(bat, 50.0, atol=1.0)              # depth = -(-50) = 50 m
    assert meta["prof_min"] > 0


def test_generar_bot_orientacion_norte_sur(tmp_path):
    # elevation crece con la latitud (más al norte = más alto) → depth menor al norte.
    raster = _raster_sintetico(lambda LAT, LON: (LAT + 33.0) * 1000.0)
    malla = {"xpc": 250000.0, "ypc": 6340000.0, "xlenc": 4000.0,
             "ylenc": 4000.0, "mxc": 8, "myc": 10}
    ruta, meta = io_batimetria.generar_bot(malla, "19S", tmp_path, raster=raster)
    bat = np.array(ruta.read_text().split(), dtype=float)
    ny, nx = 10 + 1, 8 + 1
    # io_swan reconstruye depth así; la fila norte (índice -1) debe ser menos profunda.
    depth = np.flipud(bat.reshape(ny, nx))
    assert depth[-1, :].mean() < depth[0, :].mean()
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python -m pytest test_regresion.py::test_generar_bot_signo_y_cantidad test_regresion.py::test_generar_bot_orientacion_norte_sur -v`
Expected: FAIL con `AttributeError: module 'io_batimetria' has no attribute 'generar_bot'`.

- [ ] **Step 3: Implementación**

Agregar a `io_batimetria.py`:

```python
def generar_bot(malla, zona_utm, carpeta, raster=None, nombre="bati.bot", margen=0.05):
    """
    Escribe el .bot de la malla (UTM) muestreando un raster de batimetría.

    malla: dict {xpc, ypc, xlenc, ylenc, mxc, myc}. zona_utm: p. ej. '19S'.
    raster: Dataset normalizado (lat/lon/elevation); si None, se descarga por bbox.
    Devuelve (ruta_bot, meta) con meta = {n_nodos, prof_min, prof_max, pct_tierra, epsg}.
    """
    from pyproj import Transformer
    from scipy.interpolate import RegularGridInterpolator

    mxc, myc = int(malla["mxc"]), int(malla["myc"])
    nx, ny = mxc + 1, myc + 1
    dx = float(malla["xlenc"]) / mxc
    dy = float(malla["ylenc"]) / myc
    xs = float(malla["xpc"]) + np.arange(nx) * dx       # oeste→este
    ys = float(malla["ypc"]) + np.arange(ny) * dy       # sur→norte
    gx, gy = np.meshgrid(xs, ys)                        # (ny, nx)

    epsg = epsg_utm(zona_utm)
    a_geo = Transformer.from_crs(epsg, 4326, always_xy=True)
    lon_nodos, lat_nodos = a_geo.transform(gx, gy)      # (ny, nx)

    carpeta = Path(carpeta)
    if raster is None:
        raster = descargar_raster(float(lat_nodos.min()) - margen,
                                  float(lat_nodos.max()) + margen,
                                  float(lon_nodos.min()) - margen,
                                  float(lon_nodos.max()) + margen,
                                  carpeta / "_raster_bati.nc")

    lats = raster["lat"].values
    lons = raster["lon"].values
    elev = np.asarray(raster["elevation"].values, dtype=float)
    interp = RegularGridInterpolator((lats, lons), elev,
                                     bounds_error=False, fill_value=None)
    # Recortar al rango del raster: en los bordes usa el valor del borde (no extrapola).
    plat = np.clip(lat_nodos.ravel(), lats.min(), lats.max())
    plon = np.clip(lon_nodos.ravel(), lons.min(), lons.max())
    elev_nodos = interp(np.column_stack([plat, plon])).reshape(ny, nx)
    depth = -elev_nodos                                 # SWAN: profundidad +hacia abajo

    bat = np.flipud(depth).ravel()                      # convención inversa de io_swan
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_text("\n".join(f"{v:.2f}" for v in bat))

    meta = {"n_nodos": int(bat.size),
            "prof_min": float(np.nanmin(depth)), "prof_max": float(np.nanmax(depth)),
            "pct_tierra": float(np.mean(depth <= 0) * 100.0), "epsg": epsg}
    return ruta, meta
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_regresion.py::test_generar_bot_signo_y_cantidad test_regresion.py::test_generar_bot_orientacion_norte_sur -v`
Expected: PASS ambos.

- [ ] **Step 5: Commit**

```bash
git add io_batimetria.py test_regresion.py
git commit -m "feat(bati): generar_bot proyecta malla UTM, interpola y escribe el .bot"
```

---

## Task 4: `_url_erddap` + `descargar_raster` + `leer_raster_local`

**Files:**
- Modify: `io_batimetria.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_url_erddap_arma_bbox():
    url = io_batimetria._url_erddap(-33.1, -32.9, -71.8, -71.5)
    assert url.startswith("https://")
    assert "etopo180.nc?altitude" in url
    assert "-33.1" in url and "-71.5" in url
```

(La descarga real y `leer_raster_local` se verifican manualmente: no hay test de red.)

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_url_erddap_arma_bbox -v`
Expected: FAIL con `AttributeError: module 'io_batimetria' has no attribute '_url_erddap'`.

- [ ] **Step 3: Implementación**

Agregar a `io_batimetria.py`:

```python
# Fuente de batimetría global (ERDDAP de NOAA). ETOPO1 (~1.85 km) confirmado
# estable; cambiar a un dataset más fino si se valida su id/variable.
_BASE_ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
_DATASET_ERDDAP = "etopo180"
_VAR_ERDDAP = "altitude"


def _url_erddap(lat_min, lat_max, lon_min, lon_max):
    """URL ERDDAP (.nc) del recorte por bbox del dataset de batimetría."""
    rango = (f"%5B({lat_min}):({lat_max})%5D"
             f"%5B({lon_min}):({lon_max})%5D")
    return f"{_BASE_ERDDAP}/{_DATASET_ERDDAP}.nc?{_VAR_ERDDAP}{rango}"


def descargar_raster(lat_min, lat_max, lon_min, lon_max, destino):
    """Descarga el recorte de batimetría por HTTP y lo devuelve normalizado."""
    import urllib.request
    url = _url_erddap(lat_min, lat_max, lon_min, lon_max)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, destino)
    except Exception as e:
        raise RuntimeError(
            "No se pudo descargar la batimetría (¿sin internet?). "
            "Usa un archivo de batimetría local.") from e
    return _normalizar_raster(xr.open_dataset(destino))


def leer_raster_local(ruta):
    """Abre un raster de batimetría propio (.nc) y lo devuelve normalizado."""
    return _normalizar_raster(xr.open_dataset(ruta))
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_url_erddap_arma_bbox -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add io_batimetria.py test_regresion.py
git commit -m "feat(bati): descarga ERDDAP por bbox y lectura de raster local"
```

---

## Task 5: GUI — campo "Zona UTM" y botón "Generar batimetría…"

**Files:**
- Modify: `gui_swan.py` (import, `_pestana_nuevo`, métodos nuevos)
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_gui_swan_expone_generar_batimetria():
    import gui_swan
    assert hasattr(gui_swan.VentanaSwan, "_generar_batimetria")
    assert hasattr(gui_swan.VentanaSwan, "_bati_worker")
    import io_batimetria
    assert callable(io_batimetria.generar_bot)
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_gui_swan_expone_generar_batimetria -v`
Expected: FAIL con `AttributeError: ... has no attribute '_generar_batimetria'`.

- [ ] **Step 3: Implementación**

(a) En la cabecera de imports de `gui_swan.py`, agregar:

```python
import io_batimetria
```

(b) En `_pestana_nuevo`, en la fila de celdas `m2` (después de `campo(m2, "Celdas Y", "myc", 120)`), agregar el campo de zona:

```python
        campo(m2, "Zona UTM", "zona_utm", "19S", ancho=6)
```

(c) En `_pestana_nuevo`, en la fila de batimetría `bat` (después del botón `"…"` que llama `self._elegir_bot`), agregar el botón:

```python
        ttk.Button(bat, text="Generar batimetría…",
                   command=self._generar_batimetria).pack(side="left", padx=(6, 0))
```

(d) Agregar los dos métodos a la clase `VentanaSwan` (junto a las otras acciones):

```python
    def _generar_batimetria(self):
        """Genera el .bot desde la malla (descarga GEBCO/ETOPO o usa raster local)."""
        try:
            malla = {k: float(self.v[k].get())
                     for k in ("xpc", "ypc", "xlenc", "ylenc")}
            malla["mxc"] = int(float(self.v["mxc"].get()))
            malla["myc"] = int(float(self.v["myc"].get()))
            zona = self.v["zona_utm"].get()
        except (ValueError, KeyError) as e:
            messagebox.showerror("Malla inválida",
                                 f"Revisa los campos de malla/zona: {e}")
            return
        destino = self.dest_nuevo.get().strip()
        if not destino:
            messagebox.showwarning("Falta carpeta",
                                   "Elige la carpeta destino del caso primero.")
            return
        raster = None
        if messagebox.askyesno(
                "Batimetría",
                "¿Usar un archivo de batimetría local?\n"
                "Sí = elegir un .nc propio (SHOA u otro)\n"
                "No = descargar GEBCO/ETOPO automáticamente"):
            ruta_r = filedialog.askopenfilename(
                title="Raster de batimetría (.nc)",
                filetypes=[("NetCDF", "*.nc"), ("Todos", "*.*")])
            if not ruta_r:
                return
            try:
                raster = io_batimetria.leer_raster_local(ruta_r)
            except Exception as e:
                messagebox.showerror("Raster inválido", str(e))
                return
        self.log.insert("end", "Generando batimetría…\n")
        self.log.see("end")
        threading.Thread(target=self._bati_worker, daemon=True,
                         args=(malla, zona, destino, raster)).start()

    def _bati_worker(self, malla, zona, destino, raster):
        """Corre generar_bot fuera del hilo de la GUI y rellena el campo .bot."""
        try:
            ruta, meta = io_batimetria.generar_bot(malla, zona, destino, raster=raster)
        except Exception as e:
            self.after(0, lambda: self.log.insert("end", f"Error batimetría: {e}\n"))
            return

        def ok():
            self.bat_archivo.set(str(ruta))
            self.log.insert(
                "end",
                f"Batimetría lista: {ruta.name} — profundidad "
                f"{meta['prof_min']:.1f} a {meta['prof_max']:.1f} m, "
                f"{meta['pct_tierra']:.0f}% en tierra.\n")
            self.log.see("end")
        self.after(0, ok)
```

- [ ] **Step 4: Correr el test y verificar import**

Run: `python -m pytest test_regresion.py::test_gui_swan_expone_generar_batimetria -v`
Expected: PASS.
Run: `python -c "import gui_swan, app_tablero"`
Expected: sin errores.

- [ ] **Step 5: Commit**

```bash
git add gui_swan.py test_regresion.py
git commit -m "feat(gui): campo Zona UTM y boton 'Generar batimetria' en Armar y correr"
```

---

## Verificación final

- `python -m pytest test_regresion.py -v` en verde (nuevos pasan; externos pueden marcar SKIP).
- `python -c "import io_batimetria, gui_swan, app_tablero"` sin errores.
- Prueba manual real (con internet): en "Armar y correr", llenar malla + Zona UTM, carpeta destino, "Generar batimetría…" → No (descargar) → verificar que rellena el `.bot` y el log muestra el rango de profundidad.

## Notas de implementación

- **Fuente de datos:** ETOPO1 (`etopo180`) es ~1.85 km — suficiente para un dominio regional, grueso cerca de costa. Para Reñaca fino (tesis), usar la opción de raster local (SHOA/GEBCO 15s). El dataset fino se puede fijar luego cambiando `_DATASET_ERDDAP`/`_VAR_ERDDAP`.
- **Orientación:** el `.bot` se escribe con `flipud(depth).ravel()`; el test `test_generar_bot_orientacion_norte_sur` blinda que `io_swan` lo reconstruya con el norte arriba (no espejado).
- **Tierra:** `depth = −elevation`; los nodos en tierra quedan con `depth ≤ 0` (SWAN los trata como secos). El `meta["pct_tierra"]` alto avisa de malla/zona mal ubicadas.
