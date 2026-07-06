"""
Tests de regresión de la herramienta Tablero de Oleaje.

Red de seguridad para iterar sin romper lo que ya funciona: carga las corridas
conocidas y comprueba los valores clave verificados a mano (Hs de borde, número
de pasos, orientación, mapeo de variables). Son rápidos: no corren SWAN ni
generan figuras.

Uso:  pytest test_regresion.py -v
Si los datos de prueba no están en disco, los tests que los necesitan se saltan.

Variables de entorno opcionales (solo en tu máquina, no van al repo):
  TABLERO_DATOS_SWAN   → carpeta con corridas SWAN de referencia (p. ej. SWAN_Coronel)
  TABLERO_DATOS_OLEAJE → archivo .mat/.csv/.nc de oleaje en un punto
"""

import os
from pathlib import Path

import numpy as np
import pytest

import io_swan
import io_swan_nonst
import io_oleaje
import io_era5
import geo_malla
import seguridad
import swan_builder
import swan_runner


def _ruta_datos(var_env: str) -> Path:
    valor = os.environ.get(var_env, "").strip()
    if not valor:
        return Path(f"_sin_configurar_{var_env}_")
    return Path(valor)


BASE_SWAN = _ruta_datos("TABLERO_DATOS_SWAN")
RUTA_OLEAJE = _ruta_datos("TABLERO_DATOS_OLEAJE")


def _saltar_si_falta(ruta):
    if not Path(ruta).exists():
        pytest.skip(f"datos de prueba no disponibles: {ruta}")


# --------------------------- SWAN estacionario ---------------------------
@pytest.mark.parametrize("caso, hs_large, hs_n1, hs_borde", [
    ("extremo_Tr100", 8.17, 7.565, 8.16),
    ("extremo_Tr10", 7.449, 6.94, 7.44),
    ("reinante", 2.426, 1.259, 2.42),
])
def test_swan_estacionario(caso, hs_large, hs_n1, hs_borde):
    carpeta = BASE_SWAN / caso
    _saltar_si_falta(carpeta)
    corr = io_swan.cargar_corrida(carpeta)

    assert set(corr["dominios"]) == {"large", "n1"}
    assert corr["meta"]["Hs_borde"] == pytest.approx(hs_borde, abs=0.01)

    ds = corr["dominios"]["large"]
    assert dict(ds.sizes) == {"y": 60, "x": 49}
    assert float(ds["Hs"].max()) == pytest.approx(hs_large, abs=0.05)

    n1 = corr["dominios"]["n1"]
    assert dict(n1.sizes) == {"y": 51, "x": 46}
    assert float(n1["Hs"].max()) == pytest.approx(hs_n1, abs=0.05)
    assert "Setup" in n1.data_vars
    assert corr["espectro"] is not None


def test_swan_offset_utm_nido_derivado():
    """
    El UTM del nido se deriva del CGRID (origen local 36480, 32229 + offset del
    large), no del valor hardcodeado del módulo original, que tenía mal el Norte
    (usaba 5893222 en vez de 5908680: el nido quedaba ~15 km desplazado en Y).
    """
    carpeta = BASE_SWAN / "extremo_Tr100"
    _saltar_si_falta(carpeta)
    n1 = io_swan.cargar_corrida(carpeta)["dominios"]["n1"]
    assert float(n1["x"].min()) == pytest.approx(620494.0 + 36480.0, abs=1.0)
    assert float(n1["y"].min()) == pytest.approx(5876451.0 + 32229.0, abs=1.0)


def test_inferir_utm_desde_meta(tmp_path):
    io_swan.guardar_meta_caso(tmp_path, {"xpc": 610494.0, "ypc": 5866451.0},
                              zona_utm="19S")
    r = io_swan.inferir_utm_desde_carpeta(tmp_path)
    assert r["origen"] == "meta"
    assert r["utm_x"] == pytest.approx(610494.0)
    assert r["zona_utm"] == "19S"


def test_inferir_utm_cgrid_absoluto(tmp_path):
    (tmp_path / "caso.swn").write_text(
        "CGRID 250000 6340000 0 8000 8000 80 80 CIRCLE 36 0.04 1\n")
    r = io_swan.inferir_utm_desde_carpeta(tmp_path)
    assert r["origen"] == "cgrid"
    assert r["utm_x"] == pytest.approx(250000.0)
    assert r["utm_y"] == pytest.approx(6340000.0)


def test_inferir_utm_local_cero_usa_default(tmp_path):
    (tmp_path / "caso.swn").write_text(
        "CGRID 0 0 0 8000 8000 80 80 CIRCLE 36 0.04 1\n")
    r = io_swan.inferir_utm_desde_carpeta(tmp_path)
    assert r["origen"] == "default"
    assert r["utm_x"] == io_swan.UTM_LARGE_DEFAULT[0]


# --------------------------- SWAN no estacionario ---------------------------
def test_swan_nonst_estructura_y_orientacion():
    carpeta = BASE_SWAN / "no_estacionario"
    _saltar_si_falta(carpeta)
    corr = io_swan_nonst.cargar_corrida_nonst(carpeta)
    large = corr["dominios"]["large"]

    assert corr["meta"]["nt"] == 168
    assert dict(large.sizes) == {"time": 168, "y": 60, "x": 49}

    t = large["time"].values
    assert bool(np.all(np.diff(t) > np.timedelta64(0)))          # monótona
    assert float(large["Hs"].max()) == pytest.approx(6.997, abs=0.05)

    # El peak de Hs cae en el paso 118 (= frames_clave_3d.m de MATLAB).
    i_peak = int(large["Hs"].max(dim=("y", "x")).argmax("time"))
    assert i_peak == 118


def test_nido_nonst_se_omite():
    """
    El nido no estacionario de Coronel es inestable (oleaje sólo en el paso 0);
    _nido_util debe marcarlo como no-útil para que el multipanel omita su panel.
    """
    import video_swan
    carpeta = BASE_SWAN / "no_estacionario"
    _saltar_si_falta(carpeta)
    n1 = io_swan_nonst.cargar_corrida_nonst(carpeta)["dominios"]["n1"]
    assert video_swan._nido_util(n1) is False


def test_espectro_temporal():
    carpeta = BASE_SWAN / "no_estacionario"
    _saltar_si_falta(carpeta)
    esp = io_swan_nonst.leer_espectro_temporal(carpeta / "Espectro_Punto.mat")
    assert dict(esp.sizes) == {"time": 168, "freq": 35, "dir": 180}
    with np.errstate(invalid="ignore"):
        con_energia = int((esp["Efth"].sum(("freq", "dir")).values > 0).sum())
    assert con_energia == 1                                      # sólo el paso 0


# --------------------------- Serie temporal (oleaje) ---------------------------
def test_oleaje_talcahuano():
    _saltar_si_falta(RUTA_OLEAJE)
    ds = io_oleaje.cargar(RUTA_OLEAJE)
    assert {"Hs", "Tp", "Dir"} <= set(ds.data_vars)
    assert "time" in ds.coords
    assert ds.sizes["time"] > 100_000                           # 36 años, 3-horario
    t = ds["time"].values
    assert bool(np.all(np.diff(t) > np.timedelta64(0)))
    assert 0 < float(ds["Hs"].max()) < 15                       # rango físico


# --------------------------- Funciones puras ---------------------------
def test_mapeo_variables_swan():
    assert io_swan._QUANT_VAR["HSIGN"] == "Hs"
    assert io_swan._QUANT_VAR["RTP"] == "Tp"
    assert io_swan._QUANT_VAR["DIR"] == "Dir"
    assert io_swan._var_de_nombre("Hs_Large(nc).txt") == "Hs"
    assert io_swan._var_de_nombre("SetUp_N1(c).txt") == "Setup"
    assert io_swan._var_de_nombre("TPAR1.txt") in (None, "Tp")  # se filtra por tamaño


def test_builder_genera_bloques_clave():
    txt = swan_builder.construir_swn(
        nombre="T", malla={"xpc": 0., "ypc": 0., "xlenc": 1000, "ylenc": 1000,
                           "mxc": 10, "myc": 10},
        batimetria={"archivo": "f.bot"},
        bordes=[{"lado": "W", "hs": 2., "per": 10., "dir": 270., "dd": 15.}],
        salidas=("Hs", "Dir"))
    assert "CGRID 0.0 0.0 0.0 1000 1000 10 10 CIRCLE" in txt
    assert "READINP BOTTOM 1.0 'f.bot'" in txt
    assert "BOUN SIDE W CCW CON PAR 2.0 10.0 270.0 15.0" in txt
    assert "BLOCK 'COMPGRID' NOHEADER 'Hs.txt' HS" in txt
    assert "BLOCK 'COMPGRID' NOHEADER 'Dir.txt' DIR" in txt
    assert txt.rstrip().endswith("STOP")


def test_casos_ordenados_padre_primero(tmp_path):
    """El dominio grande (sin BOU NEST) va antes que el anidado (con BOU NEST)."""
    (tmp_path / "grande.swn").write_text("CGRID 0. 0. 0. 1000 1000 10 10 CIRCLE 36 .04 1\n")
    (tmp_path / "nido.swn").write_text(
        "CGRID 300 300 0. 200 200 20 20 CIRCLE 36 .04 1\n"
        "BOU NEST 'nest1' CLOSED\n")
    assert swan_runner.casos_ordenados(tmp_path) == ["grande", "nido"]


def test_correr_swan_no_hereda_exito_si_falla_el_nido(tmp_path, monkeypatch):
    """norm_end es por carpeta: si el grande sale OK y el nido falla, ok_global=False."""
    (tmp_path / "grande.swn").write_text("CGRID 0. 0. 0. 1000 1000 10 10 CIRCLE 36 .04 1\n")
    (tmp_path / "nido.swn").write_text(
        "CGRID 300 300 0. 200 200 20 20 CIRCLE 36 .04 1\nBOU NEST 'g' CLOSED\n")

    # SWAN simulado: el grande deja norm_end; el nido deja un .erf y NO toca norm_end
    # (queda el stale del grande, que es justo la trampa del bug).
    class _Popen:
        def __init__(self, comando, **kw):
            self._caso = comando[-1]
            self._cwd = Path(kw["cwd"])
            self.stdout = iter(())

        def wait(self):
            if self._caso == "grande":
                (self._cwd / "norm_end").write_text("")
            else:
                (self._cwd / f"{self._caso}.erf").write_text("error fatal")

    monkeypatch.setattr(swan_runner.shutil, "which", lambda nombre: r"C:\fake\swanrun.bat")
    monkeypatch.setattr(swan_runner.prioridad, "proteger_swan", lambda **kw: None)
    monkeypatch.setattr(swan_runner.subprocess, "Popen", lambda *a, **k: _Popen(*a, **k))

    ok, _ = swan_runner.correr_swan(tmp_path)
    assert ok is False


