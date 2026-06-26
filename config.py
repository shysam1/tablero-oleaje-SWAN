"""
Configuración persistente mínima de la app (preferencias entre sesiones).

Guarda un diccionario simple en `config.json` junto al código: por ahora, las
últimas carpetas usadas, para que los diálogos de archivo abran donde quedaste.
Tolerante a fallos: si el archivo no existe o está corrupto, devuelve vacío.
"""

import json
from pathlib import Path

_RUTA = Path(__file__).parent / "config.json"


def cargar():
    """Devuelve el dict de configuración (vacío si no hay o está dañado)."""
    try:
        return json.loads(_RUTA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def obtener(clave, defecto=None):
    return cargar().get(clave, defecto)


def guardar(clave, valor):
    """Fija una clave y persiste. Silencioso si no se puede escribir."""
    datos = cargar()
    datos[clave] = valor
    try:
        _RUTA.write_text(json.dumps(datos, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    except Exception:
        pass
