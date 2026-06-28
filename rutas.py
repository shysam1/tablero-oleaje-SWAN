"""
Ubicación de las salidas de la herramienta.

Todos los productos (tableros de curvas, tableros de mapas SWAN y videos) se
guardan dentro de la propia herramienta, en `salidas/<fuente>/`, con una
subcarpeta por cada archivo o corrida procesada. Así el código queda limpio y
cada resultado queda agrupado con los de su misma fuente.
"""

from pathlib import Path

import seguridad

# Raíz de las salidas, junto al código de la herramienta.
RAIZ_SALIDAS = Path(__file__).parent / "salidas"


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