def test_correr_swan_ok_si_todos_los_casos_terminan(tmp_path, monkeypatch):
    """Caso feliz: si todos dejan norm_end y ninguno deja .erf, ok_global=True."""
    (tmp_path / "grande.swn").write_text("CGRID 0. 0. 0. 1000 1000 10 10 CIRCLE 36 .04 1\n")
    (tmp_path / "nido.swn").write_text(
        "CGRID 300 300 0. 200 200 20 20 CIRCLE 36 .04 1\nBOU NEST 'g' CLOSED\n")

    class _Popen:
        def __init__(self, comando, **kw):
            self._cwd = Path(kw["cwd"])
            self.stdout = iter(())

        def wait(self):
            (self._cwd / "norm_end").write_text("")

    monkeypatch.setattr(swan_runner.shutil, "which", lambda nombre: r"C:\fake\swanrun.bat")
    monkeypatch.setattr(swan_runner.prioridad, "proteger_swan", lambda **kw: None)
    monkeypatch.setattr(swan_runner.subprocess, "Popen", lambda *a, **k: _Popen(*a, **k))

    ok, _ = swan_runner.correr_swan(tmp_path)
    assert ok is True


def test_paso_correr_distingue_no_corrido_fallo_y_ok():
    """PasoCorrer.validar: bloquea si no corrió, bloquea si corrió y falló, deja si OK."""
    import pasos_modelar
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        paso = pasos_modelar.PasoCorrer(root)
        paso.entrar({})
        ok, msg = paso.validar()                 # aún no corre
        assert not ok and "espera" in msg.lower()

        paso.corrido, paso.ok = True, False       # corrió pero falló
        ok, msg = paso.validar()
        assert not ok and "error" in msg.lower()

        paso.ok = True                            # corrió y salió bien
        ok, _ = paso.validar()
        assert ok
    finally:
        root.destroy()


# --------------------------- Partición espectral ---------------------------
import particion_espectral


def test_pesos_y_m0_reconstruyen_hs():
    """m0 integrado de un espectro debe reproducir Hs = 4*sqrt(m0)."""
    freqs = np.linspace(0.04, 0.40, 30)
    dirs = np.arange(0.0, 360.0, 15.0)
    # Espectro unimodal: una gaussiana en (f, dir) con energía conocida.
    F, D = np.meshgrid(freqs, dirs, indexing="ij")
    efth = np.exp(-((F - 0.10) / 0.02) ** 2) * np.exp(-((D - 200.0) / 20.0) ** 2)

    dfreq, ddir = particion_espectral._pesos(freqs, dirs)
    m0 = particion_espectral._m0(efth, dfreq, ddir)
    hs = 4.0 * np.sqrt(m0)
    assert m0 > 0
    assert 0.0 < hs < 5.0           # rango físico para esa energía


def test_parametros_de_familia_unimodal():
    """Sobre un espectro unimodal, la máscara total reproduce Hs/Tp/Dir del pico."""
    freqs = np.linspace(0.04, 0.40, 30)
    dirs = np.arange(0.0, 360.0, 15.0)
    F, D = np.meshgrid(freqs, dirs, indexing="ij")
    efth = np.exp(-((F - 0.10) / 0.02) ** 2) * np.exp(-((D - 200.0) / 20.0) ** 2)

    dfreq, ddir = particion_espectral._pesos(freqs, dirs)
    mascara = np.ones_like(efth, dtype=bool)
    fam = particion_espectral._parametros(efth, mascara, freqs, dirs,
                                          dfreq, ddir, viento=None)
    assert fam["Tp"] == pytest.approx(1.0 / 0.10, abs=1.0)   # pico en 0.10 Hz
    assert fam["Dir"] == pytest.approx(200.0, abs=8.0)
    assert fam["Hs"] > 0
    assert fam["tipo"] == "swell"                            # Tp largo, sin viento


def _espectro_bimodal():
    """Sea de período corto (~0.25 Hz, 270°) + swell largo (~0.07 Hz, 200°)."""
    freqs = np.linspace(0.04, 0.40, 30)
    dirs = np.arange(0.0, 360.0, 15.0)
    F, D = np.meshgrid(freqs, dirs, indexing="ij")
    sea = np.exp(-((F - 0.25) / 0.03) ** 2) * np.exp(-((D - 270.0) / 20.0) ** 2)
    swell = 0.6 * np.exp(-((F - 0.07) / 0.012) ** 2) * np.exp(-((D - 200.0) / 15.0) ** 2)
    return freqs, dirs, sea + swell


def test_particionar_separa_dos_familias_y_conserva_energia():
    freqs, dirs, efth = _espectro_bimodal()
    fam = particion_espectral.particionar(efth, freqs, dirs, umbral_rel=0.0)
    assert len(fam) == 2

    dfreq, ddir = particion_espectral._pesos(freqs, dirs)
    m0_total = particion_espectral._m0(efth, dfreq, ddir)
    assert sum(f["m0"] for f in fam) == pytest.approx(m0_total, rel=1e-9)

    # Ordenadas por energía descendente.
    assert fam[0]["m0"] >= fam[1]["m0"]
    # La de período más largo es swell; la corta, sea.
    por_tp = sorted(fam, key=lambda f: f["Tp"])
    assert por_tp[0]["tipo"] == "sea"
    assert por_tp[-1]["tipo"] == "swell"


def test_particionar_serie_devuelve_dataset_por_familia():
    import xarray as xr
    freqs, dirs, efth = _espectro_bimodal()
    cubo = np.stack([efth, efth * 0.5])          # 2 pasos de tiempo
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), cubo)},
        coords={"time": np.array(["2024-07-28T00", "2024-07-28T03"],
                                 dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})

    res = particion_espectral.particionar_serie(ds, umbral_rel=0.0)
    assert set(["Hs", "Tp", "Dir"]) <= set(res.data_vars)
    assert res.sizes["time"] == 2
    assert res.sizes["familia"] == 2
    # La Hs total del paso 0 (raíz de la suma de m0) supera la de cualquier familia.
    hs_fam0 = res["Hs"].isel(time=0).values
    assert np.nanmax(hs_fam0) > 0


# --------------------------- Descarga ERA5 ---------------------------
import urllib.request

import io_era5
import rutas


