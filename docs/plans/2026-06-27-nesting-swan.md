# Modelo anidado (nesting) SWAN — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el camino guiado Modelar pueda armar y correr un modelo SWAN anidado (dominio grande + nido fino, dos batimetrías) desde cero, reproduciendo el patrón de las corridas tipo Coronel Tr100.

**Architecture:** Se extiende `swan_builder` con parámetros opcionales (`nido`, `bou_nest`, `punto_espectral`) y una función orquestadora `escribir_par_anidado` que emite los dos `.swn` enlazados (NGRID/NESTOUT ↔ BOU NEST); `swan_runner.casos_ordenados` pasa a ordenar por dependencia de nesting; y el wizard Modelar gana un paso opcional `PasoNido` que define la malla/batimetría fina del nido y lo agrega a `contexto["dominios"]` (lista ya preparada).

**Tech Stack:** Python 3.13, tkinter/ttk, pytest. Reusa `geo_malla`, `io_batimetria`, `swan_builder`, `swan_runner`, `tablero_swan`.

**Spec:** `docs/specs/2026-06-27-nesting-swan-design.md`

---

## Estructura de archivos

- **Modificar** `swan_builder.py` — `construir_swn` (+`nido`/`bou_nest`/`punto_espectral`), `validar_caso` (+`requiere_bordes`), y nuevas `validar_caso_anidado` y `escribir_par_anidado`.
- **Modificar** `swan_runner.py` — `casos_ordenados` por dependencia de nesting (+ helper `_es_nido`).
- **Modificar** `pasos_modelar.py` — `PasoNido` nuevo, insertado en `PASOS_MODELAR`; `PasoCorrer._correr` bifurca a 1 o 2 dominios.
- **Crear** `test_nesting.py` — tests del motor (builder, validación, orden).
- **Modificar** `README.md`, `HANDOFF.md` — documentar el nesting.

Comentarios en español con tildes, `snake_case`, mensajes de UI en español neutro (sin voseo), sin prints de debug.

---

## Task 1: `construir_swn` — NGRID/NESTOUT, BOU NEST y punto espectral

**Files:**
- Modify: `swan_builder.py`
- Test: `test_nesting.py` (crear)

- [ ] **Step 1: Escribir los tests que fallan**

Crear `test_nesting.py`:

```python
"""Tests del motor de nesting (builder, validación y orden de corrida)."""
import swan_builder
import swan_runner


MALLA_G = {"xpc": 0, "ypc": 0, "xlenc": 48000, "ylenc": 59000, "mxc": 48, "myc": 59}
MALLA_N = {"xpc": 36480, "ypc": 32229, "xlenc": 9000, "ylenc": 10000,
           "mxc": 45, "myc": 50}
NIDO = {"sname": "nido1", "nestfile": "nest1", "xpn": 36480, "ypn": 32229,
        "xlenn": 9000, "ylenn": 10000, "mxn": 45, "myn": 50}
BORDES = [{"lado": "W", "hs": 8.16, "per": 13, "dir": 315, "dd": 17.7}]


def test_construir_swn_nido_emite_ngrid_nestout():
    txt = swan_builder.construir_swn("G", MALLA_G, {"archivo": "b.bot"}, BORDES,
                                     nido=NIDO)
    assert "NGRID 'nido1' 36480 32229 0. 9000 10000 45 50" in txt
    assert "NESTOUT 'nido1' 'nest1'" in txt
    assert "BOUN SIDE W" in txt          # el grande conserva sus bordes


def test_construir_swn_bou_nest_reemplaza_boun_side():
    txt = swan_builder.construir_swn("N", MALLA_N, {"archivo": "bn.bot"}, [],
                                     bou_nest="nest1")
    assert "BOU NEST 'nest1' CLOSED" in txt
    assert "BOUN SIDE" not in txt
    assert "BOU SHAPE" not in txt


def test_construir_swn_punto_espectral():
    txt = swan_builder.construir_swn(
        "N", MALLA_N, {"archivo": "bn.bot"}, [], bou_nest="nest1",
        punto_espectral={"x": 42423, "y": 37171, "archivo": "Espectro_Punto.txt"})
    assert "POINTS 'SpecOut' 42423 37171" in txt
    assert "SPEC 'SpecOut' SPEC2D ABS 'Espectro_Punto.txt'" in txt
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `cd "Herramientas computacionales/Tablero Oleaje" && python -m pytest test_nesting.py -v`
Expected: FAIL — `construir_swn()` no acepta los kwargs `nido`/`bou_nest`/`punto_espectral` (`TypeError`).

- [ ] **Step 3: Modificar `construir_swn` en `swan_builder.py`**

Cambiar la firma (agregar los 3 parámetros al final):

```python
def construir_swn(nombre, malla, batimetria, bordes, salidas=("Hs", "Tp", "Dir"),
                  estacionario=True, tiempo=None, friccion=True, setup=True,
                  viento=False, cuadruples=False,
                  nido=None, bou_nest=None, punto_espectral=None):
