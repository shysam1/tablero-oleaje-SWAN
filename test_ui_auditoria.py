"""Regresiones de interfaz en Chromium; requiere Playwright y su navegador."""

from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def pagina():
    with playwright_api.sync_playwright() as p:
        try:
            navegador = p.chromium.launch(headless=True)
        except playwright_api.Error as exc:
            pytest.skip(f"Chromium de pruebas no disponible: {exc}")
        pagina = navegador.new_page(viewport={"width": 960, "height": 700})
        pagina.goto((Path(__file__).parent / "ui" / "index.html").resolve().as_uri())
        yield pagina
        navegador.close()


def test_escape_cancela_confirmacion_incluso_despues_de_aceptar(pagina):
    pagina.evaluate("() => { window.respuesta = null; Tablero.askConfirm('Prueba').then(r => window.respuesta = r); }")
    pagina.get_by_role("button", name="Continuar", exact=True).click()
    pagina.wait_for_function("window.respuesta === true")
    pagina.evaluate("() => { window.respuesta = null; Tablero.askConfirm('Prueba').then(r => window.respuesta = r); }")
    pagina.keyboard.press("Escape")
    pagina.wait_for_function("window.respuesta === false")


def test_escape_cancela_borde_y_no_cambia_paso(pagina):
    pagina.evaluate("() => { Tablero.startWizard('analizar', {}, 1); window.respuesta = 'pendiente'; Tablero.askBordeCondicion().then(r => window.respuesta = r); }")
    pagina.keyboard.press("Escape")
    pagina.wait_for_function("window.respuesta === null")
    assert pagina.evaluate("Tablero.state.step") == 1


def test_resultado_rapido_se_conserva_antes_de_esperar(pagina):
    resultado = pagina.evaluate("""async () => {
        dispatchPyEvent({event:'task_start', data:{id:'rapida'}});
        dispatchPyEvent({event:'task_done', data:{id:'rapida',ok:true,result:42}});
        return await Tablero.waitTask('rapida',20);
    }""")
    assert resultado["result"] == 42


def test_tarea_lenta_mantiene_bloqueo_y_recibe_resultado(pagina):
    pagina.evaluate("""() => {
        Tablero.startWizard('analizar', {}, 1);
        dispatchPyEvent({event:'task_start',data:{id:'lenta'}});
        window.resultadoLento = null;
        Tablero.waitTask('lenta',20).then(r => window.resultadoLento = r);
    }""")
    pagina.wait_for_function("document.querySelector('#inline-error').textContent.includes('sigue en curso')")
    assert pagina.evaluate("Tablero.state.busy") is True
    assert pagina.get_by_role("button", name="Atrás", exact=True).is_disabled()
    pagina.keyboard.press("Escape")
    assert pagina.evaluate("Tablero.state.step") == 1
    pagina.evaluate("dispatchPyEvent({event:'task_done',data:{id:'lenta',ok:true,result:7}})")
    pagina.wait_for_function("window.resultadoLento?.result === 7")
    assert pagina.evaluate("Tablero.state.busy") is False


def test_busy_conserva_controles_deshabilitados(pagina):
    pagina.evaluate("Tablero.startWizard('analizar'); Tablero.setBusy(true); Tablero.setBusy(true); Tablero.setBusy(false)")
    assert pagina.get_by_role("button", name="Atrás", exact=True).is_disabled()
    assert pagina.get_by_role("button", name="Siguiente →", exact=True).is_enabled()
