"""Regresiones de portabilidad y exactitud SWAN, auditoría de septiembre 2026."""

from pathlib import Path
import os

import matplotlib.pyplot as plt
import numpy as np
import pytest
import scipy.io as sio
import xarray as xr

import geo_malla
import io_batimetria
import io_swan
import io_swan_nonst
import productos_swan
import swan_builder
import swan_runner
import video_swan


MALLA = {"xpc": 600000, "ypc": 5800000, "xlenc": 4000, "ylenc": 4000,
         "mxc": 2, "myc": 2}
BORDE = [{"lado": "W", "hs": 2, "per": 10, "dir": 270, "dd": 20}]


def _par(carpeta, temporal=False, nido_fino=False):
    nido = {**MALLA, "xpc": 601000, "ypc": 5801000, "xlenc": 1000, "ylenc": 1000}
    if nido_fino:
        nido.update(mxc=4, myc=4)
    archivos = swan_builder.escribir_par_anidado(
        carpeta, "padre", "nido", MALLA, {"archivo": "bg.bot"}, BORDE,
        nido, {"archivo": "bn.bot"}, salidas=("Hs", "Dir"))
    for ruta, malla, valor, bot in zip(archivos, (MALLA, nido), (2., 1.), ("bg.bot", "bn.bot")):
        forma = (malla["myc"] + 1, malla["mxc"] + 1)
        np.savetxt(carpeta / bot, np.full(forma, 10 * valor))
        texto = ruta.read_text(encoding="utf-8")
        for var in ("Hs", "Dir"):
            nombre = f"{ruta.stem}_{var}"
            campo = np.full(forma, valor if var == "Hs" else 0.)
            if temporal:
                texto = texto.replace(f"{nombre}.txt", f"{nombre}.mat")
                prefijo = "Hsig" if var == "Hs" else "Dir"
                sio.savemat(carpeta / f"{nombre}.mat", {
                    f"{prefijo}_20260101_000000": campo,
                    f"{prefijo}_20260101_010000": campo * 2,
                })
            else:
                np.savetxt(carpeta / f"{nombre}.txt", campo)
        ruta.write_text(texto, encoding="utf-8")
    return archivos


def test_par_anidado_no_sobrescribe_salidas(tmp_path):
    grande, nido = _par(tmp_path)
    assert set(io_swan._mapa_salidas([grande])).isdisjoint(io_swan._mapa_salidas([nido]))


@pytest.mark.parametrize("temporal", [False, True])
@pytest.mark.parametrize("nido_fino", [False, True])
def test_nesting_absoluto_y_campos_del_mismo_tamano(tmp_path, temporal, nido_fino):
    _par(tmp_path, temporal=temporal, nido_fino=nido_fino)
    cargar = io_swan_nonst.cargar_corrida_nonst if temporal else io_swan.cargar_corrida
    dominios = cargar(tmp_path)["dominios"]
    padre, nido = dominios["large"], dominios["n1"]
    assert float(padre.x[0]) == 600000
    assert float(nido.x[0]) == 601000
    assert float(nido.y[0]) == 5801000
    assert float(padre.Hs.min()) == 2
    assert float(nido.Hs.min()) == 1
    assert float(padre.depth.min()) == 20
    assert float(nido.depth.min()) == 10
    assert nido.Dir.attrs["convencion"] == "nautica"


def test_builder_rechaza_mismo_nombre_de_caso(tmp_path):
    with pytest.raises(ValueError, match="nombres distintos"):
        swan_builder.escribir_par_anidado(
            tmp_path, "Caso", "caso", MALLA, {"archivo": "b.bot"}, BORDE,
            MALLA, {"archivo": "n.bot"})
    assert not list(tmp_path.glob("*.swn"))


def test_cgrid_regular_con_continuacion(tmp_path):
    ruta = tmp_path / "ejemplo.swn"
    ruta.write_text("CGRID REGULAR 0 0 0 &\n 1000 2000 10 20 CIRCLE 36 .04 1\n")
    geo = io_swan._leer_cgrid(ruta)
    assert (geo["nx"], geo["ny"], geo["dx"], geo["dy"]) == (11, 21, 100, 100)


@pytest.mark.parametrize("texto, mensaje", [
    ("CGRID 0 0 30 1000 1000 10 10", "rotadas"),
    ("COORD SPHERICAL\nCGRID -73 -37 0 1 1 10 10", "esféricas"),
    ("CGRID 0 0 0 -1000 1000 10 10", "positivas"),
])
def test_geometrias_no_admitidas_fallan_con_mensaje(tmp_path, texto, mensaje):
    ruta = tmp_path / "caso.swn"
    ruta.write_text(texto)
    with pytest.raises(ValueError, match=mensaje):
        io_swan._leer_cgrid(ruta)