```

Reemplazar el bloque de **condiciones de borde** actual:

```python
    L += ["$", "$*********** Condiciones de borde ***********",
         "BOU SHAPE JONSWAP 3.3 PEAK DSPR DEGREES"]

    for bd in bordes:
        dd = bd.get("dd", 0.0)
        L.append(f"BOUN SIDE {bd['lado']} CCW CON PAR "
                 f"{bd['hs']} {bd['per']} {bd['dir']} {dd}")
```

por (un nido toma su contorno del nesting, no de BOUN SIDE):

```python
    L += ["$", "$*********** Condiciones de borde ***********"]
    if bou_nest:
        L.append(f"BOU NEST '{bou_nest}' CLOSED")
    else:
        L.append("BOU SHAPE JONSWAP 3.3 PEAK DSPR DEGREES")
        for bd in bordes:
            dd = bd.get("dd", 0.0)
            L.append(f"BOUN SIDE {bd['lado']} CCW CON PAR "
                     f"{bd['hs']} {bd['per']} {bd['dir']} {dd}")
```

Reemplazar el bloque de **salidas** actual:

```python
    L += ["$", "$*********** Salidas ***********"]
    for var in salidas:
        if var in _QUANT:
            L.append(f"BLOCK 'COMPGRID' NOHEADER '{_ARCHIVO[var]}' {_QUANT[var]}")
```

por (NGRID antes de los BLOCK, NESTOUT y el punto espectral después, como en el `.swn` real):

```python
    L += ["$", "$*********** Salidas ***********"]
    if nido:
        L.append(f"NGRID '{nido['sname']}' {nido['xpn']} {nido['ypn']} 0. "
                 f"{nido['xlenn']} {nido['ylenn']} {nido['mxn']} {nido['myn']}")
    for var in salidas:
        if var in _QUANT:
            L.append(f"BLOCK 'COMPGRID' NOHEADER '{_ARCHIVO[var]}' {_QUANT[var]}")
    if nido:
        L.append(f"NESTOUT '{nido['sname']}' '{nido['nestfile']}'")
    if punto_espectral:
        pe = punto_espectral
        L.append(f"POINTS 'SpecOut' {pe['x']} {pe['y']}")
        L.append(f"SPEC 'SpecOut' SPEC2D ABS '{pe['archivo']}'")
```

Actualizar el docstring de `construir_swn` agregando, tras la descripción de `tiempo`:

```python
    nido:      dict {sname, nestfile, xpn, ypn, xlenn, ylenn, mxn, myn}. Si se da,
               el dominio emite NGRID + NESTOUT (es el grande de un anidado).
    bou_nest:  nombre del archivo de contorno. Si se da, el dominio usa
               BOU NEST en vez de BOUN SIDE (es el nido de un anidado).
    punto_espectral: dict {x, y, archivo}. Si se da, emite POINTS + SPEC 2D.
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_nesting.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Verificar que no se rompió el caso de un dominio**

Run: `python -m pytest test_regresion.py -q`
Expected: PASS (los `.swn` de un dominio siguen igual: sin `nido`/`bou_nest`, el bloque de borde y salidas es idéntico al anterior).

- [ ] **Step 6: Commit**

```bash
git add swan_builder.py test_nesting.py
git commit -m "feat: construir_swn soporta NGRID/NESTOUT, BOU NEST y punto espectral"
```

---

## Task 2: `validar_caso_anidado` + `escribir_par_anidado` + `validar_caso(requiere_bordes)`

**Files:**
- Modify: `swan_builder.py`
- Test: `test_nesting.py`

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `test_nesting.py`:

