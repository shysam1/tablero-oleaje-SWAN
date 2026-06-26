# Malla por lat/lon — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Definir la malla SWAN por lat/lon (centro + tamaño + celda) y que la app calcule sola la zona UTM y rellene los campos UTM del formulario "Armar y correr".

**Architecture:** Un motor puro `geo_malla.py` (lat/lon → campos UTM, deriva la zona) y un botón "Definir por lat/lon…" con diálogo en `gui_swan` que escribe los campos del formulario. Reusa `io_batimetria.epsg_utm` y `pyproj`.

**Tech Stack:** Python 3.13, pyproj, tkinter, pytest.

**Convenciones del repo:** comentarios en español con tildes; `snake_case`; un módulo por responsabilidad; tests al final de `test_regresion.py`; `python -m pytest` (no `pytest`). Working dir: `Herramientas computacionales/Tablero Oleaje/`. Commits: añadir al final del mensaje, en su propia línea, `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`; NO push.

---

## Estructura de archivos

- Crear: `geo_malla.py` — `malla_desde_latlon(...)` (+ helper `_zona_utm`).
- Modify: `gui_swan.py` — `import geo_malla`; función de módulo `dialogo_latlon`; botón "Definir por lat/lon…" en `_pestana_nuevo`; método `_definir_malla_latlon`.
- Modify: `test_regresion.py` — tests del motor + smoke de la GUI.

---

## Task 1: `geo_malla.malla_desde_latlon`

**Files:**
- Create: `geo_malla.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `test_regresion.py`:

```python
# --------------------------- Malla por lat/lon ---------------------------
import geo_malla


def test_malla_desde_latlon_renaca():
    m = geo_malla.malla_desde_latlon(-32.97, -71.55, 8.0, 8.0, 100.0)
    assert m["zona_utm"] == "19S"
    assert m["mxc"] == 80 and m["myc"] == 80
    assert m["xlenc"] == 8000.0 and m["ylenc"] == 8000.0
    # round-trip: el centro de la malla calculada vuelve a ~(-71.55, -32.97)
    from pyproj import Transformer
    from io_batimetria import epsg_utm
    a_geo = Transformer.from_crs(epsg_utm("19S"), 4326, always_xy=True)
    lon_c, lat_c = a_geo.transform(m["xpc"] + m["xlenc"] / 2,
                                   m["ypc"] + m["ylenc"] / 2)
    assert lon_c == pytest.approx(-71.55, abs=1e-3)
    assert lat_c == pytest.approx(-32.97, abs=1e-3)


def test_malla_zona_por_longitud():
    assert geo_malla.malla_desde_latlon(-33.0, -73.0, 5, 5, 100)["zona_utm"] == "18S"
    assert geo_malla.malla_desde_latlon(-33.0, -71.55, 5, 5, 100)["zona_utm"] == "19S"


def test_malla_validaciones():
    with pytest.raises(ValueError):
        geo_malla.malla_desde_latlon(-33.0, -71.55, 1.0, 1.0, 2000.0)   # celda > extensión
    with pytest.raises(ValueError):
        geo_malla.malla_desde_latlon(200.0, -71.55, 5, 5, 100)          # lat fuera de rango
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python -m pytest test_regresion.py -k malla -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'geo_malla'`.

- [ ] **Step 3: Implementación**

Crear `geo_malla.py`:

```python
"""
Geometría de la malla de cómputo SWAN.

Convierte una definición en lat/lon (centro + tamaño + resolución) en los campos
UTM que usa el formulario "Armar y correr" (xpc/ypc/xlenc/ylenc/mxc/myc) y deriva
la zona UTM sola, para no tener que saber el origen UTM a mano.
"""

from pyproj import Transformer

from io_batimetria import epsg_utm


