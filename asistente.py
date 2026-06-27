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
