"""
Utilidades multiplataforma del sistema operativo.

Centraliza apertura de archivos/carpetas y otros detalles que difieren entre
Windows, macOS y Linux, para no usar APIs exclusivas (p. ej. os.startfile).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def abrir_archivo(ruta: os.PathLike | str) -> None:
    """Abre un archivo con la aplicación predeterminada del sistema."""
    _abrir_en_sistema(Path(ruta).resolve())


def abrir_carpeta(ruta: os.PathLike | str) -> None:
    """Abre una carpeta en el gestor de archivos del sistema."""
    p = Path(ruta).resolve()
    if p.is_file():
        p = p.parent
    _abrir_en_sistema(p)


def _abrir_en_sistema(ruta: Path) -> None:
    destino = str(ruta)
    if sys.platform == "win32":
        os.startfile(destino)  # noqa: S606 — API nativa de Windows
        return
    if sys.platform == "darwin":
        subprocess.run(["open", destino], check=False)
        return
    subprocess.run(["xdg-open", destino], check=False)
