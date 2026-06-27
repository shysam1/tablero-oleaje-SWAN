# Asistente guiado del Tablero de Oleaje — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poner un modo guiado (pantalla de inicio + wizards paso a paso) encima de la app actual, sin reescribir motor ni perder funcionalidad, dejando preparado el hueco para el nesting.

**Architecture:** La ventana `AppTablero` pasa a ser un contenedor de vistas conmutables (Inicio, 3 wizards, Avanzado). Un mini-framework en `asistente.py` separa la máquina de estados (`MaquinaWizard`, pura y testeable) de la parte tkinter (`Paso`/`Wizard`). Cada paso reutiliza las funciones de módulo existentes; el trabajo pesado corre en hilo con barra y log comunes del wizard.

**Tech Stack:** Python 3.13, tkinter/ttk, pytest. Reusa `geo_malla`, `io_batimetria`, `borde_oleaje`, `io_era5`, `io_oleaje`, `validacion`, `productos`, `swan_builder`, `swan_runner`, `io_swan_nonst`, `tablero_oleaje`, `tablero_swan`, `video_swan`, `rutas`, `config`.

**Spec:** `docs/specs/2026-06-26-asistente-guiado-design.md`

---

## Estructura de archivos

- **Crear** `asistente.py` — `MaquinaWizard` (pura), `Paso` (ttk base), `Wizard` (ttk, barra de pasos + navegación + área común estado/progreso/log + helper `tarea` en hilo).
- **Crear** `pasos_ver.py` — pasos del camino "Ver corrida" + `PASOS_VER`.
- **Crear** `pasos_analizar.py` — pasos del camino "Analizar" + `PASOS_ANALIZAR`.
- **Crear** `pasos_modelar.py` — pasos del camino "Modelar" + `PASOS_MODELAR`.
- **Crear** `test_asistente.py` — tests de `MaquinaWizard` y de la composición de los caminos.
- **Modificar** `app_tablero.py` — `AppTablero` como contenedor de vistas; `VistaInicio`; `VistaAvanzado` (la GUI actual movida tal cual).

Convención: comentarios en español con tildes, `snake_case`, sin prints de debug.

---

## Task 1: Máquina de estados del wizard (núcleo testeable)

**Files:**
- Create: `asistente.py`
- Test: `test_asistente.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `test_asistente.py`:

```python
"""Tests del mini-framework de wizard (lógica pura, sin tkinter)."""
import asistente


class PasoFake:
    """Paso de mentira para probar la máquina sin tkinter."""
    def __init__(self, titulo, ok=True, msg="", marca=None):
        self.titulo = titulo
        self._ok = ok
        self._msg = msg
        self._marca = marca
        self.entradas = 0

    def entrar(self, contexto):
        self.entradas += 1

    def validar(self):
        return self._ok, self._msg

    def recoger(self, contexto):
        if self._marca is not None:
            contexto[self._marca] = True


def test_arranca_en_el_primer_paso():
    m = asistente.MaquinaWizard([PasoFake("a"), PasoFake("b")])
    assert m.indice == 0
    assert m.es_primero() and not m.es_ultimo()


def test_avanzar_valida_recoge_y_entra_al_siguiente():
    p0 = PasoFake("a", marca="hizo_a")
    p1 = PasoFake("b")
    m = asistente.MaquinaWizard([p0, p1])
    ok, msg = m.avanzar()
    assert ok and msg == ""
    assert m.indice == 1
    assert m.contexto["hizo_a"] is True   # recogió
    assert p1.entradas == 1               # entró al siguiente


def test_avanzar_bloquea_si_no_valida():
    p0 = PasoFake("a", ok=False, msg="falta algo", marca="hizo_a")
    m = asistente.MaquinaWizard([p0, PasoFake("b")])
    ok, msg = m.avanzar()
    assert not ok and msg == "falta algo"
    assert m.indice == 0                   # no avanzó
    assert "hizo_a" not in m.contexto      # no recogió


def test_ultimo_paso_recoge_pero_no_cambia_indice():
    p0 = PasoFake("a")
    p1 = PasoFake("b", marca="hizo_b")
    m = asistente.MaquinaWizard([p0, p1])
    m.avanzar()
    ok, _ = m.avanzar()                    # estando en el último
    assert ok
    assert m.indice == 1
    assert m.contexto["hizo_b"] is True


def test_retroceder():
    p0, p1 = PasoFake("a"), PasoFake("b")
    m = asistente.MaquinaWizard([p0, p1])
    m.avanzar()
    assert m.retroceder() is True
    assert m.indice == 0
    assert p0.entradas == 1                # vuelve a entrar al retroceder
    assert m.retroceder() is False         # ya en el primero


def test_lista_vacia_es_error():
    import pytest
    with pytest.raises(ValueError):
        asistente.MaquinaWizard([])
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `cd "Herramientas computacionales/Tablero Oleaje" && python -m pytest test_asistente.py -v`
Expected: FAIL — `AttributeError: module 'asistente' has no attribute 'MaquinaWizard'` (el módulo aún no existe).

- [ ] **Step 3: Escribir la implementación mínima**

Crear `asistente.py` con solo la máquina por ahora:

```python
"""
Mini-framework de wizard para el asistente guiado del Tablero de Oleaje.

Separa la lógica de navegación (MaquinaWizard, sin tkinter, testeable) de la
parte visual (Paso/Wizard, ttk). Cada paso declara entrar/validar/recoger y
comparte un dict `contexto` que viaja entre pasos.
"""


class MaquinaWizard:
    """
    Controla el orden de los pasos y el contexto compartido, sin tocar la GUI.

    Cada `paso` debe ofrecer:
      - entrar(contexto): se llama al mostrarlo,
      - validar() -> (ok: bool, mensaje: str),
      - recoger(contexto): guarda sus resultados en el contexto.
    """

    def __init__(self, pasos, contexto=None):
        if not pasos:
            raise ValueError("El wizard necesita al menos un paso.")
        self.pasos = list(pasos)
        self.contexto = contexto if contexto is not None else {}
        self.indice = 0

    def paso_actual(self):
        return self.pasos[self.indice]

    def es_primero(self):
        return self.indice == 0

    def es_ultimo(self):
        return self.indice == len(self.pasos) - 1

    def entrar(self):
        """Notifica al paso actual que se está mostrando."""
        self.paso_actual().entrar(self.contexto)

    def avanzar(self):
        """
        Valida el paso actual; si pasa, recoge en el contexto y avanza al
        siguiente (entrando en él). En el último paso recoge pero no cambia de
        índice. Devuelve (ok, mensaje).
        """
        ok, msg = self.paso_actual().validar()
        if not ok:
            return False, msg
        self.paso_actual().recoger(self.contexto)
        if not self.es_ultimo():
            self.indice += 1
            self.paso_actual().entrar(self.contexto)
        return True, ""

    def retroceder(self):
        """Vuelve al paso anterior (entrando en él). False si ya es el primero."""
        if self.es_primero():
            return False
        self.indice -= 1
        self.paso_actual().entrar(self.contexto)
        return True
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `python -m pytest test_asistente.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add asistente.py test_asistente.py
git commit -m "feat: MaquinaWizard, núcleo testeable del asistente guiado"
```

---

## Task 2: Parte visual del wizard (`Paso` y `Wizard`)

**Files:**
- Modify: `asistente.py` (añadir `Paso` y `Wizard` al final)

No lleva test automático (tkinter); se verifica al cablear el primer camino (Task 4). El núcleo ya está cubierto por Task 1.

- [ ] **Step 1: Añadir imports de tkinter al inicio de `asistente.py`**

Justo debajo del docstring de módulo, antes de `class MaquinaWizard`:

```python
import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
```

- [ ] **Step 2: Añadir `Paso` al final de `asistente.py`**

```python
class Paso(ttk.Frame):
    """
    Base de un paso del wizard. Subclasificar y sobreescribir lo necesario.
    `self.wizard` queda apuntando al Wizard contenedor (lo asigna el Wizard).
    """

    titulo = "Paso"

    def __init__(self, master):
        super().__init__(master, padding=4)
        self.wizard = None

    def entrar(self, contexto):
        """Se llama cada vez que el paso se muestra (incluido al retroceder)."""

    def validar(self):
        """Devuelve (ok, mensaje). Por defecto, siempre se puede avanzar."""
        return True, ""

    def recoger(self, contexto):
        """Guarda en `contexto` lo que el paso aporta. Por defecto, nada."""
