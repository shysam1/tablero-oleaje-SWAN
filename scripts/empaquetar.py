"""Empaqueta exclusivamente los archivos declarados, sin datos del equipo."""

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def archivos_entrega(proyecto):
    proyecto = Path(proyecto).resolve()
    manifiesto = proyecto / "scripts" / "archivos_entrega.txt"
    archivos = []
    for linea in manifiesto.read_text(encoding="utf-8").splitlines():
        relativa = linea.strip()
        if not relativa or relativa.startswith("#"):
            continue
        ruta = PurePosixPath(relativa)
        if ruta.is_absolute() or ".." in ruta.parts or "\\" in relativa or ":" in relativa:
            raise ValueError(f"Ruta insegura en el manifiesto: {relativa}")
        origen = (proyecto / relativa).resolve()
        if not origen.is_relative_to(proyecto) or not origen.is_file():
            raise FileNotFoundError(f"Falta un archivo de la entrega: {relativa}")
        if relativa in archivos:
            raise ValueError(f"Archivo duplicado en el manifiesto: {relativa}")
        archivos.append(relativa)
    if not archivos:
        raise ValueError("El manifiesto de entrega está vacío.")
    return archivos


def copiar_entrega(proyecto, destino):
    proyecto, destino = Path(proyecto), Path(destino)
    archivos = archivos_entrega(proyecto)
    # Un destino vacío impide heredar residuos de una entrega anterior.
    if destino.exists() and any(destino.iterdir()):
        raise ValueError(f"La carpeta de destino debe estar vacía: {destino}")
    destino.mkdir(parents=True, exist_ok=True)
    for relativa in archivos:
        archivo = destino / relativa
        archivo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(proyecto / relativa, archivo)
        if relativa.endswith((".sh", ".command")):
            archivo.write_bytes(archivo.read_bytes().replace(b"\r\n", b"\n"))
            archivo.chmod(0o755)
    return archivos


def crear_zip(proyecto, destino):
    proyecto, destino = Path(proyecto), Path(destino)
    archivos = archivos_entrega(proyecto)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # La entrega previa solo se reemplaza una vez terminado el ZIP completo.
    with tempfile.TemporaryDirectory(prefix="tablero-entrega-", dir=destino.parent) as temporal:
        parcial = Path(temporal) / "entrega.zip"
        with zipfile.ZipFile(parcial, "w", compression=zipfile.ZIP_DEFLATED) as salida:
            for relativa in archivos:
                contenido = (proyecto / relativa).read_bytes()
                info = zipfile.ZipInfo(f"Tablero Oleaje/{relativa}")
                info.create_system = 3
                ejecutable = relativa.endswith((".sh", ".command"))
                if ejecutable:
                    contenido = contenido.replace(b"\r\n", b"\n")
                info.external_attr = ((0o100755 if ejecutable else 0o100644) << 16)
                info.compress_type = zipfile.ZIP_DEFLATED
                salida.writestr(info, contenido)
        parcial.replace(destino)
    return archivos


def crear_lista_inno(proyecto, destino):
    archivos = archivos_entrega(proyecto)
    lineas = ["; Generado desde scripts/archivos_entrega.txt; no editar manualmente."]
    for relativa in archivos:
        ruta = PurePosixPath(relativa)
        origen = relativa.replace("/", "\\")
        carpeta = str(ruta.parent).replace("/", "\\")
        destino_inno = "{app}" if carpeta == "." else "{app}\\" + carpeta
        lineas.append(f'Source: "{{#SourceRoot}}\\{origen}"; DestDir: "{destino_inno}"; Flags: ignoreversion')
    Path(destino).write_text("\n".join(lineas) + "\n", encoding="utf-8-sig")
    return archivos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proyecto", type=Path, default=Path(__file__).resolve().parent.parent)
    destinos = parser.add_mutually_exclusive_group(required=True)
    destinos.add_argument("--zip", type=Path)
    destinos.add_argument("--destino", type=Path)
    destinos.add_argument("--inno", type=Path)
    args = parser.parse_args()
    try:
        if args.zip:
            archivos = crear_zip(args.proyecto, args.zip)
        elif args.inno:
            archivos = crear_lista_inno(args.proyecto, args.inno)
        else:
            archivos = copiar_entrega(args.proyecto, args.destino)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"No se pudo empaquetar: {exc}\n")
    print(f"Entrega verificada: {len(archivos)} archivos.")


if __name__ == "__main__":
    main()