```python
def test_validar_caso_anidado_nido_fuera_es_error():
    g = {**MALLA_G, "zona_utm": "18S"}
    n = {"xpc": 40000, "ypc": 55000, "xlenc": 20000, "ylenc": 20000,
         "mxc": 100, "myc": 100, "zona_utm": "18S"}     # se sale por arriba
    errores, _ = swan_builder.validar_caso_anidado(g, n)
    assert any("contenido" in e.lower() for e in errores)


def test_validar_caso_anidado_zona_distinta_es_error():
    g = {**MALLA_G, "zona_utm": "18S"}
    n = {**MALLA_N, "zona_utm": "19S"}
    errores, _ = swan_builder.validar_caso_anidado(g, n)
    assert any("zona" in e.lower() for e in errores)


def test_validar_caso_anidado_ok_no_tiene_errores():
    g = {**MALLA_G, "zona_utm": "18S"}
    n = {**MALLA_N, "zona_utm": "18S"}
    errores, _ = swan_builder.validar_caso_anidado(g, n)
    assert errores == []


def test_validar_caso_anidado_celda_no_fina_avisa():
    g = {**MALLA_G, "zona_utm": "18S"}                  # ~1000 m
    n = {"xpc": 1000, "ypc": 1000, "xlenc": 9000, "ylenc": 10000,
         "mxc": 4, "myc": 5, "zona_utm": "18S"}         # ~2250 m, más gruesa
    _, avisos = swan_builder.validar_caso_anidado(g, n)
    assert any("fina" in a.lower() for a in avisos)


def test_validar_caso_sin_bordes_no_exige_borde():
    errores, _ = swan_builder.validar_caso(
        MALLA_N, {"archivo": "bn.bot"}, [], requiere_bordes=False)
    assert not any("borde" in e.lower() for e in errores)


def test_escribir_par_anidado_crea_dos_swn_enlazados(tmp_path):
    rg, rn = swan_builder.escribir_par_anidado(
        tmp_path, "Grande", "Nido", MALLA_G, {"archivo": "bg.bot"}, BORDES,
        MALLA_N, {"archivo": "bn.bot"})
    tg, tn = rg.read_text(), rn.read_text()
    assert "NGRID 'nido1' 36480 32229 0. 9000 10000 45 50" in tg
    assert "NESTOUT 'nido1' 'nest1'" in tg
    assert "BOU NEST 'nest1' CLOSED" in tn
    assert "CGRID 36480 32229" in tn
    assert "BOUN SIDE" not in tn
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python -m pytest test_nesting.py -v`
Expected: FAIL — `validar_caso_anidado`/`escribir_par_anidado` no existen y `validar_caso` no acepta `requiere_bordes`.

- [ ] **Step 3: Modificar `validar_caso` y agregar las dos funciones en `swan_builder.py`**

En `validar_caso`, cambiar la firma y el chequeo de bordes:

```python
def validar_caso(malla, batimetria, bordes, carpeta=None, requiere_bordes=True):
```

Reemplazar:

```python
    # Condiciones de borde.
    if not bordes:
        errores.append("Define al menos una condición de borde (lado de entrada).")
```

por:

```python
    # Condiciones de borde.
    if requiere_bordes and not bordes:
        errores.append("Define al menos una condición de borde (lado de entrada).")
```

Agregar al final del módulo (antes del bloque `if __name__`):

