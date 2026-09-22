"""Regresiones de instalación, entrega y preferencias sin GUI ni credenciales."""

import json
import zipfile
from pathlib import Path

import pytest

import config
import rutas
from scripts import empaquetar, estado_entorno


@pytest.mark.parametrize("contenido", ["[]", "null", '"ruta"', "42", "{invalido"])
def test_config_invalida_se_recupera(monkeypatch, tmp_path, contenido):
    archivo = tmp_path / "config.json"
    archivo.write_text(contenido, encoding="utf-8")
    monkeypatch.setattr(config, "_RUTA", archivo)
    assert config.obtener("carpeta", "defecto") == "defecto"
    config.guardar("carpeta", "nueva")
    assert config.cargar() == {"carpeta": "nueva"}


def test_sonda_escritura_preserva_archivos(tmp_path):
    previo = tmp_path / ".test_escritura"
    previo.write_text("archivo del usuario", encoding="utf-8")
    assert rutas._directorio_escribible(tmp_path)
    assert previo.read_text(encoding="utf-8") == "archivo del usuario"
    assert list(tmp_path.iterdir()) == [previo]


def test_fallback_mac_usa_application_support(monkeypatch):
    monkeypatch.setattr(rutas.sys, "platform", "darwin")
    assert rutas._raiz_datos_usuario() == Path.home() / "Library/Application Support/Tablero de Oleaje"


def test_fallback_windows_sin_localappdata(monkeypatch):
    monkeypatch.setattr(rutas.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert rutas._raiz_datos_usuario() == Path.home() / "AppData/Local/Tablero de Oleaje"


def test_fallback_verifica_salidas_reales(monkeypatch, tmp_path):
    codigo = Path(rutas.__file__).parent
    monkeypatch.setattr(rutas, "_directorio_escribible", lambda d: d != codigo / "salidas")
    monkeypatch.setattr(rutas, "_raiz_datos_usuario", lambda: tmp_path)
    assert rutas._raiz_salidas() == tmp_path / "salidas"


def test_marcador_incompleto_o_requisitos_cambiados(monkeypatch, tmp_path):
    requisitos = tmp_path / "requirements.txt"
    requisitos.write_text("pip>=20\n", encoding="utf-8")
    marcador = tmp_path / ".tablero-listo.json"
    monkeypatch.setattr(estado_entorno, "MODULOS", {"pip": "pip"})
    assert not estado_entorno.entorno_listo(requisitos, marcador)
    estado_entorno.registrar_entorno(requisitos, marcador)
    assert estado_entorno.entorno_listo(requisitos, marcador)
    requisitos.write_text("pip>=21\n", encoding="utf-8")
    assert not estado_entorno.entorno_listo(requisitos, marcador)


def test_marcador_detecta_dependencia_quitada(monkeypatch, tmp_path):
    requisitos, marcador = tmp_path / "requirements.txt", tmp_path / "listo.json"
    requisitos.write_text("pip\n", encoding="utf-8")
    monkeypatch.setattr(estado_entorno, "MODULOS", {"pip": "pip"})
    estado_entorno.registrar_entorno(requisitos, marcador)
    monkeypatch.setattr(estado_entorno, "MODULOS", {"paquete-inexistente-tablero-auditoria": "no_existe"})
    assert not estado_entorno.entorno_listo(requisitos, marcador)


def test_marcador_invalida_lock_windows_modificado(monkeypatch, tmp_path):
    requisitos, marcador = tmp_path / "requirements.txt", tmp_path / "listo.json"
    requisitos.write_text("pip\n", encoding="utf-8")
    lock = tmp_path / "requirements-windows-py313.lock"
    lock.write_text("pip==24\n", encoding="utf-8")
    monkeypatch.setattr(estado_entorno.sys, "platform", "win32")
    monkeypatch.setattr(estado_entorno.sys, "version_info", (3, 13, 0))
    monkeypatch.setattr(estado_entorno, "MODULOS", {"pip": "pip"})
    estado_entorno.registrar_entorno(requisitos, marcador)
    assert estado_entorno.entorno_listo(requisitos, marcador)
    lock.write_text("pip==25\n", encoding="utf-8")
    assert not estado_entorno.entorno_listo(requisitos, marcador)


def test_import_fallido_no_registra_entorno(monkeypatch, tmp_path):
    requisitos, marcador = tmp_path / "requirements.txt", tmp_path / "listo.json"
    requisitos.write_text("pip\n", encoding="utf-8")
    monkeypatch.setattr(estado_entorno, "MODULOS", {"pip": "modulo_inexistente_tablero"})
    with pytest.raises(ImportError):
        estado_entorno.registrar_entorno(requisitos, marcador)
    assert not marcador.exists()


def _proyecto_sintetico(tmp_path):
    proyecto = tmp_path / "proyecto"
    (proyecto / "scripts").mkdir(parents=True)
    (proyecto / "scripts/archivos_entrega.txt").write_text("app_web.py\niniciar_mac.command\n", encoding="utf-8")
    (proyecto / "app_web.py").write_text("print('app')", encoding="utf-8")
    (proyecto / "iniciar_mac.command").write_bytes(b"#!/bin/bash\r\n")
    return proyecto


def test_zip_solo_manifiesto_y_permiso_mac(tmp_path):
    proyecto = _proyecto_sintetico(tmp_path)
    for nombre in (".env", ".cdsapirc", "config.json", "datos.nc"):
        (proyecto / nombre).write_text("dato ficticio que no debe distribuirse", encoding="utf-8")
    (proyecto / ".claude").mkdir()
    (proyecto / ".claude/settings.local.json").write_text("{}", encoding="utf-8")
    archivo = tmp_path / "entrega.zip"
    empaquetar.crear_zip(proyecto, archivo)
    with zipfile.ZipFile(archivo) as entrega:
        assert set(entrega.namelist()) == {"Tablero Oleaje/app_web.py", "Tablero Oleaje/iniciar_mac.command"}
        assert entrega.getinfo("Tablero Oleaje/iniciar_mac.command").external_attr >> 16 & 0o111
        assert entrega.read("Tablero Oleaje/iniciar_mac.command") == b"#!/bin/bash\n"


def test_entrega_incompleta_no_silencia_archivo_faltante(tmp_path):
    proyecto = _proyecto_sintetico(tmp_path)
    (proyecto / "app_web.py").unlink()
    with pytest.raises(FileNotFoundError, match="app_web.py"):
        empaquetar.crear_zip(proyecto, tmp_path / "incompleto.zip")
    assert not (tmp_path / "incompleto.zip").exists()


def test_manifest_no_permite_salir_del_proyecto(tmp_path):
    proyecto = _proyecto_sintetico(tmp_path)
    (proyecto / "scripts/archivos_entrega.txt").write_text("../fuera.txt", encoding="utf-8")
    with pytest.raises(ValueError, match="insegura"):
        empaquetar.archivos_entrega(proyecto)


def test_payload_no_reutiliza_carpeta_con_datos(tmp_path):
    proyecto = _proyecto_sintetico(tmp_path)
    destino = tmp_path / "instalador"
    destino.mkdir()
    (destino / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="vacía"):
        empaquetar.copiar_entrega(proyecto, destino)


def test_lista_inno_sincronizada_con_manifiesto(tmp_path):
    proyecto = Path(__file__).parent
    esperado = tmp_path / "archivos_entrega.iss"
    empaquetar.crear_lista_inno(proyecto, esperado)
    assert esperado.read_bytes() == (proyecto / "installer/windows/archivos_entrega.iss").read_bytes()
