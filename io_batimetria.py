"""
Genera la batimetría (.bot) de un caso SWAN a partir de la malla de cómputo.

Proyecta los nodos de la malla (UTM) a lat/lon, muestrea un raster de batimetría
(descargado de GEBCO/ETOPO por coordenadas, o uno local) e escribe el .bot con la
misma convención que lee io_swan (reshape + flipud). SWAN usa profundidad positiva
hacia abajo, así que depth = -elevation.

La parte de red (descarga) está aislada de la lógica pura, que se testea con
rasters sintéticos sin tocar internet.
"""

import re
from pathlib import Path

import numpy as np
import xarray as xr


def epsg_utm(zona):
    """
    EPSG de una zona UTM: '19S'->32719, '18S'->32718, '19N'->32619.
    Lanza ValueError si la cadena no es una zona válida.
    """
    texto = str(zona).strip().upper()
    m = re.fullmatch(r"(\d{1,2})\s*([NS])", texto)
    if not m:
        raise ValueError(f"Zona UTM inválida: {zona!r} (usa p. ej. '19S').")
    numero = int(m.group(1))
    if not 1 <= numero <= 60:
        raise ValueError(f"Huso UTM fuera de rango: {numero}")
    return (32700 if m.group(2) == "S" else 32600) + numero
