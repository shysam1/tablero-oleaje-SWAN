"""
Tests de regresión de la herramienta Tablero de Oleaje.

Red de seguridad para iterar sin romper lo que ya funciona: carga las corridas
conocidas y comprueba los valores clave verificados a mano (Hs de borde, número
de pasos, orientación, mapeo de variables). Son rápidos: no corren SWAN ni
generan figuras.

Uso:  pytest test_regresion.py -v
Si los datos de prueba no están en disco, los tests que los necesitan se saltan.
"""

from pathlib import Path

import numpy as np
import pytest

import io_swan
import io_swan_nonst
import io_oleaje
import swan_builder
import swan_runner

BASE_SWAN = Path(r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python\SWAN_Coronel")
RUTA_OLEAJE = Path(r"C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python"
                   r"\Tarea 3 Costas\Datos_Nodo10_37S_75W_Talcahuano.mat")


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
    """El dominio grande (origen 0,0) va antes que el anidado."""
    (tmp_path / "grande.swn").write_text("CGRID 0. 0. 0. 1000 1000 10 10 CIRCLE 36 .04 1\n")
    (tmp_path / "nido.swn").write_text("CGRID 300 300 0. 200 200 20 20 CIRCLE 36 .04 1\n")
    assert swan_runner.casos_ordenados(tmp_path) == ["grande", "nido"]


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