```

- [ ] **Step 3: Añadir `Wizard` al final de `asistente.py`**

```python
class Wizard(ttk.Frame):
    """
    Vista de un camino guiado: barra de pasos, área del paso actual, fila de
    estado/progreso, log y botones ← Inicio / Atrás / Siguiente.

    `clases_paso`: lista de subclases de Paso (se instancian aquí).
    `al_inicio`:   callback sin argumentos para volver a la pantalla de inicio.
    """

    def __init__(self, master, titulo, clases_paso, al_inicio):
        super().__init__(master, padding=12)
        self.titulo_txt = titulo
        self.al_inicio = al_inicio
        self.contexto = {}
        self.pasos = [c(self) for c in clases_paso]
        for p in self.pasos:
            p.wizard = self
        self.maquina = MaquinaWizard(self.pasos, self.contexto)
        self._construir()
        self._mostrar_actual()

    # ------------------------------------------------------------------ UI
    def _construir(self):
        ttk.Label(self, text=self.titulo_txt,
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.barra_pasos = ttk.Label(self, foreground="#555")
        self.barra_pasos.pack(anchor="w", pady=(0, 8))

        # Área donde se apilan los pasos (uno visible a la vez con tkraise).
        self.area = ttk.Frame(self)
        self.area.pack(fill="both", expand=True)
        self.area.rowconfigure(0, weight=1)
        self.area.columnconfigure(0, weight=1)
        for p in self.pasos:
            p.grid(in_=self.area, row=0, column=0, sticky="nsew")

        # Estado + progreso + log comunes a todos los pasos.
        fila_e = ttk.Frame(self)
        fila_e.pack(fill="x", pady=(8, 0))
        self.estado = ttk.Label(fila_e, text="Listo.", foreground="#1f6feb")
        self.estado.pack(side="left")
        self.progreso = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progreso.pack(fill="x", pady=(4, 0))
        self.log = scrolledtext.ScrolledText(self, height=9, font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(6, 0))

        # Botones de navegación.
        fila_b = ttk.Frame(self)
        fila_b.pack(fill="x", pady=(8, 0))
        ttk.Button(fila_b, text="← Inicio",
                   command=self._volver_inicio).pack(side="left")
        self.boton_sig = ttk.Button(fila_b, text="Siguiente →",
                                    command=self._siguiente)
        self.boton_sig.pack(side="right")
        self.boton_atras = ttk.Button(fila_b, text="Atrás", command=self._atras)
        self.boton_atras.pack(side="right", padx=(0, 6))

    def _mostrar_actual(self):
        p = self.maquina.paso_actual()
        self.maquina.entrar()
        p.tkraise()
        self.barra_pasos.config(
            text=f"Paso {self.maquina.indice + 1} de {len(self.pasos)}: {p.titulo}")
        self.boton_atras.config(
            state="disabled" if self.maquina.es_primero() else "normal")
        self.boton_sig.config(
            text="Finalizar" if self.maquina.es_ultimo() else "Siguiente →")

    # -------------------------------------------------------------- navegación
    def _siguiente(self):
        era_ultimo = self.maquina.es_ultimo()
        ok, msg = self.maquina.avanzar()
        if not ok:
            messagebox.showwarning("Falta completar", msg)
            return
        if era_ultimo:
            self._volver_inicio()
        else:
            self._mostrar_actual()

    def _atras(self):
        if self.maquina.retroceder():
            self._mostrar_actual()

    def _volver_inicio(self):
        self.al_inicio()

    # ------------------------------------------------------- tarea en segundo plano
    def tarea(self, funcion, al_terminar=None):
        """
        Corre `funcion(log, progreso)` en un hilo, con la navegación bloqueada y
        barra indeterminada. `log(msg)` y `progreso(i, n)` son seguros desde el
        hilo. Al terminar llama `al_terminar(resultado)` en el hilo de la GUI
        (resultado=None si hubo excepción, que se vuelca al log).
        """
        self._bloquear(True)

        def log(msg):
            self.after(0, lambda: (self.log.insert("end", msg + "\n"),
                                   self.log.see("end")))

        def progreso(i, n):
            self.after(0, self._set_progreso, i, n)

        def worker():
            try:
                res = funcion(log, progreso)
                self.after(0, lambda: self._fin_tarea(res, al_terminar, None))
            except Exception:
                self.after(0, lambda: self._fin_tarea(None, al_terminar,
                                                      traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def _set_progreso(self, i, n):
        self.progreso.config(mode="determinate", maximum=max(n, 1), value=i + 1)
        self.estado.config(text=f"Procesando… {i + 1}/{n}", foreground="#d18616")

    def _bloquear(self, activo):
        estado = "disabled" if activo else "normal"
        self.boton_sig.config(state=estado)
        self.boton_atras.config(state=estado)
        if activo:
            self.progreso.config(mode="indeterminate")
            self.progreso.start(12)
            self.estado.config(text="Procesando…", foreground="#d18616")
        else:
            self.progreso.stop()
            self.progreso.config(mode="determinate", value=0)

    def _fin_tarea(self, resultado, al_terminar, error):
        self._bloquear(False)
        if error:
            self.log.insert("end", error + "\n")
            self.estado.config(text="Error. Revisa el detalle.", foreground="#d1242f")
        else:
            self.estado.config(text="Listo.", foreground="#1f6feb")
        if al_terminar:
            al_terminar(resultado)
```

- [ ] **Step 4: Verificar que el módulo importa sin errores**

Run: `python -c "import asistente; print('ok', asistente.Wizard, asistente.Paso)"`
Expected: imprime `ok <class 'asistente.Wizard'> <class 'asistente.Paso'>` sin traza de error.

- [ ] **Step 5: Commit**

```bash
git add asistente.py
git commit -m "feat: Paso y Wizard (parte visual del asistente)"
```

---

## Task 3: Refactor de AppTablero a contenedor de vistas + VistaAvanzado + VistaInicio

**Files:**
- Modify: `app_tablero.py`

Mueve la GUI actual a `VistaAvanzado` **sin cambiar su lógica**, convierte `AppTablero` en contenedor de vistas y agrega `VistaInicio`. Los wizards se cablean en la Task 4 en adelante (aquí los botones de inicio quedan conectados a un método que se completará).

- [ ] **Step 1: Reescribir `app_tablero.py`**

El contenido completo del archivo pasa a ser:

```python
"""
Interfaz gráfica del Tablero de Oleaje.

Arranca en una pantalla de inicio ("¿Qué querés hacer?") con tres caminos
guiados (analizar una serie, modelar con SWAN, ver una corrida existente) y un
acceso al modo avanzado, que es la caja de herramientas de siempre (selector +
Crear + Procesar SWAN + Descargar ERA5). Todo vive en la misma ventana, que
intercambia "vistas".
"""

import io
import os
import threading
import traceback
from contextlib import redirect_stdout
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

import tablero_oleaje
import tablero_swan
import video_swan
import io_swan_nonst
import gui_swan
import config
import io_era5
import rutas
import io_oleaje
import borde_oleaje
import asistente
import pasos_analizar
import pasos_modelar
import pasos_ver


def validar_inputs_era5(lat_txt, lon_txt, inicio, fin):
    """Convierte y valida lat/lon; devuelve (lat, lon). Lanza ValueError si no sirven."""
    lat = float(lat_txt)
    lon = float(lon_txt)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Latitud/longitud fuera de rango.")
    if not (inicio and fin):
        raise ValueError("Faltan fechas de inicio/fin.")
    return lat, lon


class VistaInicio(ttk.Frame):
    """Pantalla de inicio con las tres tarjetas de camino + acceso avanzado."""

    def __init__(self, master, ir_a):
        super().__init__(master, padding=16)
        self.ir_a = ir_a              # callback: ir_a(nombre_vista)
        ttk.Label(self, text="Tablero de Oleaje",
                  font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(self, text="¿Qué querés hacer?",
                  font=("Segoe UI", 12)).pack(anchor="w", pady=(2, 16))

        tarjetas = ttk.Frame(self)
        tarjetas.pack(fill="both", expand=True)
        datos = [
            ("📈  Analizar oleaje\nen un punto",
             "Datos propios o descargados de ERA5 → curvas, régimen extremo, "
             "espectro.", "analizar"),
            ("🌊  Modelar propagación\ncon SWAN",
             "Desde cero: malla → batimetría → borde → correr → mapas.", "modelar"),
            ("🗺️  Ver una corrida\nSWAN ya hecha",
             "Tenés la carpeta corrida y solo querés graficarla (mapas o video).",
             "ver"),
        ]
        for i, (titulo, desc, destino) in enumerate(datos):
            tarjetas.columnconfigure(i, weight=1)
            tarj = ttk.Frame(tarjetas, relief="solid", borderwidth=1, padding=12)
            tarj.grid(row=0, column=i, sticky="nsew", padx=6)
            ttk.Label(tarj, text=titulo, font=("Segoe UI", 12, "bold"),
                      justify="left").pack(anchor="w")
            ttk.Label(tarj, text=desc, foreground="#555", wraplength=180,
                      justify="left").pack(anchor="w", pady=(6, 10))
            ttk.Button(tarj, text="Empezar →",
                       command=lambda d=destino: self.ir_a(d)).pack(anchor="w")

        ttk.Button(self, text="Herramientas sueltas (modo avanzado) →",
                   command=lambda: self.ir_a("avanzado")).pack(anchor="e",
                                                               pady=(16, 0))


class VistaAvanzado(ttk.Frame):
    """La caja de herramientas de siempre: selector + Crear + SWAN + ERA5."""

    def __init__(self, master, al_inicio):
        super().__init__(master, padding=12)
        self.al_inicio = al_inicio
        self.ruta_datos = tk.StringVar(value="")
        # Offset UTM del nodo (0,0) del dominio grande SWAN (default: Golfo de
        # Arauco). Sólo afecta las etiquetas UTM de los mapas/videos.
        self.utm_x = tk.StringVar(value="620494")
        self.utm_y = tk.StringVar(value="5876451")
        self._construir_widgets()

    def _construir_widgets(self):
        fila_top = ttk.Frame(self)
        fila_top.pack(fill="x")
        ttk.Button(fila_top, text="← Inicio",
                   command=self.al_inicio).pack(side="left")
        ttk.Label(fila_top, text="Modo avanzado",
                  font=("Segoe UI", 16, "bold")).pack(side="left", padx=(10, 0))
        ttk.Label(self, text="Serie temporal (.mat/.csv/.nc) → curvas. "
                  "Carpeta SWAN → mapas. Carpeta SWAN no estacionaria → video.",
                  foreground="#555").pack(anchor="w", pady=(4, 10))

        # Selector: campo de texto + botones para archivo o carpeta SWAN.
        fila = ttk.Frame(self)
        fila.pack(fill="x", pady=4)
        ttk.Entry(fila, textvariable=self.ruta_datos).pack(
            side="left", fill="x", expand=True)
        ttk.Button(fila, text="Archivo…", command=self._elegir_archivo).pack(
            side="left", padx=(6, 0))
        ttk.Button(fila, text="Carpeta SWAN…", command=self._elegir_carpeta).pack(
            side="left", padx=(6, 0))

        fila_b = ttk.Frame(self)
        fila_b.pack(pady=10)
        self.boton_crear = ttk.Button(fila_b, text="Crear", command=self._crear)
        self.boton_crear.pack(side="left", ipadx=10, ipady=4)
        ttk.Button(fila_b, text="Procesar SWAN…", command=self._abrir_swan).pack(
            side="left", padx=(8, 0), ipadx=6, ipady=4)
        ttk.Button(fila_b, text="Descargar ERA5…", command=self._abrir_era5).pack(
            side="left", padx=(8, 0), ipadx=6, ipady=4)

        # Campo avanzado: offset UTM del dominio grande SWAN (sólo mapas/videos).
        fila_utm = ttk.Frame(self)
        fila_utm.pack(fill="x", pady=(0, 2))
        ttk.Label(fila_utm, text="Offset UTM grande (avanzado):",
                  foreground="#888").pack(side="left")
        ttk.Entry(fila_utm, textvariable=self.utm_x, width=10).pack(
            side="left", padx=(4, 0))
        ttk.Entry(fila_utm, textvariable=self.utm_y, width=10).pack(
            side="left", padx=(2, 0))

        self.estado = ttk.Label(self, text="Listo.", foreground="#1f6feb")
        self.estado.pack(anchor="w")

        # Barra de avance (sólo se llena en el modo video, frame a frame).
        self.progreso = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progreso.pack(fill="x", pady=(4, 0))

        # Consola embebida: muestra el reporte que el pipeline imprime.
        self.salida = scrolledtext.ScrolledText(self, height=14,
                                                font=("Consolas", 9))
        self.salida.pack(fill="both", expand=True, pady=(8, 0))

    def _abrir_swan(self):
        """Abre la ventana de corrida SWAN (el paso previo a graficar)."""
        gui_swan.VentanaSwan(self)

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
            self.after(0, self.ruta_datos.set, str(nc_serie))
            self.after(0, self._exito, buffer.getvalue(), str(carpeta))
        except Exception:
            self.after(0, self._error, buffer.getvalue() + "\n" + traceback.format_exc())

    def _elegir_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Selecciona el archivo de oleaje",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.mat *.csv *.nc"),
                       ("Todos los archivos", "*.*")])
        if ruta:
            self.ruta_datos.set(ruta)
            config.guardar("ultima_carpeta_datos", str(Path(ruta).parent))

    def _elegir_carpeta(self):
        ruta = filedialog.askdirectory(
            title="Selecciona la carpeta de corrida SWAN",
            initialdir=config.obtener("ultima_carpeta_datos"))
        if ruta:
            self.ruta_datos.set(ruta)
            config.guardar("ultima_carpeta_datos", str(Path(ruta).parent))

    def _crear(self):
        ruta = self.ruta_datos.get().strip()
        if not ruta:
            messagebox.showwarning("Falta el archivo",
                                   "Primero selecciona un archivo de oleaje.")
            return
        if not Path(ruta).exists():
            messagebox.showerror("Archivo no encontrado", f"No existe:\n{ruta}")
            return
        self.boton_crear.config(state="disabled")
        self.estado.config(text="Procesando…", foreground="#d18616")
        self.progreso["value"] = 0
        self.salida.delete("1.0", "end")
        threading.Thread(target=self._procesar, args=(ruta,), daemon=True).start()

    def _procesar(self, ruta):
        """Corre el pipeline capturando lo que imprime, fuera del hilo de la GUI."""
        buffer = io.StringIO()

        def progreso(i, n):
            self.after(0, self._set_progreso, i, n)

        try:
            with redirect_stdout(buffer):
                salida = self._despachar(Path(ruta), progreso)
            self.after(0, self._exito, buffer.getvalue(), str(salida))
        except Exception:
            self.after(0, self._error,
                       buffer.getvalue() + "\n" + traceback.format_exc())

    def _utm_large(self):
        """Offset UTM del campo avanzado, o None si está vacío/ inválido."""
        try:
            return (float(self.utm_x.get()), float(self.utm_y.get()))
        except ValueError:
            return None

    def _despachar(self, ruta, progreso):
        """
        Elige el pipeline según la entrada:
          carpeta SWAN no estacionaria → video del evento (con avance),
          carpeta SWAN estacionaria    → tablero de mapas,
          serie temporal               → tablero de curvas.
        """
        carpeta = ruta.parent if ruta.suffix.lower() == ".swn" else ruta
        utm = self._utm_large()
        if ruta.is_dir() or ruta.suffix.lower() == ".swn":
            if io_swan_nonst.es_corrida_nonst(carpeta):
                return video_swan.generar_videos(carpeta, multipanel=True,
                                                 utm_large=utm, progreso=progreso)[0]
            return tablero_swan.generar_tablero_swan(carpeta, utm_large=utm)
        return tablero_oleaje.generar_tablero(str(ruta))

    def _set_progreso(self, i, n):
        self.progreso["maximum"] = n
        self.progreso["value"] = i + 1
        self.estado.config(text=f"Generando video… frame {i + 1}/{n}",
                           foreground="#d18616")

    def _exito(self, reporte, ruta_salida):
        self.salida.insert("end", reporte + f"\nResultado: {ruta_salida}\n")
        self.estado.config(text="Listo.", foreground="#1f6feb")
        self.progreso["value"] = 0
        self.boton_crear.config(state="normal")
        try:
            os.startfile(ruta_salida)
        except Exception:
            pass

    def _error(self, mensaje):
        self.salida.insert("end", mensaje)
        self.estado.config(text="Error al generar el resultado.", foreground="#d1242f")
        self.progreso["value"] = 0
        self.boton_crear.config(state="normal")
        messagebox.showerror("Error",
                             "Ocurrió un problema. Revisa el detalle en la ventana.")


class AppTablero(tk.Tk):
    """Ventana principal: contenedor que intercambia vistas (inicio/wizards/avanzado)."""

    def __init__(self):
        super().__init__()
        self.title("Tablero de Oleaje")
        self.geometry("760x620")
        self.minsize(680, 560)
        self.contenedor = ttk.Frame(self)
        self.contenedor.pack(fill="both", expand=True)
        self.contenedor.rowconfigure(0, weight=1)
        self.contenedor.columnconfigure(0, weight=1)
        self._vista = None
        self.mostrar("inicio")

    def _crear_vista(self, nombre):
        """Crea la vista pedida (las vistas son de usar y tirar para empezar limpias)."""
        ir_inicio = lambda: self.mostrar("inicio")
        if nombre == "inicio":
            return VistaInicio(self.contenedor, ir_a=self.mostrar)
        if nombre == "avanzado":
            return VistaAvanzado(self.contenedor, al_inicio=ir_inicio)
        if nombre == "analizar":
            return asistente.Wizard(self.contenedor, "Analizar oleaje en un punto",
                                    pasos_analizar.PASOS_ANALIZAR, ir_inicio)
        if nombre == "modelar":
            return asistente.Wizard(self.contenedor, "Modelar propagación con SWAN",
                                    pasos_modelar.PASOS_MODELAR, ir_inicio)
        if nombre == "ver":
            return asistente.Wizard(self.contenedor, "Ver una corrida SWAN",
                                    pasos_ver.PASOS_VER, ir_inicio)
        raise ValueError(f"Vista desconocida: {nombre}")

    def mostrar(self, nombre):
        """Reemplaza la vista visible por una nueva instancia de `nombre`."""
        if self._vista is not None:
            self._vista.destroy()
        self._vista = self._crear_vista(nombre)
        self._vista.grid(row=0, column=0, sticky="nsew")


if __name__ == "__main__":
    AppTablero().mainloop()
```

> Nota: este archivo importa `pasos_analizar`, `pasos_modelar` y `pasos_ver`, que se crean en las Tasks 4–6. Para que la app abra antes de eso, esas tasks deben completarse; el orden recomendado es Task 4 (ver) → 5 (analizar) → 6 (modelar). Si querés validar la vista de inicio/avanzado de inmediato, comentá temporalmente esos tres `import` y las tres ramas del wizard en `_crear_vista`, y descomentá al implementar cada camino.

- [ ] **Step 2: Crear stubs mínimos de los tres módulos de pasos para que la app importe**

Para no romper el import mientras se construyen los caminos, crear archivos mínimos (se completan en sus tasks):

`pasos_ver.py`:
```python
"""Pasos del camino 'Ver una corrida SWAN' (se completan en su task)."""
PASOS_VER = []
```

`pasos_analizar.py`:
```python
"""Pasos del camino 'Analizar oleaje en un punto' (se completan en su task)."""
PASOS_ANALIZAR = []
```

`pasos_modelar.py`:
```python
"""Pasos del camino 'Modelar propagación con SWAN' (se completan en su task)."""
PASOS_MODELAR = []
```

(Una lista vacía hará fallar `MaquinaWizard`, pero esos caminos no se abren hasta tener pasos; inicio y avanzado funcionan.)

- [ ] **Step 3: Verificar que la app arranca en Inicio y el modo avanzado funciona**

Run: `python app_tablero.py`
Expected (verificación manual):
- Abre en la pantalla de inicio con las 3 tarjetas y el enlace de modo avanzado.
- "Herramientas sueltas (modo avanzado) →" muestra la GUI de siempre con su botón "← Inicio".
- En modo avanzado, "Crear" / "Procesar SWAN…" / "Descargar ERA5…" siguen funcionando igual que antes (probar al menos abrir "Procesar SWAN…").
- "← Inicio" vuelve a la pantalla de inicio.

- [ ] **Step 4: Correr la red de regresión del motor**

Run: `python -m pytest test_regresion.py test_asistente.py -q`
Expected: PASS (el motor no cambió; los tests del asistente siguen verdes).

- [ ] **Step 5: Commit**

```bash
git add app_tablero.py pasos_ver.py pasos_analizar.py pasos_modelar.py
git commit -m "feat: AppTablero como contenedor de vistas + VistaInicio + VistaAvanzado"
```

---

## Task 4: Camino "Ver corrida SWAN existente" (3 pasos)

**Files:**
- Modify: `pasos_ver.py`
- Test: `test_asistente.py` (añadir un test de composición)

Es el camino más simple: valida el patrón Wizard de punta a punta.

- [ ] **Step 1: Escribir `pasos_ver.py` completo**

```python
"""
Pasos del camino "Ver una corrida SWAN ya hecha".

1. Elegir la carpeta de la corrida.
2. Autodetectar si es estacionaria (mapas) o no estacionaria (video) y mostrar
   lo detectado; ofrecer el offset UTM avanzado.
3. Generar el producto (tablero de mapas o video) y abrirlo.
Reutiliza tablero_swan / video_swan / io_swan_nonst sin tocar el motor.
"""

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

import asistente
import config
import io_swan_nonst
import swan_runner
import tablero_swan
import video_swan


class PasoCarpeta(asistente.Paso):
    titulo = "Elegir carpeta de la corrida"

    def __init__(self, master):
        super().__init__(master)
        self.carpeta = tk.StringVar()
        ttk.Label(self, text="Carpeta con los archivos .swn y las salidas de SWAN:"
                  ).pack(anchor="w", pady=(0, 6))
        fila = ttk.Frame(self); fila.pack(fill="x")
        ttk.Entry(fila, textvariable=self.carpeta).pack(
            side="left", fill="x", expand=True)
        ttk.Button(fila, text="Carpeta…", command=self._elegir).pack(
            side="left", padx=(6, 0))
        self.detalle = ttk.Label(self, foreground="#555")
        self.detalle.pack(anchor="w", pady=(8, 0))

    def _elegir(self):
        d = filedialog.askdirectory(
            title="Carpeta de la corrida SWAN",
            initialdir=config.obtener("ultima_carpeta_swan"))
        if not d:
            return
        self.carpeta.set(d)
        config.guardar("ultima_carpeta_swan", d)
        casos = swan_runner.casos_ordenados(d)
        self.detalle.config(
            text=(f"Casos detectados: {', '.join(casos)}" if casos
                  else "No se encontraron archivos .swn en la carpeta."))

    def validar(self):
        d = self.carpeta.get().strip()
        if not d or not Path(d).is_dir():
            return False, "Elegí una carpeta válida con la corrida SWAN."
        return True, ""

    def recoger(self, contexto):
        contexto["carpeta"] = self.carpeta.get().strip()


class PasoTipo(asistente.Paso):
    titulo = "Tipo de corrida"

    def __init__(self, master):
        super().__init__(master)
        self.info = ttk.Label(self, foreground="#333", justify="left")
        self.info.pack(anchor="w")
        fila = ttk.Frame(self); fila.pack(fill="x", pady=(10, 0))
        ttk.Label(fila, text="Offset UTM grande (avanzado):",
                  foreground="#888").pack(side="left")
        self.utm_x = tk.StringVar(value="620494")
        self.utm_y = tk.StringVar(value="5876451")
        ttk.Entry(fila, textvariable=self.utm_x, width=10).pack(side="left", padx=(4, 0))
        ttk.Entry(fila, textvariable=self.utm_y, width=10).pack(side="left", padx=(2, 0))

    def entrar(self, contexto):
        carpeta = Path(contexto["carpeta"])
        self.nonst = io_swan_nonst.es_corrida_nonst(carpeta)
        tipo = ("no estacionaria → se generará un VIDEO del evento" if self.nonst
                else "estacionaria → se generará un TABLERO DE MAPAS")
        self.info.config(text=f"Carpeta: {carpeta.name}\nDetectada como {tipo}.")

    def recoger(self, contexto):
        contexto["nonst"] = self.nonst
        try:
            contexto["utm_large"] = (float(self.utm_x.get()), float(self.utm_y.get()))
        except ValueError:
            contexto["utm_large"] = None


class PasoGenerar(asistente.Paso):
    titulo = "Generar y ver"

    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Generá el producto y se abrirá al terminar.").pack(
            anchor="w")
        self.boton = ttk.Button(self, text="Generar", command=self._generar)
        self.boton.pack(anchor="w", pady=(8, 0))
        self.resultado = None

    def entrar(self, contexto):
        self._contexto = contexto
        self.resultado = None
        producto = "video" if contexto.get("nonst") else "tablero de mapas"
        self.boton.config(text=f"Generar {producto}")

    def _generar(self):
        ctx = self._contexto
        carpeta = ctx["carpeta"]
        utm = ctx.get("utm_large")
        nonst = ctx.get("nonst")

        def trabajo(log, progreso):
            if nonst:
                return video_swan.generar_videos(
                    carpeta, multipanel=True, utm_large=utm, progreso=progreso)[0]
            return tablero_swan.generar_tablero_swan(carpeta, utm_large=utm)

        def al_terminar(res):
            if res is None:
                return
            self.resultado = res
            self.wizard.log.insert("end", f"Resultado: {res}\n")
            try:
                os.startfile(str(res))
            except Exception:
                pass

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if self.resultado is None:
            return False, "Pulsá «Generar» y esperá a que termine antes de finalizar."
        return True, ""