def _zona_utm(lat, lon):
    """Zona UTM ('19S', '18S', '19N', ...) del punto."""
    zona = int((lon + 180) // 6) + 1
    return f"{zona}{'S' if lat < 0 else 'N'}"


def malla_desde_latlon(lat_centro, lon_centro, ancho_km, alto_km, celda_m):
    """
    Campos de malla UTM para un dominio centrado en (lat, lon).

    ancho_km/alto_km: extensión; celda_m: tamaño de celda. La zona UTM se deriva
    del centro. Devuelve {xpc, ypc, xlenc, ylenc, mxc, myc, zona_utm}. Lanza
    ValueError si los datos no son físicos.
    """
    if not -90.0 <= lat_centro <= 90.0:
        raise ValueError(f"Latitud fuera de rango: {lat_centro}")
    if not -180.0 <= lon_centro <= 180.0:
        raise ValueError(f"Longitud fuera de rango: {lon_centro}")
    if ancho_km <= 0 or alto_km <= 0:
        raise ValueError("El ancho y el alto deben ser positivos.")
    if celda_m <= 0:
        raise ValueError("El tamaño de celda debe ser positivo.")

    xlenc = float(ancho_km) * 1000.0
    ylenc = float(alto_km) * 1000.0
    mxc = int(round(xlenc / celda_m))
    myc = int(round(ylenc / celda_m))
    if mxc < 2 or myc < 2:
        raise ValueError("La celda es demasiado grande: se necesitan al menos "
                         "2 celdas por lado.")

    zona = _zona_utm(lat_centro, lon_centro)
    a_utm = Transformer.from_crs(4326, epsg_utm(zona), always_xy=True)
    x_c, y_c = a_utm.transform(lon_centro, lat_centro)

    return {"xpc": x_c - xlenc / 2.0, "ypc": y_c - ylenc / 2.0,
            "xlenc": xlenc, "ylenc": ylenc, "mxc": mxc, "myc": myc,
            "zona_utm": zona}
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_regresion.py -k malla -v`
Expected: PASS los 3 tests (`test_malla_desde_latlon_renaca`, `test_malla_zona_por_longitud`, `test_malla_validaciones`).

- [ ] **Step 5: Commit**

```bash
git add geo_malla.py test_regresion.py
git commit -m "feat(malla): malla_desde_latlon deriva zona UTM y campos de malla"
```

---

## Task 2: GUI — botón "Definir por lat/lon…"

**Files:**
- Modify: `gui_swan.py` (import, función de módulo, botón en `_pestana_nuevo`, método)
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_gui_swan_expone_definir_malla_latlon():
    import gui_swan
    assert callable(gui_swan.dialogo_latlon)
    assert hasattr(gui_swan.VentanaSwan, "_definir_malla_latlon")
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_gui_swan_expone_definir_malla_latlon -v`
Expected: FAIL con `AttributeError: module 'gui_swan' has no attribute 'dialogo_latlon'`.

- [ ] **Step 3: Implementación**

(a) En la cabecera de imports de `gui_swan.py`, agregar:

```python
import geo_malla
```

(b) A nivel de módulo (fuera de la clase), agregar el diálogo:

```python
def dialogo_latlon(parent):
    """
    Diálogo para definir la malla por lat/lon (centro + tamaño + celda).
    Devuelve un dict {lat, lon, ancho, alto, celda} (strings) o None si se cancela.
    """
    win = tk.Toplevel(parent)
    win.title("Definir malla por lat/lon")
    win.transient(parent)
    win.grab_set()
    campos = {}
    for etiqueta, clave, valor in (
            ("Latitud centro", "lat", "-32.97"),
            ("Longitud centro", "lon", "-71.55"),
            ("Ancho [km]", "ancho", "8"),
            ("Alto [km]", "alto", "8"),
            ("Tamaño de celda [m]", "celda", "100")):
        fila = ttk.Frame(win)
        fila.pack(fill="x", padx=10, pady=3)
        ttk.Label(fila, text=etiqueta, width=20).pack(side="left")
        var = tk.StringVar(value=valor)
        ttk.Entry(fila, textvariable=var, width=12).pack(side="left")
        campos[clave] = var

    elegido = {}

    def aceptar():
        elegido.update({k: v.get() for k, v in campos.items()})
        win.destroy()

    ttk.Button(win, text="Calcular", command=aceptar).pack(pady=10, ipadx=8)
    parent.wait_window(win)
    return elegido or None
```

(c) En `_pestana_nuevo`, después de la fila `m2` (celdas + Zona UTM) y antes de la
sección "Condición de borde", agregar el botón:

```python
        ttk.Button(f, text="Definir por lat/lon…",
                   command=self._definir_malla_latlon).pack(anchor="w", pady=(6, 0))
```

(d) Agregar el método a la clase `VentanaSwan`:

```python
    def _definir_malla_latlon(self):
        """Calcula la malla UTM desde lat/lon y rellena los campos del formulario."""
        datos = dialogo_latlon(self)
        if not datos:
            return
        try:
            m = geo_malla.malla_desde_latlon(
                float(datos["lat"]), float(datos["lon"]),
                float(datos["ancho"]), float(datos["alto"]), float(datos["celda"]))
        except (ValueError, KeyError) as e:
            messagebox.showerror("Datos inválidos", str(e))
            return
        self.v["xpc"].set(f"{m['xpc']:.0f}")
        self.v["ypc"].set(f"{m['ypc']:.0f}")
        self.v["xlenc"].set(f"{m['xlenc']:.0f}")
        self.v["ylenc"].set(f"{m['ylenc']:.0f}")
        self.v["mxc"].set(str(m["mxc"]))
        self.v["myc"].set(str(m["myc"]))
        self.v["zona_utm"].set(m["zona_utm"])
        self.log.insert("end", f"Malla definida: zona {m['zona_utm']}, "
                        f"{m['mxc']}×{m['myc']} celdas.\n")
        self.log.see("end")
```

- [ ] **Step 4: Correr el test y verificar import**

Run: `python -m pytest test_regresion.py::test_gui_swan_expone_definir_malla_latlon -v`
Expected: PASS.
Run: `python -c "import gui_swan, app_tablero"`
Expected: sin errores.

- [ ] **Step 5: Commit**

```bash
git add gui_swan.py test_regresion.py
git commit -m "feat(gui): boton 'Definir por lat/lon' que rellena la malla UTM"
```

---

## Verificación final

- `python -m pytest test_regresion.py -v` en verde (nuevos pasan; externos pueden marcar SKIP).
- `python -c "import geo_malla, gui_swan, app_tablero"` sin errores.
- Prueba manual: en "Armar y correr" → "Definir por lat/lon…" → Reñaca (−32.97, −71.55, 8, 8, 100) → verificar que rellena xpc/ypc/xlenc/ylenc/mxc/myc y Zona UTM = 19S.

## Notas de implementación

- `dialogo_latlon` es función de módulo (no método), como `dialogo_condicion`, para
  que el futuro asistente guiado pueda reutilizarla.
- El botón **rellena** los campos UTM existentes (no los oculta): la entrada UTM y
  la entrada lat/lon conviven.
