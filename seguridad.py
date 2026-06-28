"""
Utilidades de saneamiento de rutas y nombres de archivo.

Centraliza reglas compartidas entre la GUI web, tkinter y los generadores SWAN
para evitar path traversal, nombres de caso inválidos y rutas fuera de base.
"""

import math
import re
from pathlib import Path
from urllib.parse import urlparse

# Lista blanca para nombres de caso SWAN: sin espacios (swanrun.bat parte ahí).
_NOMBRE_CASO_OK = re.compile(r"^[A-Za-z0-9._-]+$")


def sanitizar_segmento(nombre, etiqueta="nombre"):
    """
    Devuelve un segmento de ruta seguro (sin directorios ni separadores).
    Lanza ValueError si el resultado queda vacío o es '.' / '..'.
    """
    if nombre is None:
        raise ValueError(f"{etiqueta} vacío.")
    seg = Path(str(nombre)).name.strip()
    if not seg or seg in (".", ".."):
        raise ValueError(f"{etiqueta} no válido: {nombre!r}.")
    if seg != str(nombre).strip().replace("\\", "/").split("/")[-1]:
        raise ValueError(f"{etiqueta} no puede contener rutas: {nombre!r}.")
    return seg


def sanitizar_nombre_caso(nombre):
    """Nombre de caso SWAN (stem del .swn): whitelist estricta, sin espacios."""
    seg = sanitizar_segmento(nombre, "Nombre de caso")
    if not _NOMBRE_CASO_OK.match(seg):
        raise ValueError(
            f"Nombre de caso SWAN no válido: {seg!r}. Usa letras, números, "
            "punto, guion o guion bajo (sin espacios).")
    return seg


def sanitizar_nombre_fuente(nombre):
    """Identificador de carpeta bajo salidas/ (stem de archivo o etiqueta ERA5)."""
    raw = str(nombre).strip().replace("\\", "/")
    if "/" in raw or any(p == ".." for p in Path(raw).parts):
        raise ValueError(f"Nombre de fuente no válido: {nombre!r}.")
    return sanitizar_segmento(nombre, "Nombre de fuente")


def es_finito_positivo(val):
    """True si `val` es un número finito estrictamente mayor que cero."""
    if val is None:
        return False
    try:
        x = float(val)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and x > 0


def es_finito_en_rango(val, vmin=0.0, vmax=360.0):
    """True si `val` es finito y cumple vmin <= val <= vmax."""
    if val is None:
        return False
    try:
        x = float(val)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and vmin <= x <= vmax


_CDS_HOSTS_PERMITIDOS = frozenset({
    "cds.climate.copernicus.eu",
    "cds-beta.climate.copernicus.eu",
})


def validar_url_cds(url):
    """
    Acepta solo HTTPS hacia hosts Copernicus CDS conocidos.
    Devuelve la URL normalizada (sin barra final).
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("Indica la URL del CDS.")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("La URL del CDS debe usar https://.")
    host = (parsed.hostname or "").lower()
    if host not in _CDS_HOSTS_PERMITIDOS:
        raise ValueError(
            f"Host CDS no permitido: {host!r}. "
            "Usa https://cds.climate.copernicus.eu/api")
    return url


def confina(base, ruta):
    """
    Resuelve `ruta` y comprueba que quede dentro de `base` (ambos absolutos).
    Devuelve la ruta resuelta o lanza ValueError.
    """
    base = Path(base).resolve()
    dest = Path(ruta).resolve()
    try:
        dest.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Ruta fuera de la carpeta permitida: {ruta}") from exc
    return dest


def ruta_en_base(base, *partes):
    """Une partes bajo `base` y verifica que el resultado siga confinado."""
    base = Path(base)
    dest = base
    for p in partes:
        dest = dest / sanitizar_segmento(p, "componente de ruta")
    return confina(base.resolve(), dest)


def escapar_comilla_swan(texto):
    """Escapa comillas simples para literales entre comillas en archivos SWAN."""
    return str(texto).replace("'", "''")


def _bases_usuario():
    """Directorios raíz donde se permiten rutas de la app (escritura/lectura vía API)."""
    bases = [Path.home().resolve()]
    try:
        from rutas import RAIZ_SALIDAS
        bases.append(RAIZ_SALIDAS.resolve())
    except ImportError:
        pass
    # Evitar duplicados si salidas/ está bajo home.
    vistos = set()
    unicas = []
    for b in bases:
        s = str(b)
        if s not in vistos:
            vistos.add(s)
            unicas.append(b)
    return unicas


def confina_usuario(ruta, etiqueta="ruta", debe_existir=False):
    """
    Resuelve `ruta` y comprueba que quede bajo el home del usuario o salidas/.
    Lanza ValueError si escapa o (opcionalmente) no existe.
    """
    if ruta is None or not str(ruta).strip():
        raise ValueError(f"{etiqueta} vacío.")
    dest = Path(ruta).expanduser().resolve()
    if debe_existir and not dest.exists():
        raise ValueError(f"{etiqueta} no existe: {ruta}")
    for base in _bases_usuario():
        try:
            dest.relative_to(base)
            return dest
        except ValueError:
            continue
    raise ValueError(
        f"{etiqueta} fuera de las carpetas permitidas del usuario: {ruta}")


def referencia_swan_segura(carpeta, ref):
    """
    Resuelve una referencia de READINP relativa a `carpeta` sin salir de ella.
    Devuelve Path resuelto o None si la referencia escapa o no existe.
    """
    carpeta = Path(carpeta).resolve()
    ref = str(ref).strip()
    if not ref or ref.startswith(("/", "\\")) or ":" in ref[:3]:
        return None
    try:
        dest = confina(carpeta, (carpeta / ref).resolve())
    except ValueError:
        return None
    return dest if dest.exists() else None
