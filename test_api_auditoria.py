"""Regresiones del puente de escritorio y de sus límites de archivos."""

import json
import queue

import numpy as np
import pytest
import xarray as xr

import config
import motor_web
import rutas
import seguridad
from api_web import Api


@pytest.fixture(autouse=True)
def preferencias_aisladas(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_RUTA", tmp_path / "config.json")
    monkeypatch.setattr(seguridad, "_RUTAS_ELEGIDAS", {})


@pytest.mark.parametrize("valor", ['[]', 'null', '1', '"texto"'])
def test_api_rechaza_json_no_objeto(valor):
    api = Api()
    assert api.guardar_preferencias(valor)["ok"] is False
    assert api.generar_producto_ver(valor)["ok"] is False


def test_seleccion_nativa_autoriza_solo_archivo_elegido(tmp_path, monkeypatch):
    monkeypatch.setattr(seguridad, "_bases_usuario", lambda: [])
    elegido = tmp_path / "serie.csv"
    vecino = tmp_path / "privado.csv"
    elegido.touch()
    vecino.touch()
    with pytest.raises(ValueError):
        seguridad.confina_usuario(elegido)
    api = Api()

    class Ventana:
        def create_file_dialog(self, *args, **kwargs):
            return (str(elegido),)

    api.set_window(Ventana())
    assert api.elegir_archivo() == str(elegido)
    assert seguridad.confina_usuario(elegido) == elegido.resolve()
    with pytest.raises(ValueError):
        seguridad.confina_usuario(vecino)


def test_seleccion_carpeta_admite_hijos_pero_no_escapes(tmp_path, monkeypatch):
    monkeypatch.setattr(seguridad, "_bases_usuario", lambda: [])
    carpeta = tmp_path / "caso"
    carpeta.mkdir()
    seguridad.registrar_ruta_elegida(carpeta)
    assert seguridad.confina_usuario(carpeta / "nuevo.bot") == carpeta / "nuevo.bot"
    with pytest.raises(ValueError):
        seguridad.confina_usuario(carpeta / ".." / "otro.bot")


@pytest.mark.parametrize("sesion", [[], {"wizard": "otro", "step": 0, "ctx": {}},
                                      {"wizard": "ver", "step": 99, "ctx": {}},
                                      {"wizard": "ver", "step": 0, "ctx": []}])
def test_sesion_corrupta_no_rompe_inicio(sesion):
    config.guardar("wizard_sesion", sesion)
    assert motor_web.cargar_sesion_wizard() is None


def test_preferencias_y_recientes_corruptos_no_rompen_inicio():
    config.guardar("preferencias_ui", ["dato incorrecto"])
    config.guardar("productos_recientes", [None, 1, {"ruta": None}])
    assert motor_web.obtener_preferencias() == {}
    assert motor_web.listar_recientes() == []
    motor_web.guardar_preferencias({"utm_x": "1"})
    assert motor_web.obtener_preferencias()["utm_x"] == "1"


def test_borrado_cache_exige_hijo_directo_y_prefijo(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)
    for relativo in ("trabajo_ERA5_privado", "caso/ERA5_datos"):
        carpeta = tmp_path / relativo
        carpeta.mkdir(parents=True)
        with pytest.raises(ValueError):
            motor_web.eliminar_cache_era5(carpeta)
        assert carpeta.is_dir()
    cache = tmp_path / "ERA5_prueba"
    cache.mkdir()
    assert motor_web.eliminar_cache_era5(cache)["ok"]
    assert not cache.exists()


def test_cache_no_se_borra_mientras_hay_tarea(tmp_path):
    api = Api()
    api._busy = True
    assert api.eliminar_cache_era5(str(tmp_path))["ok"] is False
    assert tmp_path.is_dir()


def test_tarea_libera_ocupado_antes_de_anunciar_fin():
    api = Api()
    recibido = queue.Queue()
    api._emit = lambda evento, datos: recibido.put((evento, datos, api._busy))
    assert api._run_task("rapida", lambda: {"valor": 42})["ok"]
    assert recibido.get(timeout=3)[0] == "task_start"
    evento, datos, ocupado = recibido.get(timeout=3)
    assert evento == "task_done"
    assert datos["result"]["valor"] == 42
    assert ocupado is False


def test_comparacion_usa_solo_pares_finitos(tmp_path):
    tiempo = np.array(["2020-01-01", "2020-01-02", "2020-01-03"], dtype="datetime64[ns]")
    a, b = tmp_path / "a.nc", tmp_path / "b.nc"
    xr.Dataset({"Hs": ("time", [1., np.nan, 3.])}, coords={"time": tiempo}).to_netcdf(a)
    xr.Dataset({"Hs": ("time", [2., 50., 4.])}, coords={"time": tiempo}).to_netcdf(b)
    res = motor_web.comparar_series(a, b)
    assert res["n"] == 2
    assert res["bias"] == -1
    assert res["hs_a_media"] == 2
    assert res["hs_b_media"] == 3
    json.dumps(res, allow_nan=False)