def test_cliente_sin_credenciales_explica(monkeypatch, tmp_path):
    """Sin ~/.cdsapirc, _cliente lanza un error claro de configuración."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))   # HOME en Windows
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="Credenciales ERA5"):
        io_era5._cliente()


def test_guardar_y_estado_credenciales_cds(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    io_era5.guardar_credenciales_cds(
        "https://cds.climate.copernicus.eu/api", "12345:abcdef-SECRET")
    ruta = tmp_path / ".cdsapirc"
    assert ruta.is_file()
    texto = ruta.read_text(encoding="utf-8")
    assert "12345:abcdef-SECRET" in texto
    est = io_era5.estado_credenciales_cds()
    assert est["configurado"] is True
    assert est["uid"] == "12345"
    assert est["key_enmascarada"].endswith("CRET")
    assert "abcdef-SECRET" not in est["key_enmascarada"]


def test_guardar_credenciales_conserva_clave(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    io_era5.guardar_credenciales_cds(
        "https://cds.climate.copernicus.eu/api", "99:clave-original")
    io_era5.guardar_credenciales_cds(
        "https://cds.climate.copernicus.eu/api", "")
    cred = io_era5.leer_credenciales_cds()
    assert cred["key"] == "99:clave-original"


def test_probar_credenciales_rechaza_formato(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ValueError, match="UID:API-KEY"):
        io_era5.probar_credenciales_cds(
            "https://cds.climate.copernicus.eu/api", "clave-mal-formada")


def test_probar_credenciales_acepta_respuesta_cds(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=25: _Resp())

    res = io_era5.probar_credenciales_cds(
        "https://cds.climate.copernicus.eu/api", "12345:abcdef")
    assert "aceptó" in res["mensaje"].lower()


def test_peticion_serie_arma_area_y_variables():
    pet = io_era5._peticion_serie(lat=-37.0, lon=-73.5,
                                  inicio="2024-07-28", fin="2024-07-28",
                                  incluir_viento=True)
    # Área de un punto: [N, W, S, E] alrededor de (lat, lon).
    assert pet["area"][0] >= -37.0 >= pet["area"][2]
    assert pet["area"][1] <= -73.5 <= pet["area"][3]
    assert "significant_height_of_combined_wind_waves_and_swell" in pet["variable"]
    assert "peak_wave_period" in pet["variable"]
    assert "mean_wave_direction" in pet["variable"]
    assert "10m_u_component_of_wind" in pet["variable"]
    assert pet["format"] == "netcdf"


def _nc_serie_sintetico(ruta):
    """Crea un .nc con la estructura de la serie ERA5 (swh/pp1d/mwd, punto+tiempo)."""
    import xarray as xr
    t = np.array(["2024-07-28T00", "2024-07-28T03"], dtype="datetime64[ns]")
    lat = np.array([-36.75, -37.25]); lon = np.array([-73.75, -73.25])
    forma = (len(t), len(lat), len(lon))
    ds = xr.Dataset(
        {"swh": (("time", "latitude", "longitude"), np.full(forma, 2.5)),
         "pp1d": (("time", "latitude", "longitude"), np.full(forma, 12.0)),
         "mwd": (("time", "latitude", "longitude"), np.full(forma, 225.0))},
        coords={"time": t, "latitude": lat, "longitude": lon})
    ds.to_netcdf(ruta)


def test_parsear_serie_selecciona_punto_y_renombra(tmp_path):
    ruta = tmp_path / "serie.nc"
    _nc_serie_sintetico(ruta)
    ds = io_era5._parsear_serie_nc(ruta, lat=-37.0, lon=-73.5)
    assert {"Hs", "Tp", "Dir"} <= set(ds.data_vars)
    assert "time" in ds.coords
    assert ds.sizes["time"] == 2
    assert float(ds["Hs"].isel(time=0)) == pytest.approx(2.5)
    assert "latitude" not in ds.dims          # punto ya seleccionado


def test_parsear_serie_conserva_mwd_como_procedencia(tmp_path):
    """
    El mwd escalar de ERA5 ya es procedencia («coming from», doc. ECMWF): el
    parser NO debe sumarle 180°. Regresión del bug que invertía la rosa y el
    borde SWAN derivado de ERA5 (auditoría 2026-07, hallazgo A2-1).
    """
    ruta = tmp_path / "serie.nc"
    _nc_serie_sintetico(ruta)
    ds = io_era5._parsear_serie_nc(ruta, lat=-37.0, lon=-73.5)
    assert float(ds["Dir"].isel(time=0)) == pytest.approx(225.0)
    assert ds.attrs.get("dir_convencion") == "procedencia"


def test_serie_cache_sin_marca_de_convencion_se_descarta(tmp_path):
    """
    Las cachés parseadas antes del fix A2-1 guardan Dir invertida 180° y no
    llevan el atributo 'dir_convencion': deben tratarse como caché inutilizable
    para forzar el re-parseo/re-descarga.
    """
    import xarray as xr
    vieja = tmp_path / "era5_serie.nc"
    t = np.array(["2024-07-28T00"], dtype="datetime64[ns]")
    xr.Dataset({"Hs": ("time", [2.0]), "Tp": ("time", [12.0]),
                "Dir": ("time", [45.0])},
               coords={"time": t}).to_netcdf(vieja)
    assert io_era5._serie_cache_limpia(vieja) is False

    nueva = tmp_path / "era5_serie_ok.nc"
    ds = xr.Dataset({"Hs": ("time", [2.0])}, coords={"time": t},
                    attrs={"dir_convencion": "procedencia"})
    ds.to_netcdf(nueva)
    assert io_era5._serie_cache_limpia(nueva) is True


def test_parsear_serie_recorta_al_rango_pedido(tmp_path):
    """
    La petición CDS lista años/meses/días como conjuntos y el servidor devuelve
    el producto cartesiano: un rango que cruza año nuevo trae fechas espurias
    (p. ej. 2024-01 y 2025-12). El parser debe recortar a [inicio, fin]
    (auditoría 2026-07, hallazgo A2-2).
    """
    import xarray as xr
    t = np.array(["2024-01-20", "2024-12-25", "2025-01-05", "2025-12-20"],
                 dtype="datetime64[ns]")
    lat = np.array([-37.0]); lon = np.array([-73.5])
    forma = (len(t), 1, 1)
    ruta = tmp_path / "serie.nc"
    xr.Dataset(
        {"swh": (("valid_time", "latitude", "longitude"), np.full(forma, 2.0)),
         "pp1d": (("valid_time", "latitude", "longitude"), np.full(forma, 12.0)),
         "mwd": (("valid_time", "latitude", "longitude"), np.full(forma, 250.0))},
        coords={"valid_time": t, "latitude": lat, "longitude": lon}).to_netcdf(ruta)

    ds = io_era5._parsear_serie_nc(ruta, -37.0, -73.5,
                                   inicio="2024-12-20", fin="2025-01-10")
    fechas = ds["time"].values.astype("datetime64[D]").astype(str).tolist()
    assert fechas == ["2024-12-25", "2025-01-05"]


def test_parsear_espectro_recorta_al_rango_pedido(tmp_path):
    """El espectro d2fd usa la misma petición cartesiana: mismo recorte que la serie."""
    import xarray as xr
    t = np.array(["2024-01-20", "2024-12-25", "2025-01-05", "2025-12-20"],
                 dtype="datetime64[ns]")
    freqs = np.array([0.05, 0.1]); dirs = np.array([7.5, 22.5])
    ruta = tmp_path / "espectro.nc"
    xr.Dataset(
        {"d2fd": (("valid_time", "frequency", "direction"),
                  np.full((len(t), 2, 2), -1.0))},
        coords={"valid_time": t, "frequency": freqs, "direction": dirs}).to_netcdf(ruta)

    ds = io_era5._parsear_espectro_nc(ruta, inicio="2024-12-20", fin="2025-01-10")
    assert ds.sizes["time"] == 2


def test_seguridad_rechaza_nombre_caso_con_espacios():
    import seguridad
    with pytest.raises(ValueError):
        seguridad.sanitizar_nombre_caso("Mi Caso")


def test_seguridad_rechaza_path_traversal_en_salida():
    import seguridad
    with pytest.raises(ValueError):
        seguridad.sanitizar_nombre_fuente("../../fuera")


def test_confina_usuario_rechaza_ruta_sistema():
    import sys
    import seguridad
    ruta = r"C:\Windows\System32" if sys.platform == "win32" else "/etc"
    with pytest.raises(ValueError):
        seguridad.confina_usuario(ruta, "ruta")


def test_validar_rango_fechas_rechaza_fin_anterior():
    with pytest.raises(ValueError, match="posterior"):
        io_era5.validar_rango_fechas("2024-07-29", "2024-07-28")


def test_validar_caso_rechaza_borde_sin_tp_dir():
    errores, _ = swan_builder.validar_caso(
        {"xpc": 0, "ypc": 0, "xlenc": 1000, "ylenc": 1000, "mxc": 10, "myc": 10},
        {"archivo": "b.bot"},
        [{"lado": "W", "hs": 2.0, "per": None, "dir": None}],
    )
    assert len(errores) >= 2
    assert not any("TypeError" in e for e in errores)


def test_validar_caso_rechaza_borde_nan():
    import math
    errores, _ = swan_builder.validar_caso(
        {"xpc": 0, "ypc": 0, "xlenc": 1000, "ylenc": 1000, "mxc": 10, "myc": 10},
        {"archivo": "b.bot"},
        [{"lado": "W", "hs": float("nan"), "per": 12.0, "dir": 270.0}],
    )
    assert any("Hs" in e for e in errores)


def test_cds_url_rechaza_host_arbitrario():
    with pytest.raises(ValueError, match="Host CDS"):
        seguridad.validar_url_cds("https://evil.example/api")
    with pytest.raises(ValueError, match="https"):
        seguridad.validar_url_cds("http://cds.climate.copernicus.eu/api")


def test_nombre_fuente_no_colisiona_coords_cercanas():
    a = io_era5._nombre_fuente(-35.584, -72.661, "serie", "2024-01-01", "2024-01-31")
    b = io_era5._nombre_fuente(-35.586, -72.659, "serie", "2024-01-01", "2024-01-31")
    assert a != b


def test_longitud_para_grilla_0_360():
    lons = np.array([0.0, 60.0, 120.0, 180.0, 240.0, 300.0])
    assert io_era5._longitud_para_grilla(-73.5, lons) == pytest.approx(286.5)


def test_borde_retorno_periodo_uno_falla():
    import xarray as xr
    import borde_oleaje
    t = np.arange("2020-01-01", "2023-01-01", dtype="datetime64[D]")
    ds = xr.Dataset({"Hs": ("time", np.linspace(1, 3, len(t)))}, coords={"time": t})
    with pytest.raises(ValueError, match="mayor que 1"):
        borde_oleaje.condicion_borde(ds, "retorno", periodo_retorno=1)


def test_sanitizar_nombre_fuente_acepta_doble_punto():
    assert seguridad.sanitizar_nombre_fuente("caso..v2") == "caso..v2"


def test_malla_excesiva_rechazada():
    with pytest.raises(ValueError, match="celdas por lado"):
        geo_malla.malla_desde_latlon(-36, -73, 5000, 5000, 1)


def test_confina_ruta_existe_api():
    import api_web
    api = api_web.Api()
    assert api.ruta_existe("C:\\Windows\\System32") is False


def test_zip_era5_rechaza_entrada_fuera_de_tmp(tmp_path):
    import zipfile
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("../escape.nc", b"")
    with pytest.raises(ValueError, match="sospechosa"):
        io_era5._abrir_descarga_cds(zpath)


def test_validacion_sin_time_no_revienta():
    import xarray as xr
    ds = xr.Dataset({"Hs": ("x", [1.0, 2.0])}, coords={"x": [0, 1]})
    res = {r["nombre"]: r for r in validacion.validar(ds)}
    assert res["Continuidad temporal"]["n_falla"] == 0
    assert "sin coordenada" in res["Continuidad temporal"]["detalle"]


def test_validacion_cuenta_nan_como_falla():
    import xarray as xr
    ds = xr.Dataset(
        {"Hs": ("time", [1.0, np.nan]), "Tp": ("time", [10.0, 11.0]),
         "Dir": ("time", [270.0, 280.0])},
        coords={"time": np.arange(2)})
    res = {r["nombre"]: r for r in validacion.validar(ds)}
    assert res["Hs en rango plausible"]["n_falla"] >= 1


def test_particiones_descarga_mensual():
    partes = io_era5._particiones_descarga("2024-07-28", "2025-07-29")
    assert len(partes) >= 12
    assert partes[0][0] == "2024-07-28"
    assert partes[-1][1] == "2025-07-29"
    assert io_era5._particiones_descarga("2024-07-01", "2024-07-31") == [
        ("2024-07-01", "2024-07-31")]


def test_descargar_serie_largo_concatena_tramos(monkeypatch, tmp_path):
    """Un rango >31 días dispara varias peticiones CDS y concatena el resultado."""
    import xarray as xr

    llamadas = []

    def _falso_retrieve(dataset, peticion, destino):
        mes = int(peticion["month"][0])
        llamadas.append(mes)
        t = np.array([f"2024-{mes:02d}-15T00", f"2024-{mes:02d}-15T03"],
                     dtype="datetime64[ns]")
        lat = np.array([-36.75, -37.25])
        lon = np.array([-73.75, -73.25])
        forma = (len(t), len(lat), len(lon))
        xr.Dataset(
            {"swh": (("time", "latitude", "longitude"), np.full(forma, 2.5)),
             "pp1d": (("time", "latitude", "longitude"), np.full(forma, 12.0)),
             "mwd": (("time", "latitude", "longitude"), np.full(forma, 225.0))},
            coords={"time": t, "latitude": lat, "longitude": lon},
        ).to_netcdf(destino)

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            _falso_retrieve(dataset, peticion, destino)

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)

    ds = io_era5.descargar_serie(-37.0, -73.5, "2024-01-01", "2024-03-31")
    assert len(llamadas) == 3
    assert ds.sizes["time"] == 6
    _, destino = io_era5.ruta_cache_serie(-37.0, -73.5, "2024-01-01", "2024-03-31")
    assert destino.exists()
    ds.close()


def test_descargar_serie_paralelo_max_dos(monkeypatch, tmp_path):
    """Con varios tramos, no más de 2 peticiones CDS activas a la vez."""
    import time
    import threading
    import xarray as xr

    activos = {"n": 0, "max": 0}
    lock = threading.Lock()

    def _falso_retrieve(dataset, peticion, destino):
        mes = int(peticion["month"][0])
        with lock:
            activos["n"] += 1
            activos["max"] = max(activos["max"], activos["n"])
        time.sleep(0.08)
        t = np.array([f"2024-{mes:02d}-15T00", f"2024-{mes:02d}-15T03"],
                     dtype="datetime64[ns]")
        lat = np.array([-36.75, -37.25])
        lon = np.array([-73.75, -73.25])
        forma = (len(t), len(lat), len(lon))
        xr.Dataset(
            {"swh": (("time", "latitude", "longitude"), np.full(forma, 2.5)),
             "pp1d": (("time", "latitude", "longitude"), np.full(forma, 12.0)),
             "mwd": (("time", "latitude", "longitude"), np.full(forma, 225.0))},
            coords={"time": t, "latitude": lat, "longitude": lon},
        ).to_netcdf(destino)
        with lock:
            activos["n"] -= 1

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            _falso_retrieve(dataset, peticion, destino)

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)

    ds = io_era5.descargar_serie(-37.0, -73.5, "2024-01-01", "2024-04-30")
    assert ds.sizes["time"] == 8
    assert activos["max"] <= io_era5._MAX_TRAMOS_PARALELO
    assert activos["max"] == io_era5._MAX_TRAMOS_PARALELO
    ds.close()


def test_descargar_serie_usa_cliente_y_parsea(monkeypatch, tmp_path):
    """descargar_serie: pide al cliente, escribe el .nc y devuelve Dataset(time)."""
    def _falso_retrieve(dataset, peticion, destino):
        _nc_serie_sintetico(destino)          # simula la descarga del CDS

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            _falso_retrieve(dataset, peticion, destino)

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)

    ds = io_era5.descargar_serie(lat=-37.0, lon=-73.5,
                                 inicio="2024-07-28", fin="2024-07-28")
    assert {"Hs", "Tp", "Dir"} <= set(ds.data_vars)
    assert ds.sizes["time"] == 2


def test_nombre_fuente_incluye_rango_fechas():
    n = io_era5._nombre_fuente(-37.0, -73.5, "serie", "2024-01-01", "2024-03-31")
    assert "20240101" in n and "20240331" in n
    assert io_era5._nombre_fuente(-37.0, -73.5, "serie", "2024-01-01", "2024-03-31") != \
        io_era5._nombre_fuente(-37.0, -73.5, "serie", "2024-04-01", "2024-06-30")


def test_descargar_serie_rangos_distintos_no_comparten_cache(monkeypatch, tmp_path):
    """Dos periodos en el mismo punto usan carpetas distintas."""
    import xarray as xr
    llamadas = {"n": 0}

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            llamadas["n"] += 1
            # Fechas DENTRO del rango pedido (como el CDS real): con el recorte
            # temporal de A2-2, datos fuera del rango quedarían vacíos.
            anio, mes = peticion["year"][0], int(peticion["month"][0])
            t = np.array([f"{anio}-{mes:02d}-15T00", f"{anio}-{mes:02d}-15T03"],
                         dtype="datetime64[ns]")
            lat = np.array([-36.75, -37.25]); lon = np.array([-73.75, -73.25])
            forma = (len(t), len(lat), len(lon))
            xr.Dataset(
                {"swh": (("time", "latitude", "longitude"), np.full(forma, 2.5)),
                 "pp1d": (("time", "latitude", "longitude"), np.full(forma, 12.0)),
                 "mwd": (("time", "latitude", "longitude"), np.full(forma, 225.0))},
                coords={"time": t, "latitude": lat, "longitude": lon},
            ).to_netcdf(destino)

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)

    io_era5.descargar_serie(-37.0, -73.5, "2024-01-01", "2024-01-31")
    io_era5.descargar_serie(-37.0, -73.5, "2024-06-01", "2024-06-30")
    assert llamadas["n"] == 2
    _, nc1 = io_era5.ruta_cache_serie(-37.0, -73.5, "2024-01-01", "2024-01-31")
    _, nc2 = io_era5.ruta_cache_serie(-37.0, -73.5, "2024-06-01", "2024-06-30")
    assert nc1 != nc2
    assert nc1.exists() and nc2.exists()


def test_descargar_serie_redescarga_cache_corrupta(monkeypatch, tmp_path):
    """Una cache .nc vacía/corrupta no se usa: se vuelve a descargar."""
    llamadas = {"n": 0}

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            llamadas["n"] += 1
            _nc_serie_sintetico(destino)

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)

    # Deja una cache corrupta (0 bytes) en el sitio donde caería el .nc.
    carpeta = rutas.carpeta_salida(
        io_era5._nombre_fuente(-37.0, -73.5, "serie", "2024-07-28", "2024-07-28"))
    (carpeta / "era5_serie.nc").write_bytes(b"")

    ds = io_era5.descargar_serie(lat=-37.0, lon=-73.5,
                                 inicio="2024-07-28", fin="2024-07-28")
    assert llamadas["n"] == 1                  # ignoró la cache vacía y descargó
    assert ds.sizes["time"] == 2


def _zip_serie_sintetico(ruta):
    """Imita la descarga del CDS NUEVO: un ZIP con un .nc por 'stream' (olas y
    atmósfera), coordenada 'valid_time' y grillas lat/lon DISTINTAS por stream."""
    import xarray as xr
    import zipfile, tempfile, shutil
    t = np.array(["2024-07-28T00", "2024-07-28T03"], dtype="datetime64[ns]")
    tmp = Path(tempfile.mkdtemp())
    try:
        olas = xr.Dataset(
            {"swh": (("valid_time", "latitude", "longitude"), np.full((2, 1, 1), 2.5)),
             "pp1d": (("valid_time", "latitude", "longitude"), np.full((2, 1, 1), 12.0)),
             "mwd": (("valid_time", "latitude", "longitude"), np.full((2, 1, 1), 225.0))},
            coords={"valid_time": t, "latitude": [-37.0], "longitude": [-73.5],
                    "number": 0, "expver": "0001"})
        atm = xr.Dataset(
            {"u10": (("valid_time", "latitude", "longitude"), np.full((2, 3, 3), 1.0)),
             "v10": (("valid_time", "latitude", "longitude"), np.full((2, 3, 3), -2.0))},
            coords={"valid_time": t, "latitude": [-36.75, -37.0, -37.25],
                    "longitude": [-73.75, -73.5, -73.25], "number": 0, "expver": "0001"})
        p_olas = tmp / "data_stream-wave.nc"; olas.to_netcdf(p_olas)
        p_atm = tmp / "data_stream-oper.nc"; atm.to_netcdf(p_atm)
        with zipfile.ZipFile(ruta, "w") as z:
            z.write(p_olas, p_olas.name)
            z.write(p_atm, p_atm.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_parsear_serie_zip_multistream_cds_nuevo(tmp_path):
    """El CDS nuevo entrega un ZIP (aunque la extensión sea .nc) con olas y viento
    en streams separados; se unen, se selecciona el punto y valid_time→time."""
    ruta = tmp_path / "serie.nc"
    _zip_serie_sintetico(ruta)
    ds = io_era5._parsear_serie_nc(ruta, lat=-37.0, lon=-73.5)
    assert {"Hs", "Tp", "Dir", "u10", "v10"} <= set(ds.data_vars)
    assert "time" in ds.coords and ds.sizes["time"] == 2
    assert "valid_time" not in ds.coords
    assert float(ds["Hs"].isel(time=0)) == pytest.approx(2.5)
    assert "latitude" not in ds.dims          # punto ya seleccionado


def test_descargar_serie_cachea_nc_limpio_legible(monkeypatch, tmp_path):
    """El CDS deja un ZIP; la cache debe quedar como .nc LIMPIO que io_oleaje.cargar
    abre sin saber de ERA5 (Hs/Tp/Dir/time), y el crudo se limpia."""
    import io_oleaje

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            _zip_serie_sintetico(Path(destino))      # el CDS entrega un zip

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)

    ds = io_era5.descargar_serie(-37.0, -73.5, "2024-07-28", "2024-07-28")
    assert {"Hs", "Tp", "Dir"} <= set(ds.data_vars)

    carpeta = rutas.carpeta_salida(
        io_era5._nombre_fuente(-37.0, -73.5, "serie", "2024-07-28", "2024-07-28"))
    destino = carpeta / "era5_serie.nc"
    leido = io_oleaje.cargar(str(destino))           # el pipeline lo lee como .nc normal
    assert {"Hs", "Tp", "Dir"} <= set(leido.data_vars)
    assert "time" in leido.coords
    assert not (carpeta / "era5_serie_cruda.nc").exists()


def test_descargar_raster_rechaza_respuesta_no_netcdf(monkeypatch, tmp_path):
    """Un 200 con cuerpo de error (HTML) no debe guardarse como si fuera NetCDF."""
    import urllib.request
    from email.message import Message

    class _Resp:
        def __init__(self):
            self.status = 200
            self._h = Message(); self._h["Content-Type"] = "text/html"
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def getcode(self): return self.status
        @property
        def headers(self): return self._h
        def read(self): return b"<html>Error: bbox fuera de rango</html>"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    with pytest.raises(RuntimeError, match="NetCDF"):
        io_batimetria.descargar_raster(-33.1, -32.9, -71.8, -71.5, tmp_path / "r.nc")


def _nc_espectro_sintetico(ruta, *, con_grilla=False):
    """Crea un .nc tipo ERA5 2D spectra: d2fd en log10."""
    import xarray as xr
    t = np.array(["2024-07-28T00"], dtype="datetime64[ns]")
    freq = 0.03453 * 1.1 ** np.arange(30)         # 30 frecuencias ERA5
    direction = np.arange(7.5, 360.0, 15.0)       # 24 direcciones ERA5
    dens = np.full((len(t), len(freq), len(direction)), 0.5)   # densidad lineal
    d2fd = np.log10(dens)                          # ERA5 la almacena en log10
    if con_grilla:
        lat = np.array([-37.0, -36.75])
        lon = np.array([286.5, 286.75])            # 0–360 como ERA5
        d2fd = np.broadcast_to(
            d2fd[:, :, :, np.newaxis, np.newaxis],
            (len(t), len(freq), len(direction), len(lat), len(lon)),
        ).copy()
        ds = xr.Dataset(
            {"d2fd": (("time", "frequency", "direction", "latitude", "longitude"), d2fd)},
            coords={"time": t, "frequency": freq, "direction": direction,
                    "latitude": lat, "longitude": lon})
    else:
        ds = xr.Dataset(
            {"d2fd": (("time", "frequency", "direction"), d2fd)},
            coords={"time": t, "frequency": freq, "direction": direction})
    ds.to_netcdf(ruta)


def test_parsear_espectro_decodifica_log10_y_reordena(tmp_path):
    ruta = tmp_path / "espectro.nc"
    _nc_espectro_sintetico(ruta)
    esp = io_era5._parsear_espectro_nc(ruta)
    assert dict(esp.sizes) == {"time": 1, "freq": 30, "dir": 24}
    assert set(["Efth"]) <= set(esp.data_vars)
    # 10**log10(0.5) = 0.5 (des-logueo correcto).
    assert float(esp["Efth"].isel(time=0, freq=0, dir=0)) == pytest.approx(0.5)


def test_parsear_espectro_selecciona_punto_en_grilla(tmp_path):
    """El parser debe reducir lat/lon a un solo punto (como la serie ERA5)."""
    ruta = tmp_path / "espectro_grilla.nc"
    _nc_espectro_sintetico(ruta, con_grilla=True)
    esp = io_era5._parsear_espectro_nc(ruta, lat=-37.0, lon=-73.5)
    assert dict(esp.sizes) == {"time": 1, "freq": 30, "dir": 24}
    assert "latitude" not in esp["Efth"].dims


def test_parsear_espectro_reconstruye_ejes_de_bin(tmp_path):
    """
    La conversión GRIB→NetCDF del CDS entrega frequency/direction como números
    de bin (1..30 y 1..24): el parser debe reconstruir las magnitudes físicas
    (f₁=0,03453 Hz ·1,1ⁿ⁻¹; dir=7,5°+15°·(n−1), «hacia») y pasar la dirección a
    procedencia náutica (auditoría 2026-07, hallazgo A2-3).
    """
    import xarray as xr
    t = np.array(["2024-07-28T00"], dtype="datetime64[ns]")
    dens = np.full((1, 30, 24), 0.001)
    dens[0, :, 0] = 0.5          # energía concentrada en el bin 1 (hacia 7,5°)
    ruta = tmp_path / "espectro_bins.nc"
    xr.Dataset(
        {"d2fd": (("time", "frequency", "direction"), np.log10(dens))},
        coords={"time": t,
                "frequency": np.arange(1, 31, dtype=float),
                "direction": np.arange(1, 25, dtype=float)}).to_netcdf(ruta)

    esp = io_era5._parsear_espectro_nc(ruta)
    freqs = esp["freq"].values
    assert freqs[0] == pytest.approx(0.03453)
    assert freqs[-1] == pytest.approx(0.03453 * 1.1 ** 29, rel=1e-6)
    # La energía que iba «hacia 7,5°» debe quedar en procedencia 187,5°.
    e_por_dir = esp["Efth"].isel(time=0).sum("freq")
    dir_pico = float(esp["dir"].values[int(e_por_dir.argmax())])
    assert dir_pico == pytest.approx(187.5)
    assert esp["Efth"].attrs["units"] == "m2/Hz/rad"
    assert esp.attrs.get("ejes") == "fisicos"


def test_espectro_cache_sin_marca_de_ejes_se_descarta(tmp_path):
    """Cachés de espectro parseadas con ejes de bin (pre-fix A2-3) se descartan."""
    import xarray as xr
    t = np.array(["2024-07-28T00"], dtype="datetime64[ns]")
    vieja = tmp_path / "era5_espectro.nc"
    xr.Dataset(
        {"Efth": (("time", "freq", "dir"), np.full((1, 2, 2), 0.5))},
        coords={"time": t, "freq": [1.0, 2.0], "dir": [1.0, 2.0]}).to_netcdf(vieja)
    assert io_era5._espectro_cache_limpia(vieja) is False


def test_ruta_cache_espectro_comparte_carpeta_con_serie():
    c_serie, _ = io_era5.ruta_cache_serie(-37.0, -73.5, "2024-01-01", "2024-01-31")
    c_esp, nc_esp = io_era5.ruta_cache_espectro(-37.0, -73.5, "2024-01-01", "2024-01-31")
    assert c_serie == c_esp
    assert nc_esp.name == "era5_espectro.nc"


def test_descargar_espectro_tramos_y_cache_limpia(tmp_path, monkeypatch):
    """Espectro ERA5: parseo en punto, tramos y .nc limpio en carpeta de la serie."""
    import xarray as xr
    import rutas
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path)
    # Un hilo a la vez: netCDF4 no es thread-safe al escribir en tests paralelos.
    monkeypatch.setattr(io_era5, "_MAX_TRAMOS_PARALELO", 1)

    def _falso_retrieve(dataset, peticion, destino):
        mes = int(peticion["month"][0])
        t = np.array([f"2024-{mes:02d}-15T00", f"2024-{mes:02d}-15T03"],
                     dtype="datetime64[ns]")
        freq = 0.03453 * 1.1 ** np.arange(30)
        direction = np.arange(7.5, 360.0, 15.0)
        lat = np.array([-36.75, -37.25])
        lon = np.array([286.5, 286.75])
        dens = np.full((len(t), len(freq), len(direction), len(lat), len(lon)), 0.5)
        d2fd = np.log10(dens)
        xr.Dataset(
            {"d2fd": (("time", "frequency", "direction", "latitude", "longitude"), d2fd)},
            coords={"time": t, "frequency": freq, "direction": direction,
                    "latitude": lat, "longitude": lon},
        ).to_netcdf(destino)

    class _ClienteFalso:
        def retrieve(self, dataset, peticion, destino):
            _falso_retrieve(dataset, peticion, destino)

    monkeypatch.setattr(io_era5, "_cliente", lambda: _ClienteFalso())
    ds = io_era5.descargar_espectro(-37.0, -73.5, "2024-01-01", "2024-03-31")
    try:
        assert ds.sizes["time"] == 6
        assert set(ds["Efth"].dims) == {"time", "freq", "dir"}
        carpeta, destino = io_era5.ruta_cache_espectro(
            -37.0, -73.5, "2024-01-01", "2024-03-31")
        assert destino.is_file()
        assert io_era5._espectro_cache_limpia(destino)
        assert (carpeta / "chunks_espectro").is_dir()
    finally:
        ds.close()


def test_producto_espectro_medido_desde_efth():
    import xarray as xr
    import productos
    freqs, dirs, efth = _espectro_bimodal()
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), np.stack([efth])),
         "Hs": ("time", [1.0]), "Tp": ("time", [10.0]), "Dir": ("time", [270.0])},
        coords={"time": np.array(["2024-07-28T00"], dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    informe = productos.evaluar(ds)
    item = next(it for it in informe if it["nombre"] == "Espectro medido S(f)")
    assert item["disponible"]
    assert item["resultado"]["S"].max() > 0


def test_producto_espectro_medido_desde_sf():
    import xarray as xr
    import productos
    freqs = np.linspace(0.04, 0.40, 30)
    sf = np.exp(-((freqs - 0.10) / 0.02) ** 2)
    ds = xr.Dataset(
        {"Sf": (("freq",), sf), "Hs": ("time", [1.0]), "Tp": ("time", [10.0]),
         "Dir": ("time", [200.0])},
        coords={"time": np.array(["2024-07-28T00"], dtype="datetime64[ns]"),
                "freq": freqs})
    informe = productos.evaluar(ds)
    item = next(it for it in informe if it["nombre"] == "Espectro medido S(f)")
    assert item["disponible"]
    assert item["resultado"]["tp"] == pytest.approx(10.0, abs=1.0)


# --------------------------- Productos de partición ---------------------------
import productos_particion


def test_calcular_particion_resume_familias():
    import xarray as xr
    freqs, dirs, efth = _espectro_bimodal()
    cubo = np.stack([efth, efth])
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), cubo)},
        coords={"time": np.array(["2024-07-28T00", "2024-07-28T03"],
                                 dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    r = productos_particion.calcular_serie(ds)
    assert "series" in r and r["series"].sizes["familia"] == 2
    assert r["n_familias"] >= 2


def test_tabla_familias_exportable():
    """tabla_familias devuelve un DataFrame con una fila por familia del paso pico."""
    freqs, dirs, efth = _espectro_bimodal()
    tabla = productos_particion.tabla_familias(efth, freqs, dirs)
    assert list(tabla.columns) == ["familia", "tipo", "Hs", "Tp", "Dir"]
    assert len(tabla) == 2


def test_retorno_gumbel_no_disponible_con_serie_corta():
    """Con <2 años de datos, el producto Gumbel se marca no disponible (no se calcula)."""
    import xarray as xr
    import productos
    t = np.arange("2024-01-01", "2024-02-15", dtype="datetime64[D]")   # ~1 mes, 1 año
    ds = xr.Dataset({"Hs": ("time", np.linspace(1.0, 2.0, len(t)))}, coords={"time": t})
    informe = {it["nombre"]: it for it in productos.evaluar(ds)}
    gumbel = informe["Períodos de retorno (Gumbel)"]
    assert gumbel["disponible"] is False
    assert gumbel["resultado"] is None
    assert any("año" in f for f in gumbel["faltan"])      # motivo informado


def test_retorno_gumbel_calcular_serie_corta_lanza():
    """_calc_retorno directo con 1 año lanza ValueError claro, sin overflow silencioso."""
    import xarray as xr
    import productos
    t = np.arange("2024-01-01", "2024-02-01", dtype="datetime64[D]")
    ds = xr.Dataset({"Hs": ("time", np.linspace(1.0, 2.0, len(t)))}, coords={"time": t})
    with pytest.raises(ValueError, match="Gumbel"):
        productos._calc_retorno(ds)


def test_retorno_gumbel_disponible_con_serie_larga():
    """Con ≥2 años el producto Gumbel sí está disponible y calcula la curva."""
    import xarray as xr
    import productos
    t = np.arange("2018-01-01", "2022-01-01", dtype="datetime64[D]")   # 4 años
    rng = np.random.default_rng(0)
    ds = xr.Dataset({"Hs": ("time", 1.5 + np.abs(rng.normal(0, 0.6, len(t))))},
                    coords={"time": t})
    informe = {it["nombre"]: it for it in productos.evaluar(ds)}
    gumbel = informe["Períodos de retorno (Gumbel)"]
    assert gumbel["disponible"] is True
    assert 100 in gumbel["resultado"]["diseno"]


def test_serie_corta_usa_resolucion_nativa():
    """Con < 365 días de span, la serie temporal no agrega por mes."""
    import xarray as xr
    import productos
    t = np.arange("2024-07-01", "2024-08-01", dtype="datetime64[3h]")
    hs = np.linspace(1.0, 2.0, len(t))
    ds = xr.Dataset({"Hs": ("time", hs)}, coords={"time": t})
    r = productos._calc_serie(ds)
    assert r["modo"] == "nativa"
    assert len(r["hs"]) == len(t)


def test_serie_larga_usa_media_mensual():
    """Con ≥ 365 días de span, la serie temporal se agrega mensualmente."""
    import xarray as xr
    import productos
    t = np.arange("2020-01-01", "2022-01-01", dtype="datetime64[D]")
    ds = xr.Dataset({"Hs": ("time", np.ones(len(t)))}, coords={"time": t})
    r = productos._calc_serie(ds)
    assert r["modo"] == "mensual"
    assert len(r["hs"]) == 24          # 24 meses en 2 años


def test_climatologia_y_extremos_no_disponibles_serie_corta():
    """Climatología y régimen extremo requieren span ≥ 730 d y ≥ 2 años calendario."""
    import xarray as xr
    import productos
    t = np.arange("2024-07-01", "2024-09-01", dtype="datetime64[3h]")
    ds = xr.Dataset({"Hs": ("time", np.linspace(1.0, 2.0, len(t)))}, coords={"time": t})
    informe = {it["nombre"]: it for it in productos.evaluar(ds)}
    for nombre in ("Climatología mensual", "Régimen extremo (máx. anual)",
                   "Períodos de retorno (Gumbel)"):
        item = informe[nombre]
        assert item["disponible"] is False
        assert item["resultado"] is None
        assert any("730" in f or "año" in f for f in item["faltan"])


def test_multi_anual_no_disponible_un_ano_dos_calendarios():
    """Jul-2024→jul-2025: 2 años en el eje pero span ~1 año → sin paneles multi-anuales."""
    import xarray as xr
    import productos
    t = np.arange("2024-07-28", "2025-07-29", dtype="datetime64[h]")
    ds = xr.Dataset({"Hs": ("time", 1.5 + 0.5 * np.sin(np.linspace(0, 20, len(t))))},
                    coords={"time": t})
    assert productos._n_anios(ds) == 2
    assert productos._span_dias(ds) < productos._MIN_DIAS_MULTI_ANUAL
    informe = {it["nombre"]: it for it in productos.evaluar(ds)}
    for nombre in ("Climatología mensual", "Régimen extremo (máx. anual)",
                   "Períodos de retorno (Gumbel)"):
        assert informe[nombre]["disponible"] is False


def test_multi_anual_disponible_dos_anios_completos():
    """Ene-2020→dic-2021: span ≥ 730 d y 2 años calendario → paneles multi-anuales."""
    import xarray as xr
    import productos
    t = np.arange("2020-01-01", "2022-01-01", dtype="datetime64[D]")
    rng = np.random.default_rng(1)
    ds = xr.Dataset({"Hs": ("time", 1.5 + np.abs(rng.normal(0, 0.5, len(t))))},
                    coords={"time": t})
    assert productos.datos_suficientes_multi_anual(ds)
    informe = {it["nombre"]: it for it in productos.evaluar(ds)}
    for nombre in ("Climatología mensual", "Régimen extremo (máx. anual)",
                   "Períodos de retorno (Gumbel)"):
        assert informe[nombre]["disponible"] is True


def test_excedencia_incluye_percentiles():
    import xarray as xr
    import productos
    t = np.arange("2024-07-01", "2024-08-01", dtype="datetime64[3h]")
    ds = xr.Dataset({"Hs": ("time", np.linspace(1.0, 3.0, len(t)))}, coords={"time": t})
    r = productos._calc_excedencia(ds)
    assert set(r["percentiles"]) == {50, 90, 99}
    assert r["percentiles"][50] < r["percentiles"][99]


def test_registro_productos_detecta_particion_con_efth():
    import xarray as xr
    import productos
    freqs, dirs, efth = _espectro_bimodal()
    ds = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), np.stack([efth]))},
        coords={"time": np.array(["2024-07-28T00"], dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    informe = productos.evaluar(ds)
    item = next(i for i in informe if i["nombre"] == "Partición sea/swell (serie)")
    assert item["disponible"] is True


def test_espectro_particionado_registrado_en_swan():
    import productos_swan
    # Una corrida mínima con espectro (un paso) y sin dominios.
    import xarray as xr
    freqs, dirs, efth = _espectro_bimodal()
    espectro = xr.Dataset(
        {"Efth": (("time", "freq", "dir"), np.stack([efth]))},
        coords={"time": np.array(["2024-07-28T00"], dtype="datetime64[ns]"),
                "freq": freqs, "dir": dirs})
    corrida = {"dominios": {}, "espectro": espectro, "meta": {}}
    informe = productos_swan.evaluar(corrida)
    item = next(i for i in informe if i["nombre"] == "Espectro particionado")
    assert item["disponible"] is True
    assert item["proyeccion"] == "polar"


def test_asegurar_salida_estandar_repara_stdout_none(monkeypatch):
    """Bajo pythonw (stdout/stderr None), el guard los repara y print() no revienta."""
    import app_tablero
    import sys
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    app_tablero._asegurar_salida_estandar()
    assert sys.stdout is not None and sys.stderr is not None
    print("esto no debe lanzar")               # escribir al sumidero es seguro
    sys.stderr.write("ni esto")


def test_validar_inputs_era5_convierte_y_valida():
    import app_tablero
    lat, lon = app_tablero.validar_inputs_era5("-37.0", "-73.5",
                                               "2024-07-28", "2024-07-29")
    assert (lat, lon) == pytest.approx((-37.0, -73.5))
    with pytest.raises(ValueError):
        app_tablero.validar_inputs_era5("abc", "-73.5", "2024-07-28", "2024-07-29")


# --------------------------- Borde de oleaje (puente SWAN) ---------------------------
import borde_oleaje


def _serie_sintetica(con_dir=True):
    """Serie de 12 años con un temporal real conocido (peak) en una fecha."""
    import xarray as xr
    t = np.arange("2008-01-01", "2020-01-01", dtype="datetime64[D]")   # 12 años
    n = len(t)
    rng = np.random.default_rng(0)
    hs = 1.5 + np.abs(rng.normal(0.0, 0.7, n))
    tp = 6.0 + 0.5 * hs
    dirr = np.full(n, 200.0)
    ipk = 1500
    hs[ipk], tp[ipk], dirr[ipk] = 9.0, 14.0, 315.0    # peak real
    data = {"Hs": ("time", hs), "Tp": ("time", tp)}
    if con_dir:
        data["Dir"] = ("time", dirr)
    return xr.Dataset(data, coords={"time": t}), ipk, hs, tp, dirr


def test_borde_maximo_toma_el_peak():
    ds, ipk, hs, tp, dirr = _serie_sintetica()
    b = borde_oleaje.condicion_borde(ds, "maximo")
    assert b["hs"] == pytest.approx(9.0)
    assert b["per"] == pytest.approx(14.0)
    assert b["dir"] == pytest.approx(315.0)
    assert "Máximo observado" in b["descripcion"]


def test_borde_retorno_monotono_y_hereda_peak():
    ds, *_ = _serie_sintetica()
    b100 = borde_oleaje.condicion_borde(ds, "retorno", 100)
    b2 = borde_oleaje.condicion_borde(ds, "retorno", 2)
    assert b100["hs"] > b2["hs"]                 # T mayor → Hs mayor (Gumbel monótono)
    assert b100["per"] == pytest.approx(14.0)    # Tp/Dir heredados del peak real
    assert b100["dir"] == pytest.approx(315.0)
    assert "T=100" in b100["descripcion"]


def test_borde_retorno_pocos_datos_falla():
    import xarray as xr
    t = np.arange("2020-01-01", "2020-02-01", dtype="datetime64[D]")   # 1 año solo
    ds = xr.Dataset({"Hs": ("time", np.linspace(1, 3, len(t)))}, coords={"time": t})
    with pytest.raises(ValueError, match="2 años"):
        borde_oleaje.condicion_borde(ds, "retorno")


def test_borde_retorno_un_ano_dos_calendarios_falla():
    """Gumbel en borde exige span ≥ 730 d, no solo 2 años calendario."""
    import xarray as xr
    t = np.arange("2024-07-28", "2025-07-29", dtype="datetime64[h]")
    ds = xr.Dataset({"Hs": ("time", np.linspace(1, 3, len(t)))}, coords={"time": t})
    with pytest.raises(ValueError, match="730"):
        borde_oleaje.condicion_borde(ds, "retorno")


def test_borde_reinante_mediana_y_sector():
    ds, ipk, hs, tp, dirr = _serie_sintetica()
    b = borde_oleaje.condicion_borde(ds, "reinante")
    assert b["hs"] == pytest.approx(float(np.median(hs)))
    assert b["dir"] == pytest.approx(191.25)     # sector dominante de 200° (180–202.5)
    assert "reinante" in b["descripcion"].lower()


def test_borde_sin_dir_devuelve_none():
    ds, *_ = _serie_sintetica(con_dir=False)
    b = borde_oleaje.condicion_borde(ds, "maximo")
    assert b["dir"] is None
    assert b["per"] == pytest.approx(14.0)


def test_builder_emite_set_nautical():
    txt = swan_builder.construir_swn(
        nombre="T", malla={"xpc": 0., "ypc": 0., "xlenc": 1000, "ylenc": 1000,
                           "mxc": 10, "myc": 10},
        batimetria={"archivo": "f.bot"},
        bordes=[{"lado": "W", "hs": 2., "per": 10., "dir": 270., "dd": 15.}],
        salidas=("Hs", "Dir"))
    assert "SET NAUTICAL" in txt
    # el borde y el resto siguen intactos
    assert "BOUN SIDE W CCW CON PAR 2.0 10.0 270.0 15.0" in txt
    assert "CGRID 0.0 0.0 0.0 1000 1000 10 10 CIRCLE" in txt


def test_aplicar_borde_rellena_formulario():
    import gui_swan

    class _Var:
        def __init__(self): self.valor = None
        def set(self, v): self.valor = str(v)

    class _Log:
        def insert(self, *a): pass
        def see(self, *a): pass

    class _Stub:
        def __init__(self):
            self.v = {"hs": _Var(), "per": _Var(), "dir": _Var()}
            self.log = _Log()

    stub = _Stub()
    borde = {"hs": 8.0, "per": 14.0, "dir": 315.0, "descripcion": "máx"}
    gui_swan.VentanaSwan.aplicar_borde(stub, borde)
    assert stub.v["hs"].valor == "8"
    assert stub.v["per"].valor == "14"
    assert stub.v["dir"].valor == "315"

    # Dir None → campo en blanco, sin reventar
    stub2 = _Stub()
    gui_swan.VentanaSwan.aplicar_borde(stub2, {"hs": 2.0, "per": None, "dir": None,
                                               "descripcion": "x"})
    assert stub2.v["hs"].valor == "2"
    assert stub2.v["per"].valor == ""
    assert stub2.v["dir"].valor == ""


def test_gui_swan_expone_dialogo_y_handler():
    import gui_swan
    assert callable(gui_swan.dialogo_condicion)
    assert hasattr(gui_swan.VentanaSwan, "_tomar_borde_archivo")
    assert hasattr(gui_swan.VentanaSwan, "aplicar_borde")


def test_app_tablero_importa_borde():
    import app_tablero
    import borde_oleaje, io_oleaje      # deben ser importables desde app_tablero
    assert hasattr(app_tablero, "validar_inputs_era5")


# --------------------------- Batimetría automática ---------------------------
import io_batimetria


def test_epsg_utm_parsea_zona():
    assert io_batimetria.epsg_utm("19S") == 32719
    assert io_batimetria.epsg_utm("18S") == 32718
    assert io_batimetria.epsg_utm("19N") == 32619
    assert io_batimetria.epsg_utm(" 18s ") == 32718      # tolerante a espacios/caso
    with pytest.raises(ValueError):
        io_batimetria.epsg_utm("ABC")


def test_normalizar_raster_etopo_y_gebco():
    import xarray as xr
    lat = np.array([-32.9, -33.0, -33.1])      # descendente (como ETOPO)
    lon = np.array([-71.8, -71.7, -71.6])
    alt = np.arange(9).reshape(3, 3).astype(float)

    etopo = xr.Dataset({"altitude": (("latitude", "longitude"), alt)},
                       coords={"latitude": lat, "longitude": lon})
    out = io_batimetria._normalizar_raster(etopo)
    assert "elevation" in out.data_vars
    assert "lat" in out.dims and "lon" in out.dims
    assert float(out["lat"][0]) < float(out["lat"][-1])    # ordenado ascendente

    gebco = xr.Dataset({"elevation": (("lat", "lon"), alt)},
                       coords={"lat": lat[::-1], "lon": lon})
    out2 = io_batimetria._normalizar_raster(gebco)
    assert "elevation" in out2.data_vars and "lat" in out2.dims


def _raster_sintetico(elev_func):
    """Raster lat/lon (50×50) sobre Reñaca con elevation = elev_func(LAT, LON)."""
    import xarray as xr
    lat = np.linspace(-33.2, -32.8, 50)
    lon = np.linspace(-71.9, -71.4, 50)
    LAT, LON = np.meshgrid(lat, lon, indexing="ij")
    return xr.Dataset({"elevation": (("lat", "lon"), elev_func(LAT, LON))},
                      coords={"lat": lat, "lon": lon})


def test_generar_bot_signo_y_cantidad(tmp_path):
    raster = _raster_sintetico(lambda LAT, LON: np.full_like(LAT, -50.0))  # 50 m mar
    malla = {"xpc": 250000.0, "ypc": 6340000.0, "xlenc": 2000.0,
             "ylenc": 2000.0, "mxc": 5, "myc": 5}
    ruta, meta = io_batimetria.generar_bot(malla, "19S", tmp_path, raster=raster)
    bat = np.array(ruta.read_text().split(), dtype=float)
    assert bat.size == (5 + 1) * (5 + 1)                 # (mxc+1)·(myc+1)
    assert np.allclose(bat, 50.0, atol=1.0)              # depth = -(-50) = 50 m
    assert meta["prof_min"] > 0


def test_generar_bot_orientacion_norte_sur(tmp_path):
    # elevation crece con la latitud (más al norte = más alto) → depth menor al norte.
    raster = _raster_sintetico(lambda LAT, LON: (LAT + 33.0) * 1000.0)
    malla = {"xpc": 250000.0, "ypc": 6340000.0, "xlenc": 4000.0,
             "ylenc": 4000.0, "mxc": 8, "myc": 10}
    ruta, meta = io_batimetria.generar_bot(malla, "19S", tmp_path, raster=raster)
    bat = np.array(ruta.read_text().split(), dtype=float)
    ny, nx = 10 + 1, 8 + 1
    # io_swan reconstruye depth así; la fila norte (índice -1) debe ser menos profunda.
    depth = np.flipud(bat.reshape(ny, nx))
    assert depth[-1, :].mean() < depth[0, :].mean()


def test_leer_bot_como_grilla_rechaza_conteo_incorrecto(tmp_path):
    malla = {"xpc": 0, "ypc": 0, "xlenc": 1000, "ylenc": 1000, "mxc": 5, "myc": 5}
    bot = tmp_path / "mal.bot"
    bot.write_text(" ".join("1.0" for _ in range(20)))
    with pytest.raises(ValueError, match="requiere 36"):
        io_batimetria.leer_bot_como_grilla(bot, malla)


def test_validar_bot_malla_ok_y_rechazo(tmp_path):
    import motor_web
    malla = {"xpc": 0, "ypc": 0, "xlenc": 1000, "ylenc": 1000, "mxc": 2, "myc": 2}
    ok_bot = tmp_path / "ok.bot"
    ok_bot.write_text("\n".join(f"{10 + i:.2f}" for i in range(9)))
    res = motor_web.validar_bot_malla(str(ok_bot), malla)
    assert res["ok"] is True
    assert res["meta"]["n_nodos"] == 9
    assert res["meta"]["estado"] in ("ok", "warn")

    mal_bot = tmp_path / "mal.bot"
    mal_bot.write_text("1.0\n" * 20)
    res2 = motor_web.validar_bot_malla(str(mal_bot), malla)
    assert res2["ok"] is False
    assert res2["meta"]["n_esperados"] == 9
    assert "9" in res2["error"]


def test_preview_batimetria_exige_conteo_correcto(tmp_path):
    import motor_web
    malla = {"xpc": 0, "ypc": 0, "xlenc": 1000, "ylenc": 1000, "mxc": 2, "myc": 2}
    bot = tmp_path / "b.bot"
    bot.write_text("\n".join("5.0" for _ in range(9)))
    url = motor_web.preview_batimetria(str(bot), malla)
    assert url.startswith("data:image/png;base64,")
    bot.write_text("1.0\n" * 20)
    with pytest.raises(ValueError, match="requiere 9"):
        motor_web.preview_batimetria(str(bot), malla)


def test_url_erddap_arma_bbox():
    url = io_batimetria._url_erddap(-33.1, -32.9, -71.8, -71.5)
    assert url.startswith("https://")
    assert "etopo180.nc?altitude" in url
    assert "-33.1" in url and "-71.5" in url


def test_gui_swan_expone_generar_batimetria():
    import gui_swan
    assert hasattr(gui_swan.VentanaSwan, "_generar_batimetria")
    assert hasattr(gui_swan.VentanaSwan, "_bati_worker")
    import io_batimetria
    assert callable(io_batimetria.generar_bot)


# --------------------------- Malla por lat/lon ---------------------------
import geo_malla


def test_malla_desde_latlon_renaca():
    m = geo_malla.malla_desde_latlon(-32.97, -71.55, 8.0, 8.0, 100.0)
    assert m["zona_utm"] == "19S"
    assert m["mxc"] == 80 and m["myc"] == 80
    assert m["xlenc"] == 8000.0 and m["ylenc"] == 8000.0
    # round-trip: el centro de la malla calculada vuelve a ~(-71.55, -32.97)
    from pyproj import Transformer
    from io_batimetria import epsg_utm
    a_geo = Transformer.from_crs(epsg_utm("19S"), 4326, always_xy=True)
    lon_c, lat_c = a_geo.transform(m["xpc"] + m["xlenc"] / 2,
                                   m["ypc"] + m["ylenc"] / 2)
    assert lon_c == pytest.approx(-71.55, abs=1e-3)
    assert lat_c == pytest.approx(-32.97, abs=1e-3)


def test_malla_zona_por_longitud():
    assert geo_malla.malla_desde_latlon(-33.0, -73.0, 5, 5, 100)["zona_utm"] == "18S"
    assert geo_malla.malla_desde_latlon(-33.0, -71.55, 5, 5, 100)["zona_utm"] == "19S"


def test_malla_validaciones():
    with pytest.raises(ValueError):
        geo_malla.malla_desde_latlon(-33.0, -71.55, 1.0, 1.0, 2000.0)   # celda > extensión
    with pytest.raises(ValueError):
        geo_malla.malla_desde_latlon(200.0, -71.55, 5, 5, 100)          # lat fuera de rango


def test_gui_swan_expone_definir_malla_latlon():
    import gui_swan
    assert callable(gui_swan.dialogo_latlon)
    assert hasattr(gui_swan.VentanaSwan, "_definir_malla_latlon")


# --------------------------- Carreras GUI/hilos ---------------------------
def test_ventana_swan_cierre_cancela_proceso(monkeypatch):
    """Cerrar la ventana mientras corre SWAN cancela y mata el árbol de procesos."""
    import gui_swan
    import swan_runner
    import tkinter as tk
    matados = []
    monkeypatch.setattr(swan_runner, "matar_proceso_arbol",
                        lambda proc: matados.append(proc))
    root = tk.Tk(); root.withdraw()
    try:
        win = gui_swan.VentanaSwan(root)

        class _Proc:
            def poll(self): return None

        p = _Proc()
        win._proc = p
        win._al_cerrar()
        assert matados == [p]
        assert win._cancelar.is_set()
    finally:
        root.destroy()


def test_ventana_swan_marshal_no_revienta_tras_cerrar():
    """Un callback de hilo agendado tras cerrar la ventana no debe lanzar ni ejecutarse."""
    import gui_swan
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        win = gui_swan.VentanaSwan(root)
        win.destroy()
        llamado = []
        win._marshal(lambda: llamado.append(1))      # ventana muerta: no debe lanzar
        assert llamado == []                          # ni ejecutar el callback
    finally:
        root.destroy()


# --------------------------- I/O robusto (entradas frágiles) ---------------------------
def test_leer_mat_sin_variable_esperada(tmp_path):
    """Un .mat sin la variable pedida da un error claro que lista las disponibles."""
    from scipy.io import savemat
    ruta = tmp_path / "raro.mat"
    savemat(ruta, {"OtraCosa": np.zeros((10, 7))})
    with pytest.raises(ValueError, match="DataTarea"):
        io_oleaje.cargar(ruta)
    with pytest.raises(ValueError, match="OtraCosa"):
        io_oleaje._leer_mat(ruta)


def test_leer_mat_columnas_incorrectas(tmp_path):
    """Una matriz con un nº de columnas distinto al esperado no se acepta a ciegas."""
    from scipy.io import savemat
    ruta = tmp_path / "corta.mat"
    savemat(ruta, {"DataTarea": np.zeros((10, 3))})       # se esperan 7 columnas
    with pytest.raises(ValueError, match="columnas"):
        io_oleaje._leer_mat(ruta)


def test_cgrid_mxc_cero_es_error(tmp_path):
    """CGRID con mxc=0 no debe provocar ZeroDivisionError, sino un error claro."""
    swn = tmp_path / "degenerado.swn"
    swn.write_text("CGRID 0 0 0 1000 1000 0 10 CIRCLE 36 0.04 1\n")
    with pytest.raises(ValueError, match="mxc/myc"):
        io_swan._leer_cgrid(swn)
    with pytest.raises(ValueError, match="mxc/myc"):
        io_swan_nonst._leer_cgrid(swn)


def test_cgrid_truncado_es_error(tmp_path):
    """CGRID con menos tokens de los necesarios da un error claro, no IndexError."""
    swn = tmp_path / "trunco.swn"
    swn.write_text("CGRID 0 0 0 1000\n")
    with pytest.raises(ValueError, match="incompleto"):
        io_swan._leer_cgrid(swn)


def test_espectro_swan_truncado_es_error(tmp_path):
    """SPEC2D estacionario con la matriz truncada → ValueError, no IndexError."""
    esp = tmp_path / "spectro.dat"
    esp.write_text("\n".join([
        "AFREQ", "2", "0.1", "0.2",
        "CDIR", "2", "0.0", "90.0",
        "FACTOR", "1.0",
        "1 2",                                   # falta la 2ª fila de la matriz
    ]) + "\n")
    with pytest.raises(ValueError, match="truncad"):
        io_swan.leer_espectro_swan(esp)


def test_espectro_temporal_truncado_es_error(tmp_path):
    """SPEC2D temporal con la matriz truncada → ValueError, no IndexError."""
    esp = tmp_path / "spectro_temporal.dat"
    esp.write_text("\n".join([
        "SWAN 1",
        "AFREQ", "2", "0.1", "0.2",
        "CDIR", "2", "0.0", "90.0",
        "20240728.000000", "FACTOR", "1.0",
        "1 2",                                   # falta la 2ª fila
    ]) + "\n")
    with pytest.raises(ValueError, match="truncad"):
        io_swan_nonst.leer_espectro_temporal(esp)


# --------------------------- Validación física ---------------------------
import validacion


def test_chequeo_tiempo_un_solo_paso_no_revienta():
    """Serie de 1 timestamp: mode() vendría vacío; el chequeo no debe lanzar."""
    import xarray as xr
    ds = xr.Dataset({"Hs": ("time", [1.5])},
                    coords={"time": np.array(["2024-07-28T00"], dtype="datetime64[ns]")})
    res = {r["nombre"]: r for r in validacion.validar(ds)}
    cont = res["Continuidad temporal"]
    assert cont["aplicable"] is True
    assert cont["n_falla"] == 0
    assert "1 paso" in cont["detalle"]


def test_chequeo_tiempo_serie_vacia_no_revienta():
    """Serie sin pasos: tampoco debe lanzar IndexError."""
    import xarray as xr
    ds = xr.Dataset({"Hs": ("time", np.array([], dtype=float))},
                    coords={"time": np.array([], dtype="datetime64[ns]")})
    n_falla, _ = validacion._chequeo_tiempo(ds)
    assert n_falla == 0


def test_chequeo_tiempo_detecta_hueco_y_duplicado():
    """Con ≥2 pasos sigue detectando huecos y duplicados (no se rompió el caso normal)."""
    import xarray as xr
    # Paso dominante 3 h (dos veces), un duplicado (0 h) y un hueco (12 h).
    t = np.array(["2024-07-28T00", "2024-07-28T03", "2024-07-28T06",
                  "2024-07-28T06",                                    # duplicado
                  "2024-07-28T18"], dtype="datetime64[ns]")          # hueco
    ds = xr.Dataset({"Hs": ("time", [1.0, 1.1, 1.2, 1.3, 1.4])}, coords={"time": t})
    n_falla, detalle = validacion._chequeo_tiempo(ds)
    assert n_falla == 2
    assert "1 huecos" in detalle and "1 duplicados" in detalle


def test_revision_datos_estructurada(tmp_path):
    import xarray as xr
    import motor_web
    nc = tmp_path / "serie.nc"
    t = np.array(["2020-01-01", "2020-06-01", "2021-01-01"], dtype="datetime64[ns]")
    ds = xr.Dataset(
        {"Hs": ("time", [1.0, 2.0, 1.5]), "Tp": ("time", [10.0, 11.0, 10.5]),
         "Dir": ("time", [270.0, 280.0, 275.0])},
        coords={"time": t},
    )
    ds.to_netcdf(nc)
    ds.close()
    res = motor_web.revision_datos(str(nc))
    assert "validacion" in res and "productos" in res
    assert res["n_pasos"] == 3
    assert isinstance(res["validacion"], list)


def test_comparar_series(tmp_path):
    import xarray as xr
    import motor_web
    t = np.array(["2020-01-01", "2020-02-01", "2020-03-01"], dtype="datetime64[ns]")
    for nombre, hs in (("a.nc", [1.0, 2.0, 3.0]), ("b.nc", [1.1, 1.9, 3.2])):
        ds = xr.Dataset({"Hs": ("time", hs), "Tp": ("time", [10]*3), "Dir": ("time", [270]*3)},
                        coords={"time": t})
        ds.to_netcdf(tmp_path / nombre)
        ds.close()
    c = motor_web.comparar_series(str(tmp_path / "a.nc"), str(tmp_path / "b.nc"))
    assert c["n"] == 3
    assert c["rmse"] >= 0


def test_listar_cache_era5_vacio(monkeypatch, tmp_path):
    import motor_web
    import rutas
    monkeypatch.setattr(rutas, "RAIZ_SALIDAS", tmp_path / "salidas")
    (tmp_path / "salidas").mkdir()
    assert motor_web.listar_cache_era5() == []


def test_preview_malla_devuelve_data_url():
    import motor_web
    malla = {"xpc": 600000, "ypc": 5800000, "xlenc": 8000, "ylenc": 8000,
             "mxc": 80, "myc": 80, "zona_utm": "19S"}
    url = motor_web.preview_malla(malla, -37.0, -73.5)
    assert url.startswith("data:image/png;base64,")


def test_listar_plantillas_malla():
    import motor_web
    pl = motor_web.listar_plantillas_malla()
    assert any(p["id"] == "coronel" for p in pl)
    coronel = next(p for p in pl if p["id"] == "coronel")
    assert "nido" in coronel


def test_evaluar_resolucion_malla_fina():
    import motor_web
    malla = {"mxc": 80, "myc": 80, "xlenc": 8000, "ylenc": 8000}
    ev = motor_web.evaluar_resolucion_malla(malla)
    assert ev["celda_m"] == 100
    assert any("ETOPO" in a for a in ev["avisos"])


def test_checklist_correr_swan():
    import motor_web
    ctx = {
        "carpeta_caso": "C:/tmp/caso",
        "dominios": [{"malla": {"mxc": 1}, "bot": "b.bot", "bordes": [{"lado": "W"}]}],
    }
    items = motor_web.checklist_correr_swan(ctx)
    assert all(i["ok"] for i in items)


def test_preview_malla_anidada():
    import motor_web
    g = {"xpc": 600000, "ypc": 5800000, "xlenc": 48000, "ylenc": 59000,
         "mxc": 48, "myc": 59, "zona_utm": "19S"}
    n = {"xpc": 620000, "ypc": 5820000, "xlenc": 9000, "ylenc": 10000,
         "mxc": 45, "myc": 50, "zona_utm": "19S"}
    url = motor_web.preview_malla_anidada(g, n)
    assert url.startswith("data:image/png;base64,")


def test_registrar_recientes(tmp_path, monkeypatch):
    import motor_web
    import config
    png = tmp_path / "tablero.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
    monkeypatch.setattr(config, "_RUTA", tmp_path / "config.json")
    motor_web.registrar_producto(str(png), "tablero_oleaje")
    items = motor_web.listar_recientes()
    assert len(items) == 1
    assert items[0]["nombre"] == "tablero.png"
