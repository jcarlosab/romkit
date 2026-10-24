"""The sole production boundary around pycdlib; exposes normalized logical paths."""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tempfile
import hashlib
from typing import Any

import pycdlib

from romkit_core.errors import PlatformError
from romkit_core.tasks import ProgressCallback, report


def normalize_iso_path(raw: str) -> str:
    if not isinstance(raw, str) or "\\" in raw or ":" in raw or "\x00" in raw:
        raise PlatformError(f"Nombre ISO no seguro: {raw!r}")
    parts = raw.lstrip("/").split("/")
    result = []
    for part in parts:
        if part in ("", ".", ".."):
            raise PlatformError(f"Ruta ISO no segura: {raw!r}")
        part = re.sub(r";\d+$", "", part).rstrip(".")
        if not part or part.endswith(" ") or any(c in part for c in '<>"|?*'):
            raise PlatformError(f"Nombre ISO no seguro: {raw!r}")
        if part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise PlatformError(f"Nombre reservado: {raw!r}")
        result.append(part)
    return "/".join(result)


@dataclass(frozen=True)
class IsoEntry:
    logical_path: str
    iso_path: str
    size_bytes: int
    is_directory: bool = False


@dataclass
class IsoImage:
    path: Path
    _handle: Any

    def close(self):
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Iso9660Reader:
    def patch_copy(self, source: Path, destination: Path, replacements: dict[str, Path], *, progress=None, expected_sha256=None):
        """Replace equal-size extents without rebuilding or rearranging the ISO."""
        source, destination = Path(source).resolve(strict=True), Path(destination).absolute()
        if destination.exists() or destination.is_symlink() or destination.resolve() == source:
            raise PlatformError("Elige un archivo ISO nuevo; no se sobrescriben imágenes existentes")
        with self.open(source) as image:
            entries = {entry.logical_path: entry for entry in self.walk(image) if not entry.is_directory}
            regions = []
            for logical, path in replacements.items():
                if logical not in entries:
                    raise PlatformError(f"Archivo ausente en la ISO: {logical}")
                entry = entries[logical]
                record = image._handle.get_record(iso_path=entry.iso_path)
                if record.data_continuation is not None or path.stat().st_size != entry.size_bytes:
                    raise PlatformError(f"La sustitución debe conservar el tamaño y un único extent: {logical}")
                offset = record.extent_location() * image._handle.logical_block_size
                if offset + entry.size_bytes > source.stat().st_size:
                    raise PlatformError("El archivo sale de la imagen ISO")
                regions.append((offset, offset + entry.size_bytes, path))
            regions.sort()
            if any(left[1] > right[0] for left, right in zip(regions, regions[1:])):
                raise PlatformError("Los archivos de la ISO se solapan")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".romkit-", suffix=".iso", delete=False) as output:
                temporary = Path(output.name)
                total, completed = source.stat().st_size, 0
                copied_hash = hashlib.sha256()
                with source.open("rb") as original:
                    while block := original.read(1024 * 1024):
                        report(progress, completed, total, "Copiando imagen original")
                        output.write(block)
                        copied_hash.update(block)
                        completed += len(block)
                if expected_sha256 is not None and copied_hash.hexdigest() != expected_sha256:
                    raise PlatformError("La imagen cambió mientras se copiaba; no se ha generado la ISO")
                for offset, end, path in regions:
                    output.seek(offset)
                    with path.open("rb") as replacement:
                        while block := replacement.read(1024 * 1024):
                            report(progress, offset, total, "Insertando archivos reconstruidos")
                            output.write(block)
                            offset += len(block)
                output.flush()
                os.fsync(output.fileno())
            report(progress, total, total, "Verificando imagen nueva")
            with self.open(temporary) as image:
                entries = {entry.logical_path: entry for entry in self.walk(image) if not entry.is_directory}
                for logical, path in replacements.items():
                    with path.open("rb") as expected:
                        for block in self.read_chunks(image, entries[logical]):
                            report(progress, total, total, "Verificando archivos insertados")
                            if block != expected.read(len(block)):
                                raise PlatformError("La verificación de la ISO reconstruida ha fallado")
            # Exclusive publication: an existing output is never overwritten.
            os.link(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return destination

    def open(self, path: str | Path) -> IsoImage:
        path = Path(path).resolve(strict=True)
        iso = pycdlib.PyCdlib()
        try:
            iso.open(str(path))
        except (pycdlib.pycdlibexception.PyCdlibException, OSError) as exc:
            raise PlatformError(f"No se puede leer la imagen ISO9660: {path.name}") from exc
        return IsoImage(path, iso)

    def walk(self, image: IsoImage):
        if image._handle is None:
            raise PlatformError("La imagen ISO está cerrada")
        entries, seen = [], set()
        try:
            for parent, directories, files in image._handle.walk(iso_path="/"):
                for name, directory in [(name, True) for name in directories] + [(name, False) for name in files]:
                    raw = parent.rstrip("/") + "/" + name
                    logical = normalize_iso_path(raw)
                    if logical.casefold() in seen:
                        raise PlatformError(f"Rutas ISO duplicadas tras normalizar: {logical}")
                    seen.add(logical.casefold())
                    size = 0 if directory else image._handle.get_record(iso_path=raw).data_length
                    entries.append(IsoEntry(logical, raw, size, directory))
        except pycdlib.pycdlibexception.PyCdlibException as exc:
            raise PlatformError("Estructura ISO9660 inválida") from exc
        return iter(sorted(entries, key=lambda entry: entry.logical_path))

    def destination_path(self, destination: Path, entry: IsoEntry) -> Path:
        root = Path(destination).resolve()
        logical = normalize_iso_path(entry.logical_path)
        target = (root / logical).resolve()
        if not target.is_relative_to(root):
            raise PlatformError("El destino de extracción sale del directorio permitido")
        return target

    def read_chunks(self, image: IsoImage, entry: IsoEntry, block_size: int = 1024 * 1024):
        if image._handle is None or entry.is_directory:
            raise PlatformError("El recurso ISO no es un archivo abierto")
        with image._handle.open_file_from_iso(iso_path=entry.iso_path) as stream:
            while block := stream.read(block_size):
                yield block

    def extract_file(self, image: IsoImage, entry: IsoEntry, destination: Path) -> None:
        target = self.destination_path(destination, entry)
        if target == image.path or (target.exists() and os.path.samefile(target, image.path)):
            raise PlatformError("No se puede sobrescribir la imagen original")
        if entry.is_directory:
            target.mkdir(parents=True, exist_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with target.open("xb") as output:
                created = True
                image._handle.get_file_from_iso_fp(output, iso_path=entry.iso_path)
            if target.stat().st_size != entry.size_bytes:
                raise PlatformError(f"Extracción incompleta: {entry.logical_path}")
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise

    def extract_all(self, image: IsoImage, destination: Path, *, progress: ProgressCallback | None = None) -> None:
        entries = list(self.walk(image))
        # Validate every name and existing file before the first output.
        for entry in entries:
            target = self.destination_path(destination, entry)
            if not entry.is_directory and target.exists():
                raise PlatformError(f"El archivo destino ya existe: {entry.logical_path}")
        for index, entry in enumerate(entries):
            report(progress, index, len(entries), entry.logical_path)
            self.extract_file(image, entry, destination)
        report(progress, len(entries), len(entries), "Extracción terminada")