PASOS_VER = [PasoCarpeta, PasoTipo, PasoGenerar]
```

- [ ] **Step 2: Añadir test de composición a `test_asistente.py`**

```python
def test_camino_ver_tiene_tres_pasos():
    import pasos_ver
    assert len(pasos_ver.PASOS_VER) == 3
    # son subclases de Paso
    import asistente
    assert all(issubclass(c, asistente.Paso) for c in pasos_ver.PASOS_VER)
```

- [ ] **Step 3: Correr los tests**

Run: `python -m pytest test_asistente.py -q`
Expected: PASS (incluye el nuevo test de composición).

- [ ] **Step 4: Verificación manual del camino**

Run: `python app_tablero.py`
Expected:
- Inicio → "Ver una corrida SWAN" → Empezar.
- Paso 1: elegir `Python/SWAN_Coronel/extremo_Tr100` (estacionaria). "Siguiente".
- Paso 2: dice "estacionaria → tablero de mapas". "Siguiente".
- Paso 3: "Generar tablero de mapas" → corre, abre el PNG, y recién ahí "Finalizar" vuelve a Inicio.
- Repetir con `Python/SWAN_Coronel/no_estacionario` y comprobar que detecta "no estacionaria → VIDEO" y lo genera (con barra de avance).

- [ ] **Step 5: Commit**

```bash
git add pasos_ver.py test_asistente.py
git commit -m "feat: camino guiado 'Ver corrida SWAN existente'"
```

---

## Task 5: Camino "Analizar oleaje en un punto" (3 pasos)

**Files:**
- Modify: `pasos_analizar.py`
- Test: `test_asistente.py`

- [ ] **Step 1: Escribir `pasos_analizar.py` completo**

```python
"""
Pasos del camino "Analizar oleaje en un punto".

1. Origen de datos: archivo propio (.mat/.csv/.nc) o descarga ERA5 por coordenada.
2. Revisión: carga, validación física y qué productos se podrán generar.
3. Generar el tablero de curvas y abrirlo.
Reutiliza io_era5 / io_oleaje / validacion / productos / tablero_oleaje / rutas.
"""

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import asistente
import config
import rutas
import io_era5
import io_oleaje
import validacion
import productos
import tablero_oleaje


