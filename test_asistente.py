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


def test_entrar_notifica_al_paso_actual():
    p0 = PasoFake("a")
    m = asistente.MaquinaWizard([p0, PasoFake("b")])
    m.entrar()
    assert p0.entradas == 1


def test_retroceder():
    p0, p1 = PasoFake("a"), PasoFake("b")
    m = asistente.MaquinaWizard([p0, p1])
    m.entrar()                             # el caller real muestra el primer paso
    m.avanzar()
    assert m.retroceder() is True
    assert m.indice == 0
    assert p0.entradas == 2                # entró al mostrarlo + re-entró al retroceder
    assert m.retroceder() is False         # ya en el primero


def test_lista_vacia_es_error():
    import pytest
    with pytest.raises(ValueError):
        asistente.MaquinaWizard([])


def test_camino_ver_tiene_tres_pasos():
    import pasos_ver
    import asistente
    assert len(pasos_ver.PASOS_VER) == 3
    assert all(issubclass(c, asistente.Paso) for c in pasos_ver.PASOS_VER)


def test_camino_analizar_tiene_tres_pasos():
    import pasos_analizar
    import asistente
    assert len(pasos_analizar.PASOS_ANALIZAR) == 3
    assert all(issubclass(c, asistente.Paso) for c in pasos_analizar.PASOS_ANALIZAR)


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


def test_paso_nido_activo_agrega_dominio_sin_espectro():
    import pasos_modelar
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        paso = pasos_modelar.PasoNido(root)
        ctx = {"dominios": [{"malla": {"xpc": 0}}]}
        paso.entrar(ctx)
        paso.activo.set(True)
        paso.malla = {"xpc": 1, "ypc": 2, "xlenc": 9000, "ylenc": 10000,
                      "mxc": 45, "myc": 50, "zona_utm": "19S"}
        paso.bot.set("/ruta/ficticia/bati_nido.bot")
        paso.con_espectro.set(False)
        paso.recoger(ctx)
        assert len(ctx["dominios"]) == 2
        assert ctx["dominios"][1]["malla"] is paso.malla
        assert ctx["dominios"][1]["bot"] == "/ruta/ficticia/bati_nido.bot"
        assert "punto_espectral" not in ctx["dominios"][1]
        # Segunda pasada: upsert, no duplicar
        paso.recoger(ctx)
        assert len(ctx["dominios"]) == 2
    finally:
        root.destroy()


def test_paso_nido_desactivado_elimina_dominio_previo():
    import pasos_modelar
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        paso = pasos_modelar.PasoNido(root)
        ctx = {"dominios": [{"malla": {}}, {"malla": {"xpc": 9}, "bot": "x.bot"}]}
        paso.entrar(ctx)
        paso.activo.set(False)
        paso.recoger(ctx)
        assert len(ctx["dominios"]) == 1
    finally:
        root.destroy()


def test_tarea_registra_el_error_real_no_nonetype():
    """Una tarea que falla debe registrar el traceback real, no 'NoneType: None'."""
    import asistente
    import tkinter as tk

    class PasoMinimo(asistente.Paso):
        titulo = "x"

    class HiloSincrono:
        """Corre el target en el acto: test determinista, sin carrera de hilos."""
        def __init__(self, target=None, **kw):
            self._target = target

        def start(self):
            self._target()

    root = tk.Tk(); root.withdraw()
    hilo_real = asistente.threading.Thread
    asistente.threading.Thread = HiloSincrono
    try:
        w = asistente.Wizard(root, "T", [PasoMinimo], lambda: None)

        # Capturar los callbacks de after() y dispararlos luego en el hilo
        # principal, igual que haría after(0). Así se reproduce el momento exacto
        # del bug: traceback.format_exc() evaluado tras salir del except.
        diferidos = []

        def after_falso(ms, func=None, *args):
            if func is not None:
                diferidos.append(lambda: func(*args))
            return "id"

        w.after = after_falso

        def trabajo(log, progreso):
            raise RuntimeError("explosion de prueba")

        w.tarea(trabajo)                       # corre el worker en el acto
        for cb in diferidos:                   # disparar el cierre en el hilo principal
            cb()
        contenido = w.log.get("1.0", "end")
        assert "explosion de prueba" in contenido
        assert "NoneType: None" not in contenido
    finally:
        asistente.threading.Thread = hilo_real
        root.destroy()


def test_dominio_actual_crea_lista_para_el_nesting():
    import pasos_modelar
    ctx = {}
    dom = pasos_modelar._dominio_actual(ctx)
    assert ctx["dominios"] == [dom]      # estructura de lista lista para el nido
    dom["malla"] = {"x": 1}
    assert pasos_modelar._dominio_actual(ctx) is dom   # no duplica


def test_paso_revision_bloquea_con_datos_rotos():
    """Si el archivo no carga, PasoRevision no debe dejar avanzar el wizard."""
    import pasos_analizar
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        paso = pasos_analizar.PasoRevision(root)
        paso.entrar({"ruta_datos": "/ruta/que/no/existe.mat"})
        ok, msg = paso.validar()
        assert not ok
        assert msg                       # mensaje explicativo, no vacío
    finally:
        root.destroy()


def test_paso_revision_avanza_con_datos_buenos(tmp_path):
    """Con un Dataset válido (Hs) PasoRevision debe permitir avanzar."""
    import pasos_analizar
    import io_oleaje
    import pandas as pd
    import tkinter as tk

    fechas = pd.date_range("2024-01-01", periods=48, freq="3h")
    df = pd.DataFrame({
        "anio": fechas.year, "mes": fechas.month, "dia": fechas.day,
        "hora": fechas.hour, "Hs": 1.5, "Tp": 9.0, "Dir": 270.0})
    nc = tmp_path / "serie.nc"
    io_oleaje.guardar_netcdf(io_oleaje.construir_dataset(df), nc)

    root = tk.Tk(); root.withdraw()
    try:
        paso = pasos_analizar.PasoRevision(root)
        paso.entrar({"ruta_datos": str(nc)})
        ok, _ = paso.validar()
        assert ok
    finally:
        root.destroy()
