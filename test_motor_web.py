"""Tests ligeros del puente web (sin pywebview en runtime)."""

import numpy as np

import motor_web


def test_revision_con_referencia_sin_ref(tmp_path):
    import xarray as xr
    nc = tmp_path / "s.nc"
    t = np.array(["2020-01-01", "2021-01-01"], dtype="datetime64[ns]")
    ds = xr.Dataset(
        {"Hs": ("time", [1.0, 2.0]), "Tp": ("time", [10.0, 11.0]), "Dir": ("time", [270.0, 280.0])},
        coords={"time": t},
    )
    ds.to_netcdf(nc)
    ds.close()
    res = motor_web.revision_datos(str(nc))
    assert res["comparacion"] is None


def test_guardar_preferencias_roundtrip(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "_RUTA", tmp_path / "config.json")
    motor_web.guardar_preferencias({"era5_lat": "-36.0", "utm_x": "620000"})
    prefs = motor_web.obtener_preferencias()
    assert prefs["era5_lat"] == "-36.0"
    assert prefs["utm_x"] == "620000"


def test_derivar_borde_era5_desde_cache(tmp_path, monkeypatch):
    import xarray as xr
    import io_era5
    import rutas

    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)
    t = np.array(["2020-01-01", "2021-01-01", "2022-01-01"], dtype="datetime64[ns]")
    ds = xr.Dataset(
        {"Hs": ("time", [1.5, 2.5, 3.0]), "Tp": ("time", [10.0, 11.0, 12.0]),
         "Dir": ("time", [270.0, 280.0, 290.0])},
        coords={"time": t},
        attrs={"dir_convencion": "procedencia"},
    )
    _, nc = io_era5.ruta_cache_serie(-37.0, -73.5, "2020-01-01", "2022-12-31")
    nc.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(nc)
    ds.close()

    st = motor_web.estado_cache_era5_borde(-37.0, -73.5, "2020-01-01", "2022-12-31")
    assert st["en_cache"] is True

    borde = motor_web.derivar_borde_era5(
        -37.0, -73.5, "2020-01-01", "2022-12-31", "reinante", 100)
    assert borde["hs"] > 0
    assert borde["per"] > 0
    assert "ruta_serie" in borde
    import config
    monkeypatch.setattr(config, "_RUTA", tmp_path / "config.json")
    ctx = {"modo": "era5", "era5": {"lat": "-37"}}
    motor_web.guardar_sesion_wizard("analizar", 1, ctx)
    ses = motor_web.cargar_sesion_wizard()
    assert ses["wizard"] == "analizar"
    assert ses["step"] == 1
    motor_web.limpiar_sesion_wizard()
    assert motor_web.cargar_sesion_wizard() is None


def test_error_tarea_runtimeerror_y_keyerror():
    from api_web import Api
    api = Api()
    assert api._error_tarea(RuntimeError("no hay swan")) == "no hay swan"
    assert api._error_tarea(KeyError("x")) == "KeyError"