class PasoOrigen(asistente.Paso):
    titulo = "Origen de los datos"

    def __init__(self, master):
        super().__init__(master)
        self.modo = tk.StringVar(value="archivo")
        self.ruta = tk.StringVar()
        ttk.Radiobutton(self, text="Tengo un archivo (.mat / .csv / .nc)",
                        variable=self.modo, value="archivo",
                        command=self._refrescar).pack(anchor="w")
        fila = ttk.Frame(self); fila.pack(fill="x", padx=(20, 0))
        ttk.Entry(fila, textvariable=self.ruta).pack(side="left", fill="x", expand=True)
        self.boton_arch = ttk.Button(fila, text="Archivo…", command=self._elegir)
        self.boton_arch.pack(side="left", padx=(6, 0))

        ttk.Radiobutton(self, text="Descargar de ERA5 por coordenada",
                        variable=self.modo, value="era5",
                        command=self._refrescar).pack(anchor="w", pady=(10, 0))
        self.marco_era5 = ttk.Frame(self)
        self.marco_era5.pack(fill="x", padx=(20, 0))
        self.campos = {}
        for etiqueta, clave, valor in [
                ("Latitud", "lat", "-37.0"), ("Longitud", "lon", "-73.5"),
                ("Inicio (YYYY-MM-DD)", "inicio", "2024-07-28"),
                ("Fin (YYYY-MM-DD)", "fin", "2024-07-29")]:
            f = ttk.Frame(self.marco_era5); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ttk.Entry(f, textvariable=var).pack(side="left", fill="x", expand=True)
            self.campos[clave] = var
        self.viento = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.marco_era5, text="Incluir viento (sea/swell)",
                        variable=self.viento).pack(anchor="w")
        self.boton_desc = ttk.Button(self.marco_era5, text="Descargar serie ERA5",
                                     command=self._descargar)
        self.boton_desc.pack(anchor="w", pady=(4, 0))
        self.nc_descargado = None
        self._refrescar()

    def _refrescar(self):
        es_arch = self.modo.get() == "archivo"
        self.boton_arch.config(state="normal" if es_arch else "disabled")
        estado_era5 = "normal" if not es_arch else "disabled"
        for hijo in self.marco_era5.winfo_children():
            try:
                hijo.config(state=estado_era5)
            except tk.TclError:
                pass

    def _elegir(self):
        r = filedialog.askopenfilename(
            title="Archivo de oleaje",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.mat *.csv *.nc"), ("Todos", "*.*")])
        if r:
            self.ruta.set(r)
            config.guardar("ultima_carpeta_datos", str(Path(r).parent))

    def _descargar(self):
        try:
            lat = float(self.campos["lat"].get()); lon = float(self.campos["lon"].get())
            inicio = self.campos["inicio"].get(); fin = self.campos["fin"].get()
            if not (inicio and fin):
                raise ValueError("Faltan fechas de inicio/fin.")
        except ValueError as e:
            messagebox.showerror("Datos inválidos", str(e)); return

        def trabajo(log, progreso):
            ds = io_era5.descargar_serie(lat, lon, inicio, fin,
                                         incluir_viento=self.viento.get())
            log(f"Serie ERA5 descargada: {ds.sizes.get('time', 0)} pasos.")
            carpeta = rutas.carpeta_salida(io_era5._nombre_fuente(lat, lon, "serie"))
            return str(carpeta / "era5_serie.nc")

        def al_terminar(nc):
            if nc is None:
                return
            self.nc_descargado = nc
            self.ruta.set(nc)
            self.wizard.log.insert("end", f"Listo: {nc}\n")

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if self.modo.get() == "archivo":
            r = self.ruta.get().strip()
            if not r or not Path(r).exists():
                return False, "Seleccioná un archivo de oleaje existente."
            return True, ""
        if not self.nc_descargado or not Path(self.nc_descargado).exists():
            return False, "Descargá la serie ERA5 antes de continuar."
        return True, ""

    def recoger(self, contexto):
        contexto["ruta_datos"] = self.ruta.get().strip()


class PasoRevision(asistente.Paso):
    titulo = "Revisión de los datos"

    def __init__(self, master):
        super().__init__(master)
        self.texto = tk.Text(self, height=14, font=("Consolas", 9), wrap="word")
        self.texto.pack(fill="both", expand=True)

    def entrar(self, contexto):
        self.texto.config(state="normal")
        self.texto.delete("1.0", "end")
        try:
            ds = io_oleaje.cargar(contexto["ruta_datos"])
        except Exception as e:
            self.texto.insert("end", f"No se pudo leer el archivo:\n{e}\n")
            self.texto.config(state="disabled")
            return
        variables = ", ".join(ds.data_vars) or "(ninguna)"
        n = int(ds.sizes.get("time", 0))
        self.texto.insert("end", f"Variables presentes: {variables}\n")
        self.texto.insert("end", f"Pasos de tiempo: {n}\n\n")
        self.texto.insert("end", "Validación física:\n")
        for r in validacion.validar(ds):
            if not r["aplicable"]:
                self.texto.insert("end", f"  [n/a] {r['nombre']}: {r['detalle']}\n")
            elif r["n_falla"] == 0:
                self.texto.insert("end", f"  [ok ] {r['nombre']}\n")
            else:
                self.texto.insert("end",
                                  f"  [!! ] {r['nombre']}: {r['n_falla']}/{r['n_total']}\n")
        self.texto.insert("end", "\nProductos que se podrán generar:\n")
        for it in productos.evaluar(ds):
            if it["disponible"]:
                self.texto.insert("end", f"  ✓ {it['nombre']}\n")
            else:
                self.texto.insert("end",
                                  f"  ✗ {it['nombre']} (faltan: {', '.join(it['faltan'])})\n")
        self.texto.config(state="disabled")


class PasoTablero(asistente.Paso):
    titulo = "Generar el tablero"

    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Genera el tablero de curvas y se abre al terminar."
                  ).pack(anchor="w")
        ttk.Button(self, text="Generar tablero",
                   command=self._generar).pack(anchor="w", pady=(8, 0))
        self.resultado = None

    def entrar(self, contexto):
        self._contexto = contexto
        self.resultado = None

    def _generar(self):
        ruta = self._contexto["ruta_datos"]

        def trabajo(log, progreso):
            return tablero_oleaje.generar_tablero(str(ruta))

        def al_terminar(res):
            if res is None:
                return
            self.resultado = res
            self.wizard.log.insert("end", f"Resultado: {res}\n")
            try:
                os.startfile(str(res))
            except Exception:
                pass

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if self.resultado is None:
            return False, "Pulsá «Generar tablero» y esperá a que termine."
        return True, ""