```python
def validar_caso_anidado(malla_g, malla_n):
    """
    Comprueba la coherencia del par grande/nido. Devuelve (errores, avisos).

    El nido debe estar contenido en el grande, en la misma zona UTM, y con celda
    más fina (lo último es sólo aviso).
    """
    errores, avisos = [], []
    gx0, gy0 = malla_g["xpc"], malla_g["ypc"]
    gx1, gy1 = gx0 + malla_g["xlenc"], gy0 + malla_g["ylenc"]
    nx0, ny0 = malla_n["xpc"], malla_n["ypc"]
    nx1, ny1 = nx0 + malla_n["xlenc"], ny0 + malla_n["ylenc"]
    if not (nx0 >= gx0 - 1e-6 and ny0 >= gy0 - 1e-6 and
            nx1 <= gx1 + 1e-6 and ny1 <= gy1 + 1e-6):
        errores.append("El nido no está contenido en el dominio grande; "
                       "ajusta su centro o tamaño para que quede dentro.")

    zg, zn = malla_g.get("zona_utm"), malla_n.get("zona_utm")
    if zg and zn and zg != zn:
        errores.append(f"El nido está en zona UTM {zn} y el grande en {zg}; "
                       f"deben coincidir.")

    cg = max(malla_g["xlenc"] / malla_g["mxc"], malla_g["ylenc"] / malla_g["myc"])
    cn = max(malla_n["xlenc"] / malla_n["mxc"], malla_n["ylenc"] / malla_n["myc"])
    if cn >= cg:
        avisos.append(f"La celda del nido (~{cn:.0f} m) no es más fina que la del "
                      f"grande (~{cg:.0f} m); el anidamiento aporta poco.")
    return errores, avisos


def escribir_par_anidado(carpeta, nombre_grande, nombre_nido, malla_g, bat_g,
                         bordes, malla_n, bat_n, salidas=("Hs", "Tp", "Dir"),
                         punto_espectral=None, estacionario=True, tiempo=None):
    """
    Escribe el par de `.swn` de un modelo anidado y devuelve (ruta_grande, ruta_nido).

    El grande lleva NGRID + NESTOUT (recuadro del nido); el nido lleva BOU NEST y,
    opcionalmente, un punto de salida espectral. Las mallas deben venir sin la clave
    'zona_utm' (se quita en la GUI antes de llamar).
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    sname, nestfile = "nido1", "nest1"
    nido = {"sname": sname, "nestfile": nestfile,
            "xpn": malla_n["xpc"], "ypn": malla_n["ypc"],
            "xlenn": malla_n["xlenc"], "ylenn": malla_n["ylenc"],
            "mxn": malla_n["mxc"], "myn": malla_n["myc"]}
    ruta_g = (carpeta / nombre_grande).with_suffix(".swn")
    ruta_g.write_text(construir_swn(nombre_grande, malla_g, bat_g, bordes,
                                    salidas=salidas, estacionario=estacionario,
                                    tiempo=tiempo, nido=nido), encoding="utf-8")
    ruta_n = (carpeta / nombre_nido).with_suffix(".swn")
    ruta_n.write_text(construir_swn(nombre_nido, malla_n, bat_n, [],
                                    salidas=salidas, estacionario=estacionario,
                                    tiempo=tiempo, bou_nest=nestfile,
                                    punto_espectral=punto_espectral),
                      encoding="utf-8")
    return ruta_g, ruta_n
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_nesting.py -v`
Expected: PASS (9 tests: 3 de Task 1 + 6 nuevos).

- [ ] **Step 5: Verificar regresión del motor**

Run: `python -m pytest test_regresion.py -q`
Expected: PASS (la firma de `validar_caso` es retrocompatible: `requiere_bordes=True` por defecto).

- [ ] **Step 6: Commit**

```bash
git add swan_builder.py test_nesting.py
git commit -m "feat: validar_caso_anidado y escribir_par_anidado (par grande+nido)"
```

---

## Task 3: Orden de corrida por dependencia de nesting

**Files:**
- Modify: `swan_runner.py`
- Test: `test_nesting.py`

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `test_nesting.py`:

```python
def test_casos_ordenados_nido_va_despues(tmp_path):
    (tmp_path / "grande.swn").write_text(
        "CGRID 0 0 0 100 100 10 10 Circle 180 .04 1\nCOMPUTE\nSTOP\n")
    (tmp_path / "chico.swn").write_text(
        "CGRID 5 5 0 50 50 10 10 Circle 180 .04 1\n"
        "BOU NEST 'nest1' CLOSED\nCOMPUTE\nSTOP\n")
    orden = swan_runner.casos_ordenados(str(tmp_path))
    assert orden.index("grande") < orden.index("chico")


def test_es_nido_detecta_bou_nest(tmp_path):
    p = tmp_path / "n.swn"
    p.write_text("CGRID 5 5 0 50 50 10 10\nBOU NEST 'x' CLOSED\nCOMPUTE\n")
    assert swan_runner._es_nido(p) is True
    p2 = tmp_path / "g.swn"
    p2.write_text("CGRID 0 0 0 100 100 10 10\nBOUN SIDE W CCW CON PAR 3 12 290 20\n")
    assert swan_runner._es_nido(p2) is False
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python -m pytest test_nesting.py -k "ordenados or es_nido" -v`
Expected: FAIL — `_es_nido` no existe.

- [ ] **Step 3: Modificar `swan_runner.py`**

Agregar el helper antes de `casos_ordenados`:

```python
def _es_nido(ruta_swn):
    """True si el .swn toma su contorno de un nesting (BOU NEST / BOUN NEST)."""
    for linea in Path(ruta_swn).read_text().splitlines():
        s = linea.strip()
        if s.startswith("$"):
            continue
        toks = s.upper().split()
        if len(toks) >= 2 and toks[0] in ("BOU", "BOUN") and toks[1] == "NEST":
            return True
    return False
```

Reemplazar el cuerpo de `casos_ordenados` por:

```python
def casos_ordenados(carpeta):
    """
    Nombres de caso (.swn sin extensión) en orden de ejecución: los dominios que
    alimentan un nesting primero, los anidados (BOU NEST) después.
    """
    swns = sorted(Path(carpeta).glob("*.swn"))

    def clave(s):
        try:
            return (_es_nido(s), s.name)
        except Exception:
            return (True, s.name)        # ilegible: al final

    return [s.stem for s in sorted(swns, key=clave)]
```

(El docstring antiguo mencionaba "CGRID con origen local 0,0"; queda reemplazado por la regla de nesting.)

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `python -m pytest test_nesting.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Verificar regresión (orden de Coronel intacto)**

Run: `python -m pytest test_regresion.py -q`
Expected: PASS. Si los datos de Coronel están en disco, el test de `casos_ordenados` sigue dando `[Coronel1, Coronelanidada]` (el grande no tiene `BOU NEST`, el nido sí). Si algún assert de regresión asumía el criterio viejo de origen 0,0 y falla, actualizarlo para reflejar el mismo orden resultante (no cambia el orden, solo el criterio).

- [ ] **Step 6: Commit**

```bash
git add swan_runner.py test_nesting.py
git commit -m "feat: casos_ordenados por dependencia de nesting (BOU NEST al final)"
```

---

## Task 4: `PasoNido` en el camino Modelar + `PasoCorrer` para 1 o 2 dominios

**Files:**
- Modify: `pasos_modelar.py`
- Test: `test_asistente.py`

- [ ] **Step 1: Escribir el test de composición que falla**

Agregar al final de `test_asistente.py`:

```python
def test_camino_modelar_tiene_seis_pasos_con_nido():
    import pasos_modelar
    import asistente
    assert len(pasos_modelar.PASOS_MODELAR) == 6
    assert all(issubclass(c, asistente.Paso) for c in pasos_modelar.PASOS_MODELAR)