def test_vectores_nauticos_son_propagacion():
    u, v = productos_swan._vectores_direccion(np.array([0, 90, 180, 270]), "nautica")
    np.testing.assert_allclose(u, [0, -1, 0, 1], atol=1e-12)
    np.testing.assert_allclose(v, [-1, 0, 1, 0], atol=1e-12)
    np.testing.assert_allclose(video_swan._componentes_dir(np.array([0, 90])),
                               ([1, 0], [0, 1]), atol=1e-12)


def test_raster_fuera_de_cobertura_no_inventa_fondo(tmp_path):
    raster = xr.Dataset({"elevation": (("lat", "lon"), np.full((2, 2), -30.))},
                        coords={"lat": [0, 1], "lon": [0, 1]})
    with pytest.raises(ValueError, match="no cubre toda la malla"):
        io_batimetria.generar_bot(MALLA, "18S", tmp_path, raster=raster)
    assert not (tmp_path / "bati.bot").exists()


def test_malla_no_finita_no_llega_a_asignar_memoria():
    with pytest.raises(ValueError, match="finitos"):
        geo_malla.malla_desde_latlon(-37, -73, float("inf"), 5, 100)


def test_runner_codigo_no_cero_no_es_exito(tmp_path, monkeypatch):
    class Proceso:
        stdout = iter(())
        returncode = 2

        def wait(self):
            (tmp_path / "norm_end").write_text("")

    monkeypatch.setattr(swan_runner.shutil, "which", lambda _: "swanrun")
    monkeypatch.setattr(swan_runner.subprocess, "Popen", lambda *a, **k: Proceso())
    assert swan_runner.correr_caso(tmp_path, "caso") is False


def test_runner_no_ejecuta_nido_tras_fallo(tmp_path, monkeypatch):
    _par(tmp_path)
    corridos = []
    monkeypatch.setattr(swan_runner, "swan_disponible", lambda: True)
    monkeypatch.setattr(swan_runner, "correr_caso", lambda carpeta, caso, **kw:
                        (corridos.append(caso) or False))
    assert swan_runner.correr_swan(tmp_path)[0] is False
    assert corridos == ["padre"]


def test_fallback_gif_actualiza_extension_y_cierra_figura(tmp_path, monkeypatch):
    class Animacion:
        def save(self, salida, **kw):
            self.salida = salida

    monkeypatch.setattr(video_swan, "_writer", lambda *a: (object(), ".gif"))
    fig = plt.figure()
    anim = Animacion()
    ruta = video_swan._guardar(anim, fig, tmp_path / "video.mp4", "mp4", 12, "video")
    assert ruta.suffix == ".gif"
    assert not plt.fignum_exists(fig.number)


def test_error_writer_cierra_figura(tmp_path, monkeypatch):
    class Animacion:
        def save(self, *a, **kw):
            raise OSError("disco lleno")

    monkeypatch.setattr(video_swan, "_writer", lambda *a: (object(), ".gif"))
    fig = plt.figure()
    with pytest.raises(OSError, match="disco lleno"):
        video_swan._guardar(Animacion(), fig, tmp_path / "video", "gif", 12, "video")
    assert not plt.fignum_exists(fig.number)


@pytest.mark.parametrize("temporal", [False, True])
@pytest.mark.skipif(os.environ.get("TABLERO_PROBAR_SWAN") != "1",
                    reason="Requiere activar SWAN real; usa exclusivamente datos sintéticos temporales.")
def test_integracion_swan_real_par_anidado(tmp_path, temporal):
    grande = {**MALLA, "mxc": 6, "myc": 6, "mdc": 36, "msc": 12}
    nido = {**grande, "xpc": 601000, "ypc": 5801000, "xlenc": 2000, "ylenc": 2000}
    for nombre in ("bg.bot", "bn.bot"):
        np.savetxt(tmp_path / nombre, np.full((7, 7), 20.))
    swan_builder.escribir_par_anidado(
        tmp_path, "padre", "nido", grande, {"archivo": "bg.bot"}, BORDE,
        nido, {"archivo": "bn.bot"}, salidas=("Hs", "Dir"),
        estacionario=not temporal,
        tiempo={"inicio": "20260101.000000", "fin": "20260101.000200", "paso": "1 MIN"})
    mensajes = []
    ok, archivos = swan_runner.correr_swan(tmp_path, log=mensajes.append)
    assert ok, "\n".join(mensajes)
    ext = "mat" if temporal else "txt"
    assert {f"padre_Hs.{ext}", f"nido_Hs.{ext}"} <= set(archivos)
    cargar = io_swan_nonst.cargar_corrida_nonst if temporal else io_swan.cargar_corrida
    corrida = cargar(tmp_path)
    assert set(corrida["dominios"]) == {"large", "n1"}
    assert all(np.isfinite(ds.Hs).any() for ds in corrida["dominios"].values())
    assert float(corrida["dominios"]["n1"].x[0]) == 601000
    if temporal:
        assert corrida["dominios"]["large"].sizes["time"] == 3