PASOS_ANALIZAR = [PasoOrigen, PasoRevision, PasoTablero]
```

- [ ] **Step 2: Añadir test de composición**

En `test_asistente.py`:
```python
def test_camino_analizar_tiene_tres_pasos():
    import pasos_analizar, asistente
    assert len(pasos_analizar.PASOS_ANALIZAR) == 3
    assert all(issubclass(c, asistente.Paso) for c in pasos_analizar.PASOS_ANALIZAR)
```

- [ ] **Step 3: Correr los tests**

Run: `python -m pytest test_asistente.py -q`
Expected: PASS.

- [ ] **Step 4: Verificación manual**

Run: `python app_tablero.py`
Expected:
- Inicio → "Analizar oleaje en un punto".
- Paso 1, modo archivo: elegir `Python/Tarea 3 Costas/Datos_Nodo10_37S_75W_Talcahuano.mat` → Siguiente.
- Paso 2: lista variables (Hs, Tp, Dir), validación y productos disponibles.
- Paso 3: "Generar tablero" → abre el PNG; "Finalizar" vuelve a Inicio.
- (Si hay `~/.cdsapirc`) probar el modo ERA5 con un rango corto.

- [ ] **Step 5: Commit**

```bash
git add pasos_analizar.py test_asistente.py
git commit -m "feat: camino guiado 'Analizar oleaje en un punto'"
```

---

## Task 6: Camino "Modelar propagación con SWAN" (5 pasos, un dominio + hueco nesting)

**Files:**
- Modify: `pasos_modelar.py`
- Test: `test_asistente.py`

El `contexto["dominios"]` es una **lista** desde ya (un solo dominio en v1); los pasos Correr y Ver iteran sobre ella, dejando el nesting como aditivo.

- [ ] **Step 1: Escribir `pasos_modelar.py` completo**

```python
"""
Pasos del camino "Modelar propagación con SWAN" (un dominio en v1).

1. Malla: por lat/lon (centro + tamaño + celda) → geo_malla.
2. Batimetría: descarga automática (GEBCO/ETOPO) o .bot propio → io_batimetria.
3. Borde: manual o derivado de ERA5/serie → borde_oleaje.
4. Correr SWAN: validar_caso → escribir_caso → swan_runner.
5. Ver: tablero_swan del resultado.

El contexto guarda `dominios` como lista (preparado para el nido del 2º
proyecto): en v1 hay un único dominio.
"""

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import asistente
import config
import geo_malla
import io_batimetria
import io_oleaje
import borde_oleaje
import gui_swan
import swan_builder
import swan_runner
import tablero_swan