def test_paso_nido_solo_agrega_dominio_si_esta_activo():
    import pasos_modelar
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        paso = pasos_modelar.PasoNido(root)
        # grande ya presente en el contexto
        ctx = {"dominios": [{"malla": {"xpc": 0}}]}
        paso.entrar(ctx)
        paso.activo.set(False)
        paso.recoger(ctx)
        assert len(ctx["dominios"]) == 1        # nido apagado: no agrega
    finally:
        root.destroy()
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python -m pytest test_asistente.py -k "seis_pasos or paso_nido" -v`
Expected: FAIL — `PASOS_MODELAR` tiene 5 y `PasoNido` no existe.

- [ ] **Step 3: Agregar `PasoNido` en `pasos_modelar.py`**

Insertar esta clase **antes** de `class PasoCorrer`:

```python
class PasoNido(asistente.Paso):
    titulo = "Dominio anidado (opcional)"

    def __init__(self, master):
        super().__init__(master)
        self.activo = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Agregar un dominio anidado (nido) más fino",
                        variable=self.activo, command=self._refrescar).pack(anchor="w")
        self.marco = ttk.Frame(self)
        self.marco.pack(fill="x", padx=(20, 0), pady=(6, 0))
        self._editables = []               # widgets a habilitar/deshabilitar

        # Malla del nido
        self.campos = {}
        for etiqueta, clave, valor in (
                ("Latitud centro", "lat", "-36.97"),
                ("Longitud centro", "lon", "-73.15"),
                ("Ancho [km]", "ancho", "9"),
                ("Alto [km]", "alto", "10"),
                ("Tamaño de celda [m]", "celda", "200")):
            f = ttk.Frame(self.marco); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ent = ttk.Entry(f, textvariable=var, width=14); ent.pack(side="left")
            self.campos[clave] = var
            self._editables.append(ent)
        self.boton_malla = ttk.Button(self.marco, text="Calcular malla del nido",
                                      command=self._calcular)
        self.boton_malla.pack(anchor="w", pady=(4, 0))
        self._editables.append(self.boton_malla)
        self.detalle = ttk.Label(self.marco, foreground="#555")
        self.detalle.pack(anchor="w")

        # Batimetría del nido
        self.bot = tk.StringVar()
        fb = ttk.Frame(self.marco); fb.pack(fill="x", pady=(6, 0))
        self.boton_bati = ttk.Button(fb, text="Generar batimetría del nido",
                                     command=self._bati)
        self.boton_bati.pack(side="left")
        self.boton_bot = ttk.Button(fb, text="Usar .bot propio…",
                                    command=self._elegir_bot)
        self.boton_bot.pack(side="left", padx=(6, 0))
        self._editables += [self.boton_bati, self.boton_bot]
        ttk.Label(self.marco, textvariable=self.bot, foreground="#555").pack(anchor="w")

        # Punto espectral
        self.con_espectro = tk.BooleanVar(value=False)
        self.check_esp = ttk.Checkbutton(self.marco, text="Salida espectral en un punto",
                                         variable=self.con_espectro)
        self.check_esp.pack(anchor="w", pady=(6, 0))
        self._editables.append(self.check_esp)
        fe = ttk.Frame(self.marco); fe.pack(fill="x")
        self.pe = {}
        for etiqueta, clave, valor in (("Lat punto", "lat", "-36.98"),
                                       ("Lon punto", "lon", "-73.13")):
            ttk.Label(fe, text=etiqueta).pack(side="left")
            var = tk.StringVar(value=valor)
            ent = ttk.Entry(fe, textvariable=var, width=10)
            ent.pack(side="left", padx=(2, 8))
            self.pe[clave] = var
            self._editables.append(ent)

        self.malla = None
        self._refrescar()

    def entrar(self, contexto):
        self._contexto = contexto

    def _refrescar(self):
        estado = "normal" if self.activo.get() else "disabled"
        for w in self._editables:
            try:
                w.config(state=estado)
            except tk.TclError:
                pass

    def _calcular(self):
        try:
            self.malla = geo_malla.malla_desde_latlon(
                float(self.campos["lat"].get()), float(self.campos["lon"].get()),
                float(self.campos["ancho"].get()), float(self.campos["alto"].get()),
                float(self.campos["celda"].get()))
        except (ValueError, KeyError) as e:
            messagebox.showerror("Datos inválidos", str(e)); return
        m = self.malla
        self.detalle.config(text=f"Nido: zona UTM {m['zona_utm']} · "
                            f"{m['mxc']}×{m['myc']} celdas.")

    def _bati(self):
        if self.malla is None:
            messagebox.showwarning("Falta la malla", "Calcula la malla del nido primero.")
            return
        destino = self._contexto.get("carpeta_caso")
        if not destino:
            messagebox.showwarning("Falta carpeta",
                                   "Genera primero la batimetría del dominio grande "
                                   "(define la carpeta del caso).")
            return
        malla = {k: v for k, v in self.malla.items() if k != "zona_utm"}

        def trabajo(log, progreso):
            ruta, meta = io_batimetria.generar_bot(
                malla, self.malla["zona_utm"], destino, nombre="bati_nido.bot")
            log(f"Batimetría del nido: {ruta.name} — prof. {meta['prof_min']:.1f} a "
                f"{meta['prof_max']:.1f} m, {meta['pct_tierra']:.0f}% en tierra.")
            return str(ruta)

        def al_terminar(res):
            if res:
                self.bot.set(res)

        self.wizard.tarea(trabajo, al_terminar)

    def _elegir_bot(self):
        r = filedialog.askopenfilename(
            title="Batimetría del nido (.bot)",
            initialdir=config.obtener("ultima_carpeta_swan"),
            filetypes=[("Batimetría", "*.bot"), ("Todos", "*.*")])
        if r:
            self.bot.set(r)

    def validar(self):
        if not self.activo.get():
            return True, ""                 # nido opcional, apagado
        if self.malla is None:
            return False, "Calcula la malla del nido o desactiva el dominio anidado."
        grande = self._contexto.get("dominios", [{}])[0].get("malla")
        if grande:
            errores, _ = swan_builder.validar_caso_anidado(grande, self.malla)
            if errores:
                return False, "\n".join(errores)
        b = self.bot.get().strip()
        if not b or not Path(b).exists():
            return False, "Genera o selecciona la batimetría del nido."
        return True, ""

    def recoger(self, contexto):
        if not self.activo.get():
            return
        dom = {"malla": self.malla, "bot": self.bot.get().strip()}
        if self.con_espectro.get():
            try:
                import pyproj
                este, norte = pyproj.Transformer.from_crs(
                    "EPSG:4326", f"EPSG:{io_batimetria.epsg_utm(self.malla['zona_utm'])}",
                    always_xy=True).transform(float(self.pe["lon"].get()),
                                              float(self.pe["lat"].get()))
                dom["punto_espectral"] = {"x": round(este), "y": round(norte),
                                          "archivo": "Espectro_Punto.txt"}
            except Exception:
                dom["punto_espectral"] = None
        contexto["dominios"].append(dom)
