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
