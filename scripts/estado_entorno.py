"""Detecta instalaciones incompletas o requisitos cambiados sin usar la red."""

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import struct
import sys
from pathlib import Path


MODULOS = {
    "numpy": "numpy", "pandas": "pandas", "scipy": "scipy", "xarray": "xarray",
    "netCDF4": "netCDF4", "matplotlib": "matplotlib", "cdsapi": "cdsapi",
    "pyproj": "pyproj", "pywebview": "webview", "scikit-image": "skimage",
    "pillow": "PIL",
}


def firma_entorno(requisitos):
    """Incluye intérprete y versiones instaladas para detectar entornos movidos."""
    if sys.version_info < (3, 11) or struct.calcsize("P") != 8:
        raise RuntimeError("Se requiere Python 3.11 o superior de 64 bits.")
    requisitos = Path(requisitos)
    contenido = requisitos.read_bytes()
    restricciones = requisitos.with_name("requirements-windows-py313.lock")
    if sys.platform == "win32" and sys.version_info[:2] == (3, 13) and restricciones.is_file():
        contenido += restricciones.read_bytes()
    return {
        "requisitos": hashlib.sha256(contenido).hexdigest(),
        "python": str(Path(sys.executable).resolve()),
        "version": list(sys.version_info[:3]),
        "paquetes": {nombre: importlib.metadata.version(nombre) for nombre in MODULOS},
    }


def entorno_listo(requisitos, marcador):
    try:
        return json.loads(Path(marcador).read_text(encoding="utf-8")) == firma_entorno(requisitos)
    except (OSError, ValueError, RuntimeError, importlib.metadata.PackageNotFoundError):
        return False


def registrar_entorno(requisitos, marcador):
    """Solo registra éxito después de cargar todas las dependencias directas."""
    for modulo in MODULOS.values():
        importlib.import_module(modulo)
    firma = firma_entorno(requisitos)
    destino = Path(marcador)
    destino.write_text(json.dumps(firma, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=("comprobar", "registrar"))
    parser.add_argument("requisitos", type=Path)
    parser.add_argument("marcador", type=Path)
    args = parser.parse_args()
    if args.accion == "comprobar":
        return 0 if entorno_listo(args.requisitos, args.marcador) else 1
    try:
        registrar_entorno(args.requisitos, args.marcador)
    except Exception as exc:
        print(f"No se pudo validar el entorno: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