```

Cambiar la lista al final del archivo:

```python
PASOS_MODELAR = [PasoMalla, PasoBatimetria, PasoBorde, PasoNido, PasoCorrer, PasoVer]
```

- [ ] **Step 4: Reemplazar `PasoCorrer._correr` para 1 o 2 dominios**

Sustituir el método `_correr` completo de `PasoCorrer` por:

```python
    def _correr(self):
        ctx = self._contexto
        dominios = ctx.get("dominios", [])
        if not dominios or not ctx.get("carpeta_caso"):
            messagebox.showerror(
                "Faltan datos",
                "Completa malla, batimetría y borde antes de correr SWAN.")
            return
        g = dominios[0]
        if any(k not in g for k in ("malla", "bot", "bordes")):
            messagebox.showerror("Faltan datos",
                                 "Completa malla, batimetría y borde del dominio grande.")
            return
        destino = Path(ctx["carpeta_caso"])
        nombre = self.nombre.get().strip() or "MiCaso"
        bot_g = Path(g["bot"])
        if bot_g.parent != destino:
            (destino / bot_g.name).write_bytes(bot_g.read_bytes())
        malla_g = {k: v for k, v in g["malla"].items() if k != "zona_utm"}
        bordes = g["bordes"]

        errores, avisos = swan_builder.validar_caso(
            malla_g, {"archivo": bot_g.name}, bordes, carpeta=destino)

        anidado = len(dominios) >= 2
        if anidado:
            n = dominios[1]
            if any(k not in n for k in ("malla", "bot")):
                messagebox.showerror("Faltan datos",
                                     "Completa malla y batimetría del nido.")
                return
            bot_n = Path(n["bot"])
            if bot_n.parent != destino:
                (destino / bot_n.name).write_bytes(bot_n.read_bytes())
            malla_n = {k: v for k, v in n["malla"].items() if k != "zona_utm"}
            e_an, a_an = swan_builder.validar_caso_anidado(g["malla"], n["malla"])
            errores += e_an
            avisos += a_an
            e_n, a_n = swan_builder.validar_caso(
                malla_n, {"archivo": bot_n.name}, [], carpeta=destino,
                requiere_bordes=False)
            errores += e_n
            avisos += a_n

        if errores:
            messagebox.showerror("Revisa el caso", "\n\n".join(errores)); return
        if avisos and not messagebox.askyesno(
                "Advertencias", "\n\n".join(avisos) + "\n\n¿Continuar igual?"):
            return

        if anidado:
            n = dominios[1]
            malla_n = {k: v for k, v in n["malla"].items() if k != "zona_utm"}
            ruta_g, ruta_n = swan_builder.escribir_par_anidado(
                destino, nombre, nombre + "_nido",
                malla_g, {"archivo": bot_g.name}, bordes,
                malla_n, {"archivo": Path(n["bot"]).name},
                salidas=("Hs", "Tp", "Dir"),
                punto_espectral=n.get("punto_espectral"))
            self.wizard.log.insert("end",
                                   f"Par anidado generado: {ruta_g.name}, {ruta_n.name}\n")
        else:
            ruta_swn = swan_builder.escribir_caso(
                destino, nombre, nombre=nombre, malla=malla_g,
                batimetria={"archivo": bot_g.name}, bordes=bordes,
                salidas=("Hs", "Tp", "Dir"), estacionario=True)
            self.wizard.log.insert("end", f"Caso generado: {ruta_swn}\n")

        def trabajo(log, progreso):
            ok, _ = swan_runner.correr_swan(str(destino), log=log, progreso=progreso)
            return ok

        def al_terminar(ok):
            self.ok = bool(ok)
            self.wizard.log.insert(
                "end", "SWAN terminó.\n" if ok else "SWAN terminó con avisos.\n")

        self.wizard.tarea(trabajo, al_terminar)