def _dominio_actual(contexto):
    """Devuelve el dict del dominio en construcción (crea la lista si hace falta)."""
    if "dominios" not in contexto:
        contexto["dominios"] = [{}]
    return contexto["dominios"][0]


class PasoMalla(asistente.Paso):
    titulo = "Malla de cómputo (por lat/lon)"

    def __init__(self, master):
        super().__init__(master)
        self.campos = {}
        for etiqueta, clave, valor in (
                ("Latitud centro", "lat", "-32.97"),
                ("Longitud centro", "lon", "-71.55"),
                ("Ancho [km]", "ancho", "8"),
                ("Alto [km]", "alto", "8"),
                ("Tamaño de celda [m]", "celda", "100")):
            f = ttk.Frame(self); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=20).pack(side="left")
            var = tk.StringVar(value=valor)
            ttk.Entry(f, textvariable=var, width=14).pack(side="left")
            self.campos[clave] = var
        ttk.Button(self, text="Calcular malla", command=self._calcular).pack(
            anchor="w", pady=(6, 0))
        self.detalle = ttk.Label(self, foreground="#555")
        self.detalle.pack(anchor="w", pady=(6, 0))
        self.malla = None

    def _calcular(self):
        try:
            self.malla = geo_malla.malla_desde_latlon(
                float(self.campos["lat"].get()), float(self.campos["lon"].get()),
                float(self.campos["ancho"].get()), float(self.campos["alto"].get()),
                float(self.campos["celda"].get()))
        except (ValueError, KeyError) as e:
            messagebox.showerror("Datos inválidos", str(e)); return
        m = self.malla
        self.detalle.config(
            text=f"Zona UTM {m['zona_utm']} · {m['mxc']}×{m['myc']} celdas · "
                 f"origen UTM ({m['xpc']:.0f}, {m['ypc']:.0f}).")

    def validar(self):
        if self.malla is None:
            return False, "Pulsá «Calcular malla» con valores válidos."
        return True, ""

    def recoger(self, contexto):
        dom = _dominio_actual(contexto)
        dom["malla"] = self.malla
        dom["zona_utm"] = self.malla["zona_utm"]


