# Puente ERA5/serie → borde SWAN — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derivar la condición de borde de un caso SWAN (Hs/Tp/Dir) desde una serie de oleaje (ERA5 o `.mat/.csv/.nc`), con dos disparadores en la GUI (botón en el formulario SWAN y botón en la ventana ERA5) que comparten un motor puro, sin tocar los flujos actuales.

**Architecture:** Un módulo nuevo `borde_oleaje.py` (motor puro: Dataset(time) + modo → {hs,per,dir}). El relleno del formulario y el diálogo de condición viven en `gui_swan` (compartidos por las dos vías). `swan_builder` pasa a emitir `SET NAUTICAL` para que el Dir náutico del oleaje se interprete bien. Todo lo demás queda igual.

**Tech Stack:** Python 3.13, numpy, scipy, xarray, tkinter, pytest.

**Convenciones del repo:** comentarios en español con tildes; `snake_case`; un módulo por responsabilidad; tests al final de `test_regresion.py`; `python -m pytest` (no `pytest`). Working dir de los comandos: `Herramientas computacionales/Tablero Oleaje/`. Commits: añadir al final del mensaje, en su propia línea, `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`; NO push.

---

## Estructura de archivos

- Crear: `borde_oleaje.py` — motor puro `condicion_borde(ds, modo, periodo_retorno)`.
- Modify: `swan_builder.py` — `construir_swn` emite `SET NAUTICAL`.
- Modify: `gui_swan.py` — `aplicar_borde` (método), `dialogo_condicion` (función de módulo), botón Vía A + handler, `borde_inicial` en `__init__`.
- Modify: `app_tablero.py` — botón Vía B "Enviar a SWAN como borde" en la ventana ERA5.
- Modify: `test_regresion.py` — tests del motor y del builder.

**Fases para ejecución por subagentes:** Fase 1 = Tasks 1–4 (núcleo `borde_oleaje` + `swan_builder`, mismas pruebas unitarias). Fase 2 = Tasks 5–7 (GUI).

---

## Task 1: `condicion_borde` — modo "maximo"

**Files:**
- Create: `borde_oleaje.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `test_regresion.py`:

```python
# --------------------------- Borde de oleaje (puente SWAN) ---------------------------
import borde_oleaje


def _serie_sintetica(con_dir=True):
    """Serie de 12 años con un temporal real conocido (peak) en una fecha."""
    import xarray as xr
    t = np.arange("2008-01-01", "2020-01-01", dtype="datetime64[D]")   # 12 años
    n = len(t)
    rng = np.random.default_rng(0)
    hs = 1.5 + np.abs(rng.normal(0.0, 0.7, n))
    tp = 6.0 + 0.5 * hs
    dirr = np.full(n, 200.0)
    ipk = 1500
    hs[ipk], tp[ipk], dirr[ipk] = 9.0, 14.0, 315.0    # peak real
    data = {"Hs": ("time", hs), "Tp": ("time", tp)}
    if con_dir:
        data["Dir"] = ("time", dirr)
    return xr.Dataset(data, coords={"time": t}), ipk, hs, tp, dirr