```

- [ ] **Step 5: Correr los tests**

Run: `python -m pytest test_asistente.py -q`
Expected: PASS (incluye los 2 nuevos: 6 pasos y `PasoNido` apagado no agrega dominio).

- [ ] **Step 6: Smoke test no interactivo del paso**

Crear un archivo temporal FUERA del repo y correrlo vía stdin desde la carpeta del proyecto (no usar `mainloop`):

```
cd /ruta/al/tablero-oleaje && python - <<'PY'
import app_tablero, asistente
app = app_tablero.AppTablero()
app.update_idletasks(); app.update()
app.mostrar("modelar"); app.update()
w = app._vista
assert len(w.pasos) == 6
nido = w.pasos[3]
assert nido.titulo.startswith("Dominio anidado")
# apagado: los campos del nido están deshabilitados
nido.activo.set(False); nido._refrescar()
assert all(str(x.cget("state")) == "disabled" for x in nido._editables)
nido.activo.set(True); nido._refrescar()
assert all(str(x.cget("state")) == "normal" for x in nido._editables)
app.destroy()
print("SMOKE NIDO OK")
PY
```
Expected: `SMOKE NIDO OK`, sin traceback. Borrar cualquier temporal creado.

- [ ] **Step 7: Commit**

```bash
git add pasos_modelar.py test_asistente.py
git commit -m "feat: PasoNido en Modelar + PasoCorrer arma par anidado (1 o 2 dominios)"
```

---

## Task 5: Cierre — docs, regresión y verificación

**Files:**
- Modify: `README.md`, `HANDOFF.md`

- [ ] **Step 1: Actualizar `README.md`**

En la sección "Modo guiado", en el bullet de "Modelar propagación con SWAN", reemplazar la frase final "Un dominio por ahora; el modelo anidado (nido) llegará como ampliación de este camino." por:

```
Incluye un paso opcional para agregar un **dominio anidado (nido)** más fino:
define su malla por lat/lon y su propia batimetría, y la app arma el par
grande+nido (NGRID/NESTOUT ↔ BOU NEST) y lo corre en orden. Opcionalmente, un
punto de salida espectral en el nido.
```

- [ ] **Step 2: Actualizar `HANDOFF.md`**

En la sección "Modo guiado (asistente)", reemplazar el bullet "Hueco del nesting (continuidad del 2.º proyecto)…" por un bullet que diga que el nesting ya está implementado: `swan_builder` genera el par con `escribir_par_anidado` (NGRID/NESTOUT ↔ BOU NEST) y `validar_caso_anidado`; `swan_runner.casos_ordenados` ordena por `BOU NEST`; el camino Modelar tiene 6 pasos con `PasoNido` opcional (malla/batimetría fina + punto espectral); `PasoCorrer` arma 1 o 2 dominios. Mantener mención de que `contexto["dominios"]` es la lista que lo soporta.

- [ ] **Step 3: Correr toda la batería de tests**

Run: `python -m pytest -q`
Expected: PASS — `test_regresion.py` + `test_asistente.py` + `test_nesting.py`.

- [ ] **Step 4: Verificación manual (a cargo del usuario, anotar en el reporte)**

Abrir `python app_tablero.py` → Modelar → definir malla grande (lat/lon) → batimetría grande → borde → activar **Dominio anidado**, definir malla fina + batimetría del nido (+ punto espectral) → Correr → ver mapas de grande y nido. (Requiere SWAN instalado para la corrida real; sin SWAN, se verifica que los dos `.swn` + dos `.bot` se generan en la carpeta.)

- [ ] **Step 5: Commit**

```bash
git add README.md HANDOFF.md
git commit -m "docs: nesting en README y HANDOFF"
```

---

## Self-review (cobertura del spec)

- `construir_swn` con `nido`/`bou_nest`/`punto_espectral` → Task 1.
- `escribir_par_anidado` + `validar_caso_anidado` + `validar_caso(requiere_bordes)` → Task 2.
- Orden de corrida por `BOU NEST` (`_es_nido`, `casos_ordenados`) → Task 3.
- `PasoNido` opcional (malla/batimetría fina + punto espectral) insertado entre Borde y Correr → Task 4 (Steps 3).
- `PasoCorrer` arma 1 o 2 dominios; nido sin bordes (`requiere_bordes=False`) → Task 4 (Step 4).
- `PasoVer` sin cambios (tablero_swan autodetecta dominios) → no requiere tarea.
- Coordenadas UTM absolutas, misma zona, dos batimetrías → cubierto por `validar_caso_anidado` (Task 2) y el uso de `geo_malla`/`io_batimetria` en `PasoNido` (Task 4).
- Testing motor + composición → Tasks 1–4; regresión de orden Coronel → Task 3 Step 5.
- Docs → Task 5.

Consistencia de nombres verificada: `escribir_par_anidado`, `validar_caso_anidado`, `_es_nido`, `PasoNido`, claves `nido={sname,nestfile,xpn,ypn,xlenn,ylenn,mxn,myn}`, `punto_espectral={x,y,archivo}`, `contexto["dominios"]` con dicts `{malla, bot, bordes?, punto_espectral?}`.
