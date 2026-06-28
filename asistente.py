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

import estilo


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
        super().__init__(master, padding=4, style="Card.TFrame")
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
        super().__init__(master, padding=16)
        self.titulo_txt = titulo
        self.al_inicio = al_inicio
        self.contexto = {}
        self._tarea_activa = False
        self._clases_paso = clases_paso
        self.pasos = []
        self.maquina = None
        self._construir()
        self.pasos = [c(self.area) for c in self._clases_paso]
        for p in self.pasos:
            p.wizard = self
            p.grid(row=0, column=0, sticky="nsew")
        titulos = [p.titulo for p in self.pasos]
        self.stepper = estilo.Stepper(self, titulos)
        self.stepper.pack(fill="x", pady=(10, 6), after=self._titulo_w)
        self.maquina = MaquinaWizard(self.pasos, self.contexto)
        self.maquina.entrar()
        self._mostrar_actual()

    # ------------------------------------------------------------------ UI
    def _construir(self):
        self._titulo_w = ttk.Label(self, text=self.titulo_txt,
                                   style="WizardTitulo.TLabel")
        self._titulo_w.pack(anchor="w")

        self.barra_pasos = ttk.Label(self, style="Muted.TLabel")
        self.barra_pasos.pack(anchor="w", pady=(0, 10))

        marco_paso = estilo.PanelTarjeta(self)
        marco_paso.pack(fill="both", expand=True)
        self.area = tk.Frame(marco_paso.cuerpo, bg=estilo.PALETA["fondo_tarjeta"])
        self.area.pack(fill="both", expand=True)
        self.area.rowconfigure(0, weight=1)
        self.area.columnconfigure(0, weight=1)

        # Estado + progreso + log comunes a todos los pasos.
        fila_e = ttk.Frame(self)
        fila_e.pack(fill="x", pady=(8, 0))
        self.estado = ttk.Label(fila_e, text="Listo.", style="EstadoListo.TLabel")
        self.estado.pack(side="left")
        self.progreso = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progreso.pack(fill="x", pady=(4, 0))
        self.log = scrolledtext.ScrolledText(
            self, height=7, font=("Consolas", 9),
            bg="#fafafa", fg=estilo.PALETA["texto"], relief="flat",
            highlightthickness=1, highlightbackground=estilo.PALETA["borde_suave"])
        self.log.pack(fill="both", expand=True, pady=(6, 0))

        # Botones de navegación.
        fila_b = ttk.Frame(self)
        fila_b.pack(fill="x", pady=(8, 0))
        self.boton_inicio = ttk.Button(fila_b, text="← Inicio",
                                       style="Secondary.TButton",
                                       command=self._volver_inicio)
        self.boton_inicio.pack(side="left")
        self.boton_sig = ttk.Button(fila_b, text="Siguiente →",
                                    style="Primary.TButton",
                                    command=self._siguiente)
        self.boton_sig.pack(side="right")
        self.boton_atras = ttk.Button(fila_b, text="Atrás", style="Secondary.TButton",
                                      command=self._atras)
        self.boton_atras.pack(side="right", padx=(0, 6))

    def _mostrar_actual(self):
        # El paso ya recibió entrar() (en __init__, avanzar o retroceder); aquí
        # sólo se renderiza, para no dispararlo dos veces por transición.
        p = self.maquina.paso_actual()
        p.tkraise()
        self.stepper.actualizar(self.maquina.indice)
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
            self.log.insert("end", "Ya hay una tarea en curso; espera a que termine.\n")
            self.log.see("end")
            return False
        self._tarea_activa = True
        self._bloquear(True)

        def log(msg):
            def _ins():
                if not self.winfo_exists():
                    return
                self.log.insert("end", msg + "\n")
                self.log.see("end")
            self.after(0, _ins)

        def progreso(i, n):
            self.after(0, self._set_progreso, i, n)

        def worker():
            try:
                res = funcion(log, progreso)
                self.after(0, lambda: self._fin_tarea(res, al_terminar, None))
            except Exception:
                # Capturar el traceback aquí, dentro del except: si se difiriera
                # a `after`, format_exc() correría sin excepción activa y
                # devolvería "NoneType: None", ocultando el error real.
                error = traceback.format_exc()
                self.after(0, lambda: self._fin_tarea(None, al_terminar, error))

        threading.Thread(target=worker, daemon=True).start()

    def _set_progreso(self, i, n):
        if not self.winfo_exists():
            return
        self.progreso.config(mode="determinate", maximum=max(n, 1), value=i + 1)
        self.estado.config(text=f"Procesando… {i + 1}/{n}")
        estilo.configurar_estado(self.estado, "procesando")

    def _bloquear(self, activo):
        estado = "disabled" if activo else "normal"
        self.boton_sig.config(state=estado)
        self.boton_inicio.config(state=estado)
        if activo:
            self.boton_atras.config(state="disabled")
            self.progreso.config(mode="indeterminate")
            self.progreso.start(12)
            self.estado.config(text="Procesando…")
            estilo.configurar_estado(self.estado, "procesando")
        else:
            # Al desbloquear, «Atrás» respeta la posición real (off en el primer paso).
            self.boton_atras.config(
                state="disabled" if self.maquina.es_primero() else "normal")
            self.progreso.stop()
            self.progreso.config(mode="determinate", value=0)

    def _fin_tarea(self, resultado, al_terminar, error):
        if not self.winfo_exists():
            return
        self._tarea_activa = False
        self._bloquear(False)
        if error:
            self.log.insert("end", error + "\n")
            self.estado.config(text="Error. Revisa el detalle.")
            estilo.configurar_estado(self.estado, "error")
        else:
            self.estado.config(text="Listo.")
            estilo.configurar_estado(self.estado, "listo")
        if al_terminar:
            al_terminar(resultado)
