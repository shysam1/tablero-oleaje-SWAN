"""
Ejecuta corridas SWAN desde la app (el "paso previo" a graficar).

Toma una carpeta con un caso SWAN ya armado (uno o varios `.swn` + batimetría
`.bot` + condiciones de borde) y lo corre con `swanrun`, el script que trae la
instalación de SWAN. Deja las salidas BLOCK (`.txt`/`.mat`) en la misma carpeta,
listas para el flujo de tableros/videos.

Maneja el caso anidado: corre primero los dominios que alimentan un nesting y
después los anidados (identificados por BOU NEST / BOUN NEST), que dependen del
archivo de nesting que el dominio grande genera (NESTOUT). Reporta el avance
línea a línea para mostrarlo en la GUI.
"""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

import prioridad

# Caracteres permitidos en el nombre de un caso SWAN (stem del .swn). Es una
# lista blanca deliberadamente estrecha: letras, números, espacio y unos pocos
# separadores. Cualquier otro carácter (comillas, &, |, >, etc.) se rechaza para
# que el nombre no pueda inyectar comandos al lanzar el proceso.
_NOMBRE_CASO_OK = re.compile(r"^[A-Za-z0-9 ._-]+$")


def swan_disponible():
    """True si `swanrun`/`swan.exe` está accesible en el PATH."""
    return shutil.which("swanrun") is not None or shutil.which("swan") is not None


def _validar_nombre_caso(caso):
    """
    Comprueba que el nombre del caso sea seguro para pasarlo al proceso de SWAN.
    Lanza ValueError si contiene caracteres fuera de la lista blanca (defensa
    contra inyección de comandos a través del nombre del .swn).
    """
    if not caso or not _NOMBRE_CASO_OK.match(caso):
        raise ValueError(
            f"Nombre de caso SWAN no válido: {caso!r}. Usa solo letras, números, "
            "espacios, guiones, guiones bajos y puntos.")


def _es_nido(ruta_swn):
    """True si el .swn toma su contorno de un nesting (BOU NEST / BOUN NEST)."""
    for linea in Path(ruta_swn).read_text(encoding="utf-8").splitlines():
        s = linea.strip()
        if s.startswith("$"):
            continue
        toks = s.upper().split()
        if len(toks) >= 2 and toks[0] in ("BOU", "BOUN") and toks[1] == "NEST":
            return True
    return False


def casos_ordenados(carpeta):
    """
    Nombres de caso (.swn sin extensión) en orden de ejecución: los dominios que
    alimentan un nesting primero, los anidados (BOU NEST) después.
    """
    swns = sorted(Path(carpeta).glob("*.swn"))

    def clave(s):
        try:
            return (_es_nido(s), s.name)
        except Exception:
            return (True, s.name)        # ilegible: al final

    return [s.stem for s in sorted(swns, key=clave)]


def _refs_input(ruta_swn):
    """
    Archivos de entrada EXTERNOS referenciados por el .swn (READINP: batimetría,
    viento, nivel). No incluye el nesting (BOUNDNEST), que lo genera el dominio
    grande durante la corrida y no existe de antemano.
    """
    import re
    refs = []
    for linea in Path(ruta_swn).read_text(encoding="utf-8").splitlines():
        s = linea.strip()
        if s.startswith("$"):
            continue
        clave = s.split()[0].upper() if s.split() else ""
        if clave in ("READINP", "READ"):
            refs.extend(re.findall(r"'([^']*)'", s))
    return refs


def verificar_inputs(carpeta, caso):
    """
    Lista de archivos de entrada externos que el .swn referencia y NO existen en
    la carpeta. Vacía = todo en orden. (El nesting que produce el dominio grande
    no cuenta: se genera durante la corrida.)
    """
    carpeta = Path(carpeta)
    faltan = []
    for ref in _refs_input(carpeta / f"{caso}.swn"):
        if not (carpeta / ref).exists():
            faltan.append(ref)
    return faltan


