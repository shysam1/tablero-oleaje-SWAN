"""
Mini-framework de wizard para el asistente guiado del Tablero de Oleaje.

Separa la lógica de navegación (MaquinaWizard, sin tkinter, testeable) de la
parte visual (Paso/Wizard, ttk). Cada paso declara entrar/validar/recoger y
comparte un dict `contexto` que viaja entre pasos.
"""

import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


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

        Contrato para el caller: en el último paso `avanzar` recoge y devuelve
        (True, "") sin cambiar de índice, así que el caller debe consultar
        `es_ultimo()` ANTES de llamar a `avanzar` para decidir si cierra el wizard.
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
        self._tarea_activa = False
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
        hilo. `progreso(i, n)` espera `i` en base 0 (la barra muestra `i + 1` de
        `n`). Al terminar llama `al_terminar(resultado)` en el hilo de la GUI
        (resultado=None si hubo excepción, que se vuelca al log).
        """
        if self._tarea_activa:
            return                         # ya hay una tarea en curso; ignorar reentradas
        self._tarea_activa = True
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
        self._tarea_activa = False
        self._bloquear(False)
        if error:
            self.log.insert("end", error + "\n")
            self.estado.config(text="Error. Revisa el detalle.", foreground="#d1242f")
        else:
            self.estado.config(text="Listo.", foreground="#1f6feb")
        if al_terminar:
            al_terminar(resultado)