def test_gif_extenso_se_rechaza_antes_de_guardar(tmp_path, monkeypatch):
    monkeypatch.setattr(video_swan, "_writer", lambda *a: (object(), ".gif"))
    fig = plt.figure(figsize=(12.5, 7.6))
    with pytest.raises(ValueError, match="512 MiB"):
        video_swan._guardar(None, fig, tmp_path / "video", "gif", 12, "video", n_frames=168)
    assert not plt.fignum_exists(fig.number)


def test_builder_temporal_incluye_modo_matrices_y_paso():
    texto = swan_builder.construir_swn(
        "temporal", MALLA, {"archivo": "b.bot"}, BORDE, estacionario=False,
        tiempo={"inicio": "20260101.000000", "fin": "20260101.002000", "paso": "10 MIN"})
    assert "MODE NONSTATIONARY" in texto
    assert "'Hs.mat' HS OUT 20260101.000000 10 MIN" in texto
    assert "COMPUTE NONSTAT 20260101.000000 10 MIN 20260101.002000" in texto


def test_builder_temporal_rechaza_fechas_invertidas():
    with pytest.raises(ValueError, match="ordenados"):
        swan_builder.construir_swn(
            "temporal", MALLA, {"archivo": "b.bot"}, BORDE, estacionario=False,
            tiempo={"inicio": "20260102.000000", "fin": "20260101.000000", "paso": "10 MIN"})


def test_casos_antiguos_con_salidas_colisionadas_se_detectan(tmp_path):
    rutas = [tmp_path / "padre.swn", tmp_path / "nido.swn"]
    for ruta in rutas:
        ruta.write_text("BLOCK 'COMPGRID' NOHEADER 'Hs.txt' HS\n")
    with pytest.raises(ValueError, match="pudieron sobrescribirse"):
        io_swan._mapa_salidas(rutas)


def test_cantidades_medias_no_se_confunden_con_peak_y_setup(tmp_path):
    ruta = tmp_path / "caso.swn"
    ruta.write_text("BLOCK 'COMPGRID' NOHEADER 'periodo.txt' TM01\n"
                    "BLOCK 'COMPGRID' NOHEADER 'nivel.txt' WATLEV\n")
    assert io_swan._mapa_salidas([ruta]) == {"periodo.txt": "Tm01", "nivel.txt": "WaterLevel"}


def test_metadatos_borde_provienen_del_comando_y_no_de_comentario_viejo(tmp_path):
    ruta = tmp_path / "caso.swn"
    ruta.write_text("$ Hs=9.0 Tp=18 Dp=100\nBOUN SIDE W CCW CON PAR 2 10 270 20\n")
    assert io_swan._meta_condicion(ruta) == {"Hs_borde": 2, "Tp_borde": 10, "Dp_borde": 270}


def test_descarga_raster_fallback_noaa_conserva_procedencia(tmp_path, monkeypatch):
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        if len(llamadas) == 1:
            raise RuntimeError("timeout de CoastWatch")
        return xr.Dataset()

    monkeypatch.setattr(io_batimetria, "_descargar_raster_url", descargar)
    raster = io_batimetria.descargar_raster(-37.1, -37, -73.2, -73.1, tmp_path / "bati.nc")
    assert len(llamadas) == 2
    assert llamadas[1].startswith(io_batimetria._BASE_ERDDAP_RESPALDO)
    assert raster.attrs["fuente_descarga"] == llamadas[1]


@pytest.mark.parametrize("temporal", [False, True])
def test_espectros_con_varios_puntos_no_se_confunden(tmp_path, temporal):
    ruta = tmp_path / "spectro.txt"
    ruta.write_text("SWAN 1\nLOCATIONS\n2\n0 0\n1 1\n")
    lector = io_swan_nonst.leer_espectro_temporal if temporal else io_swan.leer_espectro_swan
    with pytest.raises(ValueError, match="un punto"):
        lector(ruta)


def test_espectro_ya_en_radianes_no_se_convierte_dos_veces(tmp_path):
    ruta = tmp_path / "spectro.txt"
    ruta.write_text("SWAN 1\nAFREQ\n1\n0.1\nNDIR\n2\n0\n180\n"
                    "QUANT\n1\nVaDens\nm2/Hz/rad\n-99 exception value\n"
                    "FACTOR\n1\n2 3\n")
    espectro = io_swan.leer_espectro_swan(ruta)
    np.testing.assert_array_equal(espectro.Efth, [[2, 3]])
    assert espectro.dir.attrs["convencion"] == "nautica"