class PasoBatimetria(asistente.Paso):
    titulo = "Batimetría"

    def __init__(self, master):
        super().__init__(master)
        self.bot = tk.StringVar()
        ttk.Label(self, text="Necesitás un archivo .bot que cubra la malla."
                  ).pack(anchor="w")
        ttk.Button(self, text="Descargar batimetría automática (GEBCO/ETOPO)",
                   command=self._descargar).pack(anchor="w", pady=(8, 0))
        ttk.Button(self, text="Usar un .bot propio…",
                   command=self._elegir).pack(anchor="w", pady=(4, 0))
        self.detalle = ttk.Label(self, textvariable=self.bot, foreground="#555")
        self.detalle.pack(anchor="w", pady=(8, 0))

    def entrar(self, contexto):
        self._contexto = contexto

    def _carpeta_destino(self):
        """Carpeta del caso: se pide una vez y se guarda en el contexto."""
        ctx = self._contexto
        if ctx.get("carpeta_caso"):
            return ctx["carpeta_caso"]
        d = filedialog.askdirectory(
            title="Carpeta donde se armará el caso SWAN",
            initialdir=config.obtener("ultima_carpeta_swan"))
        if d:
            ctx["carpeta_caso"] = d
            config.guardar("ultima_carpeta_swan", d)
        return d

    def _descargar(self):
        ctx = self._contexto
        dom = _dominio_actual(ctx)
        if "malla" not in dom:
            messagebox.showwarning("Falta la malla", "Definí la malla primero.")
            return
        destino = self._carpeta_destino()
        if not destino:
            return
        malla = dom["malla"]
        zona = dom["zona_utm"]

        def trabajo(log, progreso):
            ruta, meta = io_batimetria.generar_bot(malla, zona, destino)
            log(f"Batimetría: {ruta.name} — prof. {meta['prof_min']:.1f} a "
                f"{meta['prof_max']:.1f} m, {meta['pct_tierra']:.0f}% en tierra.")
            return str(ruta)

        def al_terminar(res):
            if res:
                self.bot.set(res)

        self.wizard.tarea(trabajo, al_terminar)

    def _elegir(self):
        r = filedialog.askopenfilename(
            title="Batimetría SWAN (.bot)",
            initialdir=config.obtener("ultima_carpeta_swan"),
            filetypes=[("Batimetría", "*.bot"), ("Todos", "*.*")])
        if r:
            self.bot.set(r)

    def validar(self):
        b = self.bot.get().strip()
        if not b or not Path(b).exists():
            return False, "Generá o seleccioná un archivo de batimetría .bot."
        return True, ""

    def recoger(self, contexto):
        _dominio_actual(contexto)["bot"] = self.bot.get().strip()


class PasoBorde(asistente.Paso):
    titulo = "Condición de borde"

    def __init__(self, master):
        super().__init__(master)
        self.v = {}
        for etiqueta, clave, valor in (("Hs [m]", "hs", "3.0"), ("Tp [s]", "per", "12.0"),
                                       ("Dir [°] (náutica)", "dir", "290.0"),
                                       ("Dispersión [°]", "dd", "20.0")):
            f = ttk.Frame(self); f.pack(fill="x", pady=2)
            ttk.Label(f, text=etiqueta, width=18).pack(side="left")
            var = tk.StringVar(value=valor)
            ttk.Entry(f, textvariable=var, width=10).pack(side="left")
            self.v[clave] = var
        lad = ttk.Frame(self); lad.pack(fill="x", pady=(6, 0))
        ttk.Label(lad, text="Lados de entrada:").pack(side="left")
        self.lados = {}
        for s in ("N", "S", "E", "W"):
            var = tk.BooleanVar(value=s in ("N", "W"))
            ttk.Checkbutton(lad, text=s, variable=var).pack(side="left")
            self.lados[s] = var
        ttk.Button(self, text="Derivar de ERA5/serie…",
                   command=self._derivar).pack(anchor="w", pady=(8, 0))

    def _derivar(self):
        r = filedialog.askopenfilename(
            title="Serie de oleaje (ERA5/.mat/.csv/.nc)",
            initialdir=config.obtener("ultima_carpeta_datos"),
            filetypes=[("Datos de oleaje", "*.nc *.mat *.csv"), ("Todos", "*.*")])
        if not r:
            return
        cond = gui_swan.dialogo_condicion(self)
        if not cond:
            return
        modo, tr = cond
        try:
            ds = io_oleaje.cargar(r)
            borde = borde_oleaje.condicion_borde(ds, modo, tr)
        except Exception as e:
            messagebox.showerror("No se pudo derivar el borde", str(e)); return
        for clave in ("hs", "per", "dir"):
            val = borde.get(clave)
            self.v[clave].set("" if val is None else f"{val:g}")
        self.wizard.log.insert("end", f"Borde derivado — {borde.get('descripcion','')}\n")

    def validar(self):
        try:
            hs = float(self.v["hs"].get()); per = float(self.v["per"].get())
            float(self.v["dir"].get()); float(self.v["dd"].get())
        except ValueError:
            return False, "Revisá los valores del borde (deben ser números)."
        if hs <= 0 or per <= 0:
            return False, "Hs y Tp deben ser mayores que cero."
        if not any(v.get() for v in self.lados.values()):
            return False, "Elegí al menos un lado de entrada del oleaje."
        return True, ""

    def recoger(self, contexto):
        bordes = [{"lado": s, "hs": float(self.v["hs"].get()),
                   "per": float(self.v["per"].get()),
                   "dir": float(self.v["dir"].get()),
                   "dd": float(self.v["dd"].get())}
                  for s, on in self.lados.items() if on.get()]
        _dominio_actual(contexto)["bordes"] = bordes


