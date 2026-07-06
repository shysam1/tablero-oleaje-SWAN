"""
Ubicación de las salidas de la herramienta.

Todos los productos (tableros de curvas, tableros de mapas SWAN y videos) se
guardan dentro de la propia herramienta, en `salidas/<fuente>/`, con una
subcarpeta por cada archivo o corrida procesada. Así el código queda limpio y
cada resultado queda agrupado con los de su misma fuente.

Si la carpeta del código no es escribible (p. ej. instalación antigua en
Program Files), las salidas van a la carpeta de datos del usuario.
"""

import os
import sys
from pathlib import Path

import seguridad


def _directorio_escribible(directorio: Path) -> bool:
    """True si se puede crear y borrar un archivo temporal en el directorio."""
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        prueba = directorio / ".test_escritura"
        prueba.write_text("", encoding="utf-8")
        prueba.unlink()
        return True
    except OSError:
        return False


def _raiz_datos_usuario() -> Path:
    """Carpeta de datos del usuario cuando el código no es escribible."""
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "Tablero de Oleaje"
    return Path.home() / ".local" / "share" / "Tablero de Oleaje"


def _raiz_salidas() -> Path:
    """Raíz de salidas: junto al código si es escribible, si no bajo datos de usuario."""
    codigo = Path(__file__).parent
    if _directorio_escribible(codigo):
        return codigo / "salidas"
    return _raiz_datos_usuario() / "salidas"


RAIZ_SALIDAS = _raiz_salidas()


def carpeta_salida(nombre_fuente):
    """
    Devuelve (creándola) la subcarpeta de salidas para una fuente dada.

    nombre_fuente: identificador del origen (stem del archivo de datos o nombre
    de la carpeta de la corrida SWAN).
    """
    seguro = seguridad.sanitizar_nombre_fuente(nombre_fuente)
    destino = RAIZ_SALIDAS / seguro
    destino.mkdir(parents=True, exist_ok=True)
    return destino
