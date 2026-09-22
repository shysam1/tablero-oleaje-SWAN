"""Regresiones de la auditoría de portabilidad y datos de septiembre de 2026."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import xarray as xr

import borde_oleaje
import io_era5
import io_oleaje
import particion_espectral
import productos
import productos_particion
import rutas
import tablero_oleaje


def _serie(hs, tp=None):
    datos = {"Hs": ("time", hs)}
    if tp is not None:
        datos["Tp"] = ("time", tp)
    return xr.Dataset(datos, coords={"time": pd.date_range("2020-01-01", periods=len(hs))})


def test_tablero_con_nan_en_hs_tp_se_exporta(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path / "salidas")
    ds = _serie([1., 2., np.nan], [10., np.nan, 12.])
    entrada = tmp_path / "datos.nc"
    ds.to_netcdf(entrada)
    salida = tablero_oleaje.generar_tablero(entrada)
    assert salida.is_file() and salida.stat().st_size > 1000


def test_histograma_sin_pares_validos_se_omite():
    ds = _serie([1., np.nan], [np.nan, 12.])
    informe = productos.evaluar(ds)
    panel = next(p for p in informe if p["nombre"] == "Histograma conjunto Hs–Tp")
    assert not panel["disponible"]
    assert "pares" in panel["faltan"][0]


def test_gumbel_constante_se_omite_sin_abortarse():
    ds = _serie(np.ones(1100))
    informe = productos.evaluar(ds)
    panel = next(p for p in informe if p["nombre"] == "Períodos de retorno (Gumbel)")
    assert not panel["disponible"]
    with pytest.raises(ValueError, match="distintos"):
        borde_oleaje.condicion_borde(ds, "retorno")


def test_gumbel_ignora_anio_sin_datos():
    ds = _serie(np.linspace(1, 4, 1500))
    ds["Hs"] = ds["Hs"].where(ds.time.dt.year != 2021)
    maximos, loc, escala = productos.ajustar_gumbel(ds)
    assert np.isfinite(maximos).all() and np.isfinite(loc) and escala > 0
    assert productos._n_anios(ds) == len(maximos)


def test_resumen_direccional_circular():
    ds = _serie([1., 2.]).assign(Dir=("time", [359., 1.]))
    fila = next(f for f in productos._calc_resumen(ds)["filas"] if f[0] == "Dir")
    assert fila[1] == pytest.approx(0., abs=1e-8)
    assert fila[2] == pytest.approx(1., abs=.01)


@pytest.mark.parametrize("columna,valor", [("anio", 2024.9), ("hora", .9), ("hora", 24)])
def test_fechas_no_se_truncan_o_desbordan(columna, valor):
    datos = {"anio": [2024.], "mes": [1.], "dia": [1.], "hora": [0.], "Hs": [2.]}
    datos[columna] = [valor]
    with pytest.raises(ValueError, match="enteros"):
        io_oleaje.construir_dataset(pd.DataFrame(datos))


@pytest.mark.parametrize("tipo", ["vacio", "sin_fecha", "malla"])
def test_netcdf_estructura_invalida_da_error_claro(tmp_path, tipo):
    if tipo == "vacio":
        ds = _serie([])
    elif tipo == "sin_fecha":
        ds = xr.Dataset({"Hs": ("time", [1.])}, coords={"time": [1]})
    else:
        ds = xr.Dataset({"Hs": (("time", "punto"), [[1., 2.]])},
                        coords={"time": pd.date_range("2024-01-01", periods=1)})
    entrada = tmp_path / "entrada.nc"
    ds.to_netcdf(entrada)
    with pytest.raises(ValueError):
        io_oleaje.cargar(entrada)


def test_netcdf_se_ordena_y_no_retiene_handle(tmp_path):
    ds = _serie([1., 2.]).isel(time=[1, 0])
    entrada = tmp_path / "entrada.nc"
    ds.to_netcdf(entrada)
    leido = io_oleaje.cargar(entrada)
    entrada.unlink()
    np.testing.assert_array_equal(leido.Hs, [1., 2.])


def test_cache_sin_viento_no_satisface_peticion_con_viento(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)
    carpeta, destino = io_era5.ruta_cache_serie(-37, -73, "2020-01-01", "2020-01-02")
    ds = _serie([1., 2.]).assign(Tp=("time", [10., 11.]), Dir=("time", [270., 270.]))
    ds.attrs["dir_convencion"] = "procedencia"
    ds.to_netcdf(destino)
    assert io_era5._serie_cache_limpia(destino)
    assert not io_era5._serie_cache_limpia(destino, incluir_viento=True)
    llamadas = []

    def descargar(lat, lon, tramos, incluir_viento, carpeta, log_fn):
        llamadas.append(incluir_viento)
        return [ds.assign(u10=("time", [2., 3.]), v10=("time", [1., 1.]))]

    monkeypatch.setattr(io_era5, "_descargar_tramos_serie", descargar)
    resultado = io_era5.descargar_serie(-37, -73, "2020-01-01", "2020-01-02", True)
    assert llamadas == [True]
    assert {"u10", "v10"} <= set(resultado.data_vars)


def test_peticion_espectro_usa_mars():
    p = io_era5._peticion_espectro(-37, -73, "2020-01-01", "2020-01-02")
    assert io_era5._DATASET_ESPECTRO == "reanalysis-era5-complete"
    assert p["param"] == "140251" and p["stream"] == "wave"
    assert p["frequency"] == "1/to/30" and p["direction"] == "1/to/24"
    assert p["date"] == "2020-01-01/to/2020-01-02"


def test_parser_espectro_2dfd_transpuesto_y_direccion_fisica(tmp_path):
    densidad = np.ones((4, 3, 1)) * .001
    densidad[0, :, 0] = .5
    ds = xr.Dataset({"2dfd": (("direction", "frequency", "time"), np.log10(densidad))},
                    coords={"direction": [7.5, 97.5, 187.5, 277.5],
                            "frequency": [.05, .1, .2],
                            "time": pd.date_range("2020-01-01", periods=1)})
    ruta = tmp_path / "crudo.nc"
    ds.to_netcdf(ruta)
    esp = io_era5._parsear_espectro_nc(ruta)
    assert esp.Efth.dims == ("time", "freq", "dir")
    assert float(esp.dir.isel(dir=int(esp.Efth.sum(["time", "freq"]).argmax()))) == 187.5
    assert esp.dir.attrs["convencion"] == "nautica"


def test_tp_es_maximo_de_densidad_no_energia_de_banda():
    freqs, dirs = np.array([.05, .1, .2]), np.array([0.])
    efth = np.array([[1.], [2.], [1.8]])
    dfreq, ddir = particion_espectral._pesos(freqs, dirs)
    familia = particion_espectral._parametros(efth, np.ones_like(efth, bool),
                                              freqs, dirs, dfreq, ddir, None)
    assert familia["Tp"] == 10.


def test_borde_no_devuelve_altura_infinita():
    ds = _serie([2., np.inf, 3.])
    assert borde_oleaje.condicion_borde(ds, "maximo")["hs"] == 3.


def test_escritura_atomica_limpia_temporal_si_falla(tmp_path, monkeypatch):
    destino = tmp_path / "cache.nc"
    destino.write_bytes(b"original")

    def fallar(self, ruta):
        raise OSError("disco sin espacio")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fallar)
    with pytest.raises(OSError):
        io_era5._escribir_nc_atomico(_serie([1.]), destino)
    assert destino.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.part"))


def test_io_netcdf_concurrente_se_serializa(tmp_path, monkeypatch):
    activos = 0
    pico = 0
    escritura = xr.Dataset.to_netcdf

    def instrumentado(self, ruta):
        nonlocal activos, pico
        activos += 1
        pico = max(pico, activos)
        time.sleep(.02)
        try:
            return escritura(self, ruta)
        finally:
            activos -= 1

    monkeypatch.setattr(xr.Dataset, "to_netcdf", instrumentado)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(io_era5._escribir_nc_atomico, _serie([1.]),
                               tmp_path / f"cache_{i}.nc") for i in range(4)]
        for futuro in futuros:
            futuro.result()
    assert pico == 1


@pytest.mark.parametrize("convencion,angulo,sentido", [("nautica", np.pi / 2, -1),
                                                      ("cartesiana", 0., 1)])
def test_polar_respeta_convencion(convencion, angulo, sentido):
    ds = xr.Dataset({"Efth": (("freq", "dir"), np.ones((3, 4)))},
                    coords={"freq": [.05, .1, .2], "dir": [0., 90., 180., 270.]})
    ds.dir.attrs["convencion"] = convencion
    fig, ax = plt.subplots(subplot_kw={"projection": "polar"})
    try:
        productos_particion.dibujar_polar(ax, ds)
        assert ax.get_theta_offset() == pytest.approx(angulo)
        assert ax.get_theta_direction() == sentido
    finally:
        plt.close(fig)