class PasoCorrer(asistente.Paso):
    titulo = "Correr SWAN"

    def __init__(self, master):
        super().__init__(master)
        self.nombre = tk.StringVar(value="MiCaso")
        f = ttk.Frame(self); f.pack(fill="x")
        ttk.Label(f, text="Nombre del caso:", width=18).pack(side="left")
        ttk.Entry(f, textvariable=self.nombre, width=20).pack(side="left")
        ttk.Button(self, text="Generar .swn y correr",
                   command=self._correr).pack(anchor="w", pady=(8, 0))
        self.ok = False

    def entrar(self, contexto):
        self._contexto = contexto
        self.ok = False

    def _correr(self):
        ctx = self._contexto
        dom = ctx["dominios"][0]
        destino = Path(ctx["carpeta_caso"])
        bot = Path(dom["bot"])
        # Copiar la batimetría a la carpeta del caso (rutas relativas en el .swn).
        if bot.parent != destino:
            (destino / bot.name).write_bytes(bot.read_bytes())
        malla = dict(dom["malla"]); malla.pop("zona_utm", None)
        bordes = dom["bordes"]

        errores, avisos = swan_builder.validar_caso(
            malla, {"archivo": bot.name}, bordes, carpeta=destino)
        if errores:
            messagebox.showerror("Revisá el caso", "\n\n".join(errores)); return
        if avisos and not messagebox.askyesno(
                "Advertencias", "\n\n".join(avisos) + "\n\n¿Continuar igual?"):
            return
        nombre = self.nombre.get().strip() or "MiCaso"
        ruta_swn = swan_builder.escribir_caso(
            destino, nombre, nombre=nombre, malla=malla,
            batimetria={"archivo": bot.name}, bordes=bordes,
            salidas=("Hs", "Tp", "Dir"), estacionario=True)
        self.wizard.log.insert("end", f"Caso generado: {ruta_swn}\n")

        def trabajo(log, progreso):
            ok, nuevas = swan_runner.correr_swan(str(destino), log=log,
                                                 progreso=progreso)
            return ok

        def al_terminar(ok):
            self.ok = bool(ok)
            self.wizard.log.insert(
                "end", "SWAN terminó.\n" if ok else "SWAN terminó con avisos.\n")

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if not self.ok:
            return False, "Corré SWAN y esperá a que termine antes de continuar."
        return True, ""

    def recoger(self, contexto):
        contexto["carpeta_resultado"] = contexto["carpeta_caso"]


class PasoVer(asistente.Paso):
    titulo = "Ver resultados"

    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Genera el tablero de mapas de la corrida."
                  ).pack(anchor="w")
        ttk.Button(self, text="Generar mapas",
                   command=self._generar).pack(anchor="w", pady=(8, 0))
        self.resultado = None

    def entrar(self, contexto):
        self._contexto = contexto
        self.resultado = None

    def _generar(self):
        carpeta = self._contexto["carpeta_resultado"]

        def trabajo(log, progreso):
            return tablero_swan.generar_tablero_swan(carpeta)

        def al_terminar(res):
            if res is None:
                return
            self.resultado = res
            self.wizard.log.insert("end", f"Resultado: {res}\n")
            try:
                os.startfile(str(res))
            except Exception:
                pass

        self.wizard.tarea(trabajo, al_terminar)

    def validar(self):
        if self.resultado is None:
            return False, "Pulsá «Generar mapas» y esperá a que termine."
        return True, ""


PASOS_MODELAR = [PasoMalla, PasoBatimetria, PasoBorde, PasoCorrer, PasoVer]
```

- [ ] **Step 2: Añadir tests de composición y del hueco del nesting**

En `test_asistente.py`:
```python
def test_camino_modelar_tiene_cinco_pasos():
    import pasos_modelar, asistente
    assert len(pasos_modelar.PASOS_MODELAR) == 5
    assert all(issubclass(c, asistente.Paso) for c in pasos_modelar.PASOS_MODELAR)


def test_dominio_actual_crea_lista_para_el_nesting():
    import pasos_modelar
    ctx = {}
    dom = pasos_modelar._dominio_actual(ctx)
    assert ctx["dominios"] == [dom]      # estructura de lista lista para el nido
    dom["malla"] = {"x": 1}
    assert pasos_modelar._dominio_actual(ctx) is dom   # no duplica
```

- [ ] **Step 3: Correr los tests**

Run: `python -m pytest test_asistente.py -q`
Expected: PASS (incluye los dos tests nuevos).

- [ ] **Step 4: Verificación manual end-to-end**

Run: `python app_tablero.py`
Expected:
- Inicio → "Modelar propagación con SWAN".
- Paso 1: Reñaca (−32.97, −71.55, 6×6 km, 150 m) → "Calcular malla" → muestra zona 19S.
- Paso 2: elegir carpeta destino vacía → "Descargar batimetría automática" → muestra profundidad/% tierra.
- Paso 3: dejar borde manual (Hs 3, Tp 12, Dir 290, lados N+W) → Siguiente.
- Paso 4: "Generar .swn y correr" → corre SWAN (barra animada) → "SWAN terminó".
- Paso 5: "Generar mapas" → abre el PNG; "Finalizar" vuelve a Inicio.

(Si SWAN no está instalado, el paso 4 mostrará el error de `swan_runner` en el log; el resto del flujo igual queda verificado.)

- [ ] **Step 5: Commit**

```bash
git add pasos_modelar.py test_asistente.py
git commit -m "feat: camino guiado 'Modelar propagación con SWAN' (un dominio; hueco nesting)"
```

---

## Task 7: Cierre — docs, regresión y verificación final

**Files:**
- Modify: `README.md`, `HANDOFF.md`

- [ ] **Step 1: Actualizar `README.md`**

Añadir una sección "Modo guiado" que explique: la app abre en una pantalla de inicio con tres caminos (analizar / modelar / ver); cada uno es un wizard paso a paso; el modo avanzado (botón "Herramientas sueltas") conserva la caja de herramientas de siempre. Mencionar que el motor es el mismo y que el nesting (modelo anidado) llegará como ampliación del camino "Modelar".

- [ ] **Step 2: Actualizar `HANDOFF.md`**

Añadir un apartado describiendo `asistente.py` (MaquinaWizard/Paso/Wizard), los tres módulos `pasos_*.py`, y que `app_tablero.py` ahora es un contenedor de vistas con `VistaInicio`/`VistaAvanzado`. Anotar el hueco del nesting (`contexto["dominios"]` como lista; pasos Correr/Ver iteran sobre ella) como punto de continuidad del 2.º proyecto.

- [ ] **Step 3: Correr toda la batería de tests**

Run: `python -m pytest -q`
Expected: PASS — `test_regresion.py` (motor intacto) + `test_asistente.py` (núcleo + composición de los 3 caminos).

- [ ] **Step 4: Verificación manual de no-regresión del modo avanzado**

Run: `python app_tablero.py` → modo avanzado → comprobar que "Crear" sobre un `.mat` y "Procesar SWAN…" siguen funcionando como antes (cero funcionalidad perdida).

- [ ] **Step 5: Commit**

```bash
git add README.md HANDOFF.md
git commit -m "docs: modo guiado en README y HANDOFF"
```

---

## Self-review (cobertura del spec)

- Pantalla de inicio con 3 caminos + acceso avanzado → Task 3 (`VistaInicio`).
- Mini-framework `Paso`/`Wizard` + `contexto` + máquina de estados testeable → Tasks 1–2.
- Vistas conmutables en la misma ventana → Task 3 (`AppTablero.mostrar`).
- Modo avanzado = GUI actual intacta → Task 3 (`VistaAvanzado`, código portado sin cambios de lógica).
- Camino Analizar (origen archivo/ERA5 → revisión → tablero) → Task 5.
- Camino Modelar (malla → batimetría → borde → correr → ver) → Task 6.
- Camino Ver (carpeta → autodetección → generar) → Task 4.
- Hueco del nesting (`contexto["dominios"]` lista; iterable) → Task 6 (`_dominio_actual`, test dedicado).
- No perder funcionalidad → Task 3 Step 3–4 + Task 7 Step 4 (verificación de "Crear"/"Procesar SWAN…").
- Reuso de motor sin reescritura → todos los pasos llaman a funciones existentes; `test_regresion.py` se mantiene verde (Task 3/7).
- Testing del framework con pasos fake → Task 1; composición de caminos → Tasks 4–6.
- Lanzadores .lnk/.bat siguen abriendo `app_tablero` (arranca en inicio) → sin cambios en los lanzadores (Task 3 mantiene `if __name__ == "__main__": AppTablero().mainloop()`).
