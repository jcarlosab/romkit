"""Read-only reader for Poka Poka's PSP FAT/BHD/BND and CP932 FMG tables."""
import hashlib
from pathlib import Path
import struct
import zlib

from romkit_core.errors import ValidationError
from romkit_core.models.text_candidate import TextCandidate
from romkit_core.tasks import report

MAX_TABLE_BYTES = 32 * 1024 * 1024


def fmg_candidates(data: bytes, logical_path: str):
    def invalid():
        return ValidationError(f"Tabla FMG inválida: {logical_path}")
    if len(data) < 28 or data[:4] != b"\x00\x00\x01\x00":
        raise invalid()
    size, groups, count, table = (struct.unpack_from("<I", data, offset)[0] for offset in (4, 12, 16, 20))
    if size != len(data) or table != 28 + groups * 12 or table + count * 4 > size:
        raise invalid()
    text_start = table + count * 4
    resource_id = hashlib.sha256(logical_path.encode("utf-8")).hexdigest()
    seen, candidates = set(), []
    for row in range(count):
        offset = struct.unpack_from("<I", data, table + row * 4)[0]
        if offset == 0 or offset in seen:
            continue
        if not text_start <= offset < size:
            raise invalid()
        end = data.find(b"\x00", offset)
        if end < 0:
            raise invalid()
        seen.add(offset)
        try:
            text = data[offset:end].decode("cp932", errors="strict")
        except UnicodeDecodeError as exc:
            raise invalid() from exc
        if not text.strip():
            continue
        candidates.append(TextCandidate(resource_id, logical_path, offset, "cp932", end - offset,
                                        text, b"\x00", 1.0,
                                        ("Tabla FMG indexada", f"Fila {row}", "Contenedor POKAPOKA descomprimido")))
    return candidates


def iter_archive_members(directory: Path, logical_directory: str, *, progress=None, suffixes=None, stem="POKAPOKA", on_error=None):
    directory = Path(directory)
    if not stem or any(char in stem for char in "/\\:"):
        raise ValidationError("Nombre de contenedor inválido")
    fat_path, bhd_path, bnd_path = (directory / f"{stem}.{suffix}" for suffix in ("FAT", "BHD", "BND"))
    if any(path.is_symlink() for path in (fat_path, bhd_path, bnd_path)):
        raise ValidationError("El contenedor POKAPOKA no admite enlaces simbólicos")
    if fat_path.stat().st_size > MAX_TABLE_BYTES or bhd_path.stat().st_size > MAX_TABLE_BYTES:
        raise ValidationError("Índices POKAPOKA demasiado grandes")
    fat, bhd = fat_path.read_bytes(), bhd_path.read_bytes()
    if len(fat) < 36 or len(bhd) < 28 or bhd[:4] != b"LDMU":
        raise ValidationError("Cabecera POKAPOKA inválida")
    version, names = struct.unpack_from("<2I", fat)
    bhd_version, count, archive_size = struct.unpack_from("<3I", bhd, 4)
    if (version != 0x210 or bhd_version != version or names > len(fat)
            or len(bhd) != 28 + count * 40 or archive_size != bnd_path.stat().st_size):
        raise ValidationError("Índices POKAPOKA incompatibles o truncados")
    files, seen_slots, visited = [], set(), set()
    def read_name(name_offset):
        if not names <= name_offset < len(fat):
            raise ValidationError("Nombre FAT fuera de la tabla")
        end = fat.find(b"\x00", name_offset)
        if end < 0:
            raise ValidationError("Nombre FAT sin terminador")
        try:
            name = fat[name_offset:end].decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValidationError("Nombre FAT inválido") from exc
        if any(char in name for char in "/\\:") or name in (".", ".."):
            raise ValidationError("Nombre FAT inválido")
        return name
    pending = [16]
    while pending:
        position = pending.pop()
        if position in visited or not 16 <= position <= names - 20:
            raise ValidationError("Directorio FAT inválido o cíclico")
        visited.add(position)
        _, children, table, child_count, file_count = struct.unpack_from("<5I", fat, position)
        if table + file_count * 8 > names or children + child_count * 20 > names:
            raise ValidationError("Directorio FAT fuera de la tabla")
        for child in range(child_count):
            child_position = children + child * 20
            read_name(struct.unpack_from("<I", fat, child_position)[0])
            pending.append(child_position)
        for entry in range(file_count):
            name_offset, slot = struct.unpack_from("<2I", fat, table + entry * 8)
            if slot >= count or slot in seen_slots:
                raise ValidationError("Entrada FAT inválida")
            seen_slots.add(slot)
            name = read_name(name_offset)
            if suffixes is None or Path(name).suffix.lower() in suffixes:
                files.append((slot, name))
    files.sort()
    with bnd_path.open("rb") as stream:
        for index, (slot, name) in enumerate(files):
            report(progress, index, len(files), f"Leyendo tabla · {name}")
            logical_path = f"{logical_directory}/{stem}.BND.contents/{slot:05d}/{name}"
            file_id, sector, raw_size, compressed_size = struct.unpack_from("<4I", bhd, 28 + slot * 40)
            stored_size, offset = compressed_size or raw_size, sector * 1024
            if raw_size > MAX_TABLE_BYTES or stored_size > MAX_TABLE_BYTES or offset + stored_size > archive_size:
                if on_error is not None:
                    on_error(logical_path, "Entrada BHD fuera del contenedor o demasiado grande")
                    continue
                raise ValidationError(f"Entrada BHD fuera del contenedor: {name}")
            stream.seek(offset)
            stored = stream.read(stored_size)
            if compressed_size:
                try:
                    decoder = zlib.decompressobj()
                    raw = decoder.decompress(stored, raw_size + 1)
                except zlib.error as exc:
                    if on_error is not None:
                        on_error(logical_path, f"Compresión inválida: {exc}")
                        continue
                    raise ValidationError(f"Compresión inválida: {name}") from exc
                if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                    if on_error is not None:
                        on_error(logical_path, "Flujo comprimido inválido")
                        continue
                    raise ValidationError(f"Flujo comprimido inválido: {name}")
            else:
                raw = stored
            if len(raw) != raw_size:
                if on_error is not None:
                    on_error(logical_path, "Tamaño descomprimido incorrecto")
                    continue
                raise ValidationError(f"Tamaño descomprimido incorrecto: {name}")
            origin = {"logical_path": logical_path, "archive": f"{logical_directory}/{stem}.BND",
                            "slot": slot, "file_id": file_id, "offset": offset,
                            "raw_size": raw_size, "stored_size": stored_size,
                            "compression": "zlib" if compressed_size else "none",
                            "sha256": hashlib.sha256(raw).hexdigest()}
            yield slot, name, raw, origin
    report(progress, len(files), len(files), f"{len(files)} entradas leídas")


def scan_archive(directory: Path, logical_directory: str, *, progress=None):
    candidates, origins = [], []
    for slot, name, raw, origin in iter_archive_members(directory, logical_directory, progress=progress, suffixes={".fmg"}):
        candidates.extend(fmg_candidates(raw, origin["logical_path"]))
        origins.append(origin)
    return candidates, origins