def test_borde_maximo_toma_el_peak():
    ds, ipk, hs, tp, dirr = _serie_sintetica()
    b = borde_oleaje.condicion_borde(ds, "maximo")
    assert b["hs"] == pytest.approx(9.0)
    assert b["per"] == pytest.approx(14.0)
    assert b["dir"] == pytest.approx(315.0)
    assert "Máximo observado" in b["descripcion"]
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_borde_maximo_toma_el_peak -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'borde_oleaje'`.

- [ ] **Step 3: Implementación mínima**

Crear `borde_oleaje.py`:

```python
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
    (Los modos 'retorno' y 'reinante' se agregan en tareas siguientes.)
    Las claves per/dir valen None si la serie no trae esa variable.
    """
    if modo == "maximo":
        i = _indice_peak(ds)
        per, dirr = _tp_dir_en(ds, i)
        fecha = str(ds["time"].isel(time=i).values)[:10]
        return {"hs": float(ds["Hs"].isel(time=i)), "per": per, "dir": dirr,
                "descripcion": f"Máximo observado ({fecha})"}

    raise ValueError(f"Modo de condición desconocido: {modo!r}")
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_borde_maximo_toma_el_peak -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add borde_oleaje.py test_regresion.py
git commit -m "feat(borde): condicion de borde modo maximo observado"
```

---

## Task 2: `condicion_borde` — modo "retorno" (Gumbel)

**Files:**
- Modify: `borde_oleaje.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_borde_retorno_monotono_y_hereda_peak():
    ds, *_ = _serie_sintetica()
    b100 = borde_oleaje.condicion_borde(ds, "retorno", 100)
    b2 = borde_oleaje.condicion_borde(ds, "retorno", 2)
    assert b100["hs"] > b2["hs"]                 # T mayor → Hs mayor (Gumbel monótono)
    assert b100["per"] == pytest.approx(14.0)    # Tp/Dir heredados del peak real
    assert b100["dir"] == pytest.approx(315.0)
    assert "T=100" in b100["descripcion"]


def test_borde_retorno_pocos_datos_falla():
    import xarray as xr
    t = np.arange("2020-01-01", "2020-02-01", dtype="datetime64[D]")   # 1 año solo
    ds = xr.Dataset({"Hs": ("time", np.linspace(1, 3, len(t)))}, coords={"time": t})
    with pytest.raises(ValueError, match="2 años"):
        borde_oleaje.condicion_borde(ds, "retorno")
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python -m pytest test_regresion.py::test_borde_retorno_monotono_y_hereda_peak test_regresion.py::test_borde_retorno_pocos_datos_falla -v`
Expected: FAIL ambos. El primero porque el modo "retorno" aún cae en el `raise ValueError("Modo ... desconocido")` (no devuelve dict). El segundo porque ese mensaje genérico no coincide con `match="2 años"` (el ValueError correcto, por <2 años de datos, todavía no existe).

- [ ] **Step 3: Implementación**

En `borde_oleaje.py`, insertar el bloque del modo "retorno" **antes** del `raise ValueError` final de `condicion_borde`:

```python
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
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_regresion.py::test_borde_retorno_monotono_y_hereda_peak test_regresion.py::test_borde_retorno_pocos_datos_falla -v`
Expected: PASS ambos.

- [ ] **Step 5: Commit**

```bash
git add borde_oleaje.py test_regresion.py
git commit -m "feat(borde): condicion de borde modo periodo de retorno (Gumbel)"
```

---

## Task 3: `condicion_borde` — modo "reinante" y serie sin Dir

**Files:**
- Modify: `borde_oleaje.py`
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_borde_reinante_mediana_y_sector():
    ds, ipk, hs, tp, dirr = _serie_sintetica()
    b = borde_oleaje.condicion_borde(ds, "reinante")
    assert b["hs"] == pytest.approx(float(np.median(hs)))
    assert b["dir"] == pytest.approx(191.25)     # sector dominante de 200° (180–202.5)
    assert "reinante" in b["descripcion"].lower()


def test_borde_sin_dir_devuelve_none():
    ds, *_ = _serie_sintetica(con_dir=False)
    b = borde_oleaje.condicion_borde(ds, "maximo")
    assert b["dir"] is None
    assert b["per"] == pytest.approx(14.0)
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python -m pytest test_regresion.py::test_borde_reinante_mediana_y_sector test_regresion.py::test_borde_sin_dir_devuelve_none -v`
Expected: el de "reinante" FALLA (cae en el `raise ValueError`); el de "sin dir" probablemente ya pasa (el modo "maximo" ya maneja `None`). Corre ambos igual.

- [ ] **Step 3: Implementación**

En `borde_oleaje.py`, insertar el bloque del modo "reinante" **antes** del `raise ValueError` final:

```python
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
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_regresion.py::test_borde_reinante_mediana_y_sector test_regresion.py::test_borde_sin_dir_devuelve_none -v`
Expected: PASS ambos.

- [ ] **Step 5: Commit**

```bash
git add borde_oleaje.py test_regresion.py
git commit -m "feat(borde): condicion de borde modo reinante y manejo de serie sin Dir"
```

---

## Task 4: `swan_builder` emite `SET NAUTICAL`

**Files:**
- Modify: `swan_builder.py:118-129` (lista `L` inicial de `construir_swn`)
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_builder_emite_set_nautical():
    txt = swan_builder.construir_swn(
        nombre="T", malla={"xpc": 0., "ypc": 0., "xlenc": 1000, "ylenc": 1000,
                           "mxc": 10, "myc": 10},
        batimetria={"archivo": "f.bot"},
        bordes=[{"lado": "W", "hs": 2., "per": 10., "dir": 270., "dd": 15.}],
        salidas=("Hs", "Dir"))
    assert "SET NAUTICAL" in txt
    # el borde y el resto siguen intactos
    assert "BOUN SIDE W CCW CON PAR 2.0 10.0 270.0 15.0" in txt
    assert "CGRID 0.0 0.0 0.0 1000 1000 10 10 CIRCLE" in txt
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_builder_emite_set_nautical -v`
Expected: FAIL con `assert "SET NAUTICAL" in txt`.

- [ ] **Step 3: Implementación**

En `swan_builder.py`, en `construir_swn`, la lista `L` empieza con `["$ ...", f"PROJ '{nombre}' '1'", "$", ...]`. Insertar `"SET NAUTICAL"` justo después de la línea `PROJ`. Reemplazar:

```python
    L = ["$ Archivo SWAN generado por el Tablero de Oleaje",
         f"PROJ '{nombre}' '1'",
         "$",
         "$*********** Malla y batimetría ***********",
```

por:

```python
    L = ["$ Archivo SWAN generado por el Tablero de Oleaje",
         f"PROJ '{nombre}' '1'",
         "$",
         "$ Direcciones en convención náutica (de dónde viene el oleaje).",
         "SET NAUTICAL",
         "$",
         "$*********** Malla y batimetría ***********",
```

- [ ] **Step 4: Correr los tests para verlos pasar (incluido el preexistente del builder)**

Run: `python -m pytest test_regresion.py::test_builder_emite_set_nautical test_regresion.py::test_builder_genera_bloques_clave -v`
Expected: PASS ambos.

- [ ] **Step 5: Commit**

```bash
git add swan_builder.py test_regresion.py
git commit -m "feat(swan): emitir SET NAUTICAL para el Dir del borde en convencion nautica"
```

---

## Task 5: `gui_swan.aplicar_borde` (método rellena el formulario)

**Files:**
- Modify: `gui_swan.py` (agregar método a `VentanaSwan`)
- Test: `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

El método se prueba con un *stub* (sin abrir tkinter): se invoca como función no ligada pasando un objeto con `self.v` y `self.log`.

```python
def test_aplicar_borde_rellena_formulario():
    import gui_swan

    class _Var:
        def __init__(self): self.valor = None
        def set(self, v): self.valor = str(v)

    class _Log:
        def insert(self, *a): pass
        def see(self, *a): pass

    class _Stub:
        def __init__(self):
            self.v = {"hs": _Var(), "per": _Var(), "dir": _Var()}
            self.log = _Log()

    stub = _Stub()
    borde = {"hs": 8.0, "per": 14.0, "dir": 315.0, "descripcion": "máx"}
    gui_swan.VentanaSwan.aplicar_borde(stub, borde)
    assert stub.v["hs"].valor == "8"
    assert stub.v["per"].valor == "14"
    assert stub.v["dir"].valor == "315"

    # Dir None → campo en blanco, sin reventar
    stub2 = _Stub()
    gui_swan.VentanaSwan.aplicar_borde(stub2, {"hs": 2.0, "per": None, "dir": None,
                                               "descripcion": "x"})
    assert stub2.v["hs"].valor == "2"
    assert stub2.v["per"].valor == ""
    assert stub2.v["dir"].valor == ""
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_aplicar_borde_rellena_formulario -v`
Expected: FAIL con `AttributeError: type object 'VentanaSwan' has no attribute 'aplicar_borde'`.

- [ ] **Step 3: Implementación**

En `gui_swan.py`, dentro de la clase `VentanaSwan` (p. ej. después de `_pestana_nuevo`), agregar:

```python
    def aplicar_borde(self, borde):
        """
        Rellena los campos Hs/Tp/Dir del formulario 'Armar y correr' con un borde
        derivado de una serie (dict {hs, per, dir, descripcion}). Deja en blanco
        las claves None y no toca lado/dispersión/malla/batimetría.
        """
        for clave in ("hs", "per", "dir"):
            val = borde.get(clave)
            self.v[clave].set("" if val is None else f"{val:g}")
        self.log.insert("end", f"Borde aplicado — {borde.get('descripcion', '')}: "
                        f"Hs={borde.get('hs')}, Tp={borde.get('per')}, "
                        f"Dir={borde.get('dir')}\n")
        self.log.see("end")
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_regresion.py::test_aplicar_borde_rellena_formulario -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_swan.py test_regresion.py
git commit -m "feat(gui): aplicar_borde rellena el formulario SWAN con Hs/Tp/Dir"
```

---

## Task 6: `dialogo_condicion`, botón Vía A y `borde_inicial`

**Files:**
- Modify: `gui_swan.py` (imports, función de módulo, botón en `_pestana_nuevo`, handler, `__init__`, guardar `self.nb`)
- Test: import smoke en `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_gui_swan_expone_dialogo_y_handler():
    import gui_swan
    assert callable(gui_swan.dialogo_condicion)
    assert hasattr(gui_swan.VentanaSwan, "_tomar_borde_archivo")
    assert hasattr(gui_swan.VentanaSwan, "aplicar_borde")
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_regresion.py::test_gui_swan_expone_dialogo_y_handler -v`
Expected: FAIL con `AttributeError: module 'gui_swan' has no attribute 'dialogo_condicion'`.

- [ ] **Step 3: Implementación**

(a) En la cabecera de imports de `gui_swan.py`, asegurar que estén (agregar los que falten):

```python
from tkinter import messagebox
import io_oleaje
import borde_oleaje
```

(b) A nivel de módulo (fuera de la clase), agregar la función de diálogo:

```python
def dialogo_condicion(parent):
    """
    Diálogo modal para elegir la condición de borde. Devuelve (modo, T) o None si
    se cancela. T solo aplica al modo 'retorno'. Compartido por las dos vías
    (formulario SWAN y ventana ERA5).
    """
    win = tk.Toplevel(parent)
    win.title("Condición de borde")
    win.transient(parent)
    win.grab_set()
    modo = tk.StringVar(value="retorno")
    tr = tk.StringVar(value="100")
    for val, txt in (("retorno", "Periodo de retorno (Gumbel)"),
                     ("maximo", "Máximo observado"),
                     ("reinante", "Oleaje reinante (p50)")):
        ttk.Radiobutton(win, text=txt, variable=modo, value=val).pack(
            anchor="w", padx=12, pady=2)
    fila = ttk.Frame(win)
    fila.pack(anchor="w", padx=12, pady=(4, 0))
    ttk.Label(fila, text="T [años] (solo retorno):").pack(side="left")
    ttk.Entry(fila, textvariable=tr, width=6).pack(side="left", padx=(4, 0))

    elegido = {}

    def aceptar():
        try:
            elegido["tr"] = int(float(tr.get()))
        except ValueError:
            elegido["tr"] = 100
        elegido["modo"] = modo.get()
        win.destroy()

    ttk.Button(win, text="Aceptar", command=aceptar).pack(pady=10, ipadx=8)
    parent.wait_window(win)
    if "modo" not in elegido:
        return None
    return elegido["modo"], elegido["tr"]
```

(c) En `_pestana_nuevo`, justo antes de `self.boton_armar = ...`, agregar el botón Vía A:

```python
        ttk.Button(f, text="Tomar borde de ERA5/serie…",
                   command=self._tomar_borde_archivo).pack(anchor="w", pady=(8, 0))
```

(d) Agregar el handler como método de `VentanaSwan`:

```python
    def _tomar_borde_archivo(self):
        """Vía A: elige un archivo de serie + condición y rellena el borde."""
        ruta = filedialog.askopenfilename(
            title="Serie de oleaje (ERA5/.mat/.csv/.nc)",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.nc *.mat *.csv"), ("Todos", "*.*")])
        if not ruta:
            return
        cond = dialogo_condicion(self)
        if not cond:
            return
        modo, tr = cond
        try:
            ds = io_oleaje.cargar(ruta)
            borde = borde_oleaje.condicion_borde(ds, modo, tr)
        except Exception as e:
            messagebox.showerror("No se pudo derivar el borde", str(e))
            return
        self.aplicar_borde(borde)
```

(e) En `_construir`, donde se crea el notebook `nb`, guardar la referencia para poder activar la pestaña: añadir `self.nb = nb` justo después de crear `nb` (la línea `nb = ttk.Notebook(marco)`).

(f) En `__init__`, agregar el parámetro `borde_inicial` y aplicarlo tras construir:

```python
    def __init__(self, master=None, borde_inicial=None):
        super().__init__(master)
        self.title("Procesar SWAN")
        self.geometry("720x640")
        self.minsize(640, 560)
        self._proc = None
        self._cancelar = threading.Event()
        self._construir()
        if borde_inicial:
            self.aplicar_borde(borde_inicial)
            self.nb.select(1)        # deja activa la pestaña "Armar y correr"
```

- [ ] **Step 4: Correr el test y verificar import**

Run: `python -m pytest test_regresion.py::test_gui_swan_expone_dialogo_y_handler -v`
Expected: PASS.
Run: `python -c "import gui_swan, app_tablero"`
Expected: sin errores ni ventanas.

- [ ] **Step 5: Commit**

```bash
git add gui_swan.py test_regresion.py
git commit -m "feat(gui): dialogo de condicion, boton 'Tomar borde de ERA5/serie' y borde_inicial"
```

---

## Task 7: Vía B — botón "Enviar a SWAN como borde" en la ventana ERA5

**Files:**
- Modify: `app_tablero.py` (imports + ventana ERA5 en `_abrir_era5`)
- Test: import smoke en `test_regresion.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_app_tablero_importa_borde():
    import app_tablero
    import borde_oleaje, io_oleaje      # deben ser importables desde app_tablero
    assert hasattr(app_tablero, "validar_inputs_era5")
```

(Este test fija que `app_tablero` siga importando limpio tras agregar la Vía B; la lógica de borde ya está cubierta por los tests del motor.)

- [ ] **Step 2: Correr el test (debería pasar el import actual; sirve de ancla)**

Run: `python -m pytest test_regresion.py::test_app_tablero_importa_borde -v`
Expected: PASS ya (ancla); tras implementar seguirá PASS, confirmando que no rompimos el import.

- [ ] **Step 3: Implementación**

(a) En el bloque de imports de `app_tablero.py` (junto a `import io_era5` / `import rutas`), agregar:

```python
import io_oleaje
import borde_oleaje
```

(b) Dentro de `_abrir_era5`, después de crear el botón "Descargar" (la línea `ttk.Button(win, text="Descargar", command=lanzar).pack(...)`), agregar el botón Vía B y su handler como closure (usa los `campos` lat/lon de esa ventana):

```python
        def enviar_borde():
            try:
                lat, lon = validar_inputs_era5(
                    campos["lat"].get(), campos["lon"].get(),
                    campos["inicio"].get(), campos["fin"].get())
            except ValueError as e:
                messagebox.showerror("Datos inválidos", str(e))
                return
            nc = (rutas.carpeta_salida(io_era5._nombre_fuente(lat, lon, "serie"))
                  / "era5_serie.nc")
            if not nc.exists():
                messagebox.showwarning(
                    "Sin datos",
                    "Primero descarga la serie ERA5 para esta coordenada.")
                return
            cond = gui_swan.dialogo_condicion(win)
            if not cond:
                return
            modo, tr = cond
            try:
                ds = io_oleaje.cargar(nc)
                borde = borde_oleaje.condicion_borde(ds, modo, tr)
            except Exception as e:
                messagebox.showerror("No se pudo derivar el borde", str(e))
                return
            gui_swan.VentanaSwan(self, borde_inicial=borde)

        ttk.Button(win, text="Enviar a SWAN como borde",
                   command=enviar_borde).pack(pady=(0, 10), ipadx=6)
```

- [ ] **Step 4: Correr el test y verificar import + arranque**

Run: `python -m pytest test_regresion.py::test_app_tablero_importa_borde -v`
Expected: PASS.
Run: `python -c "import app_tablero"`
Expected: sin errores.

- [ ] **Step 5: Commit**

```bash
git add app_tablero.py test_regresion.py
git commit -m "feat(gui): boton 'Enviar a SWAN como borde' en la ventana ERA5 (via B)"
```

---

## Verificación final

- `python -m pytest test_regresion.py -v` en verde (los tests nuevos pasan; los de datos externos pueden marcar SKIP si no están en disco).
- `python -c "import app_tablero, gui_swan, borde_oleaje"` sin errores.
- Repaso manual: abrir la app, "Procesar SWAN…" → pestaña "Armar y correr" → botón "Tomar borde de ERA5/serie…" funciona; y en "Descargar ERA5…" aparece "Enviar a SWAN como borde".

## Notas de implementación

- **Convención direccional:** el motor entrega el Dir tal como viene en la serie (náutico). El `.swn` ahora emite `SET NAUTICAL`, así que el `dir` del borde se interpreta como "de dónde viene el oleaje". Esto cambia la convención del campo "Dir" del formulario respecto al builder anterior (antes, sin SET, SWAN lo tomaba cartesiano): documentarlo en el README al cerrar.
- **DRY:** las dos vías comparten `borde_oleaje.condicion_borde`, `gui_swan.dialogo_condicion` y `VentanaSwan.aplicar_borde`. Los botones solo difieren en de dónde sale el archivo.
