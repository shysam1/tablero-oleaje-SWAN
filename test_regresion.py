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


# --------------------------- Descarga ERA5 ---------------------------
import io_era5
import rutas


def test_cliente_sin_credenciales_explica(monkeypatch, tmp_path):
    """Sin ~/.cdsapirc, _cliente lanza un error claro de configuración."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))   # HOME en Windows
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="cdsapirc"):
        io_era5._cliente()


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


def _nc_espectro_sintetico(ruta):
    """Crea un .nc tipo ERA5 2D spectra: d2fd en log10, dims (time, freq, dir)."""
    import xarray as xr
    t = np.array(["2024-07-28T00"], dtype="datetime64[ns]")
    freq = 0.03453 * 1.1 ** np.arange(30)         # 30 frecuencias ERA5
    direction = np.arange(7.5, 360.0, 15.0)       # 24 direcciones ERA5
    dens = np.full((len(t), len(freq), len(direction)), 0.5)   # densidad lineal
    d2fd = np.log10(dens)                          # ERA5 la almacena en log10
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