def correr_caso(carpeta, caso, log=None, on_proc=None):
    """
    Corre `swanrun <caso>` en la carpeta, transmitiendo la salida por `log`.
    `on_proc(proc)` recibe el proceso recién lanzado (para poder cancelarlo).
    Devuelve True si SWAN terminó normalmente (genera el archivo `norm_end`).
    """
    carpeta = Path(carpeta)
    _validar_nombre_caso(caso)
    if log:
        log(f"=== Corriendo SWAN: {caso} ===")
    # ABOVE_NORMAL se hereda a swan.exe; evita que Windows lo postergue.
    flags = getattr(subprocess, "ABOVE_NORMAL_PRIORITY_CLASS", 0)
    # Sin shell=True: se resuelve el ejecutable de swanrun en el PATH y se pasa el
    # caso como argumento aparte (lista), de modo que no se interpola en una línea
    # de comandos. swanrun suele ser un .bat, que necesita cmd.exe para ejecutarse;
    # como el nombre del caso ya está saneado, no puede inyectar metacaracteres.
    ejecutable = shutil.which("swanrun") or "swanrun"
    if ejecutable.lower().endswith((".bat", ".cmd")):
        comando = ["cmd", "/c", ejecutable, caso]
    else:
        comando = [ejecutable, caso]
    proc = subprocess.Popen(comando, cwd=str(carpeta), shell=False,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, creationflags=flags)
    if on_proc:
        on_proc(proc)
    # El opt-out de EcoQoS no se hereda: hay que aplicarlo a swan.exe en cuanto
    # exista. Un hilo lo espera y lo protege para que minimizar la ventana no
    # baje la frecuencia del núcleo (SWAN es monohilo) y enlentezca la corrida.
    threading.Thread(target=prioridad.proteger_swan, kwargs={"log": log},
                     daemon=True).start()
    for linea in proc.stdout:
        if log:
            log(linea.rstrip())
    proc.wait()

    ok = (carpeta / "norm_end").exists()
    erf = list(carpeta.glob(f"{caso}.erf"))
    if log:
        if ok and not erf:
            log(f"--- {caso}: terminó normalmente ---")
        elif erf:
            log(f"--- {caso}: terminó con errores (ver {erf[0].name}) ---")
        else:
            log(f"--- {caso}: no se encontró 'norm_end' (revisar {caso}.prt) ---")
    return ok


def correr_swan(carpeta, log=None, progreso=None, on_proc=None, cancelado=None):
    """
    Corre la corrida completa de la carpeta (todos los .swn en orden).

    log: callback(str) detalle; progreso: callback(i, n) por caso; on_proc:
    callback(proc) con el proceso en curso (para cancelar); cancelado: callable
    que devuelve True para abortar entre casos. Devuelve (ok_global, salidas).
    Lanza RuntimeError si SWAN no está instalado o faltan inputs.
    """
    carpeta = Path(carpeta)
    if not swan_disponible():
        raise RuntimeError(
            "No se encontró 'swanrun' en el PATH. Instala SWAN o agrégalo al PATH.")

    casos = casos_ordenados(carpeta)
    if not casos:
        raise RuntimeError(f"No hay archivos .swn en {carpeta}")

    # swanrun.bat parte el nombre del caso en el primer espacio; avisar.
    con_espacios = [c for c in casos if " " in c]
    if con_espacios and log:
        log(f"[aviso] Nombres con espacios pueden fallar en swanrun: "
            f"{', '.join(con_espacios)}")

    antes = {p.name for p in carpeta.glob("*.txt")} | \
            {p.name for p in carpeta.glob("*.mat")}

    ok_global = True
    for i, caso in enumerate(casos):
        if cancelado and cancelado():
            if log:
                log("Corrida cancelada por el usuario.")
            break
        if progreso:
            progreso(i, len(casos))
        # Se verifica cada caso justo antes de correrlo: así el nesting que el
        # dominio grande deja para el anidado ya está presente al llegar a éste.
        faltan = verificar_inputs(carpeta, caso)
        if faltan:
            raise RuntimeError(
                f"Al caso '{caso}' le faltan archivos de entrada: "
                f"{', '.join(faltan)}")
        ok_global &= correr_caso(carpeta, caso, log=log, on_proc=on_proc)
    if progreso:
        progreso(len(casos), len(casos))

    despues = {p.name for p in carpeta.glob("*.txt")} | \
              {p.name for p in carpeta.glob("*.mat")}
    nuevas = sorted(despues - antes)
    if log:
        log(f"\nSalidas generadas: {len(nuevas)} archivo(s).")
    return ok_global, nuevas


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    import argparse
    ap = argparse.ArgumentParser(description="Corre una corrida SWAN de una carpeta.")
    ap.add_argument("carpeta", help="Carpeta con el/los .swn del caso")
    args = ap.parse_args()

    print("SWAN disponible:", swan_disponible())
    print("Casos en orden:", casos_ordenados(args.carpeta))
    ok, nuevas = correr_swan(args.carpeta, log=print)
    print("OK:", ok, "| nuevas:", nuevas)
