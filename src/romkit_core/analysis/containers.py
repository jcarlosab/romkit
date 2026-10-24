"""Bounded container traversal, independent from image/text decoders."""
from dataclasses import dataclass, field
from io import BytesIO
import re
import struct
import zipfile
import zlib

MAX_MEMBER = 64 * 1024 * 1024


@dataclass
class Traversal:
    max_depth: int = 8
    max_expanded: int = 2 * 1024 * 1024 * 1024
    max_nodes: int = 50000
    expanded: int = 0
    nodes: int = 0
    containers: int = 0
    warnings: list = field(default_factory=list)

    def warn(self, path, message):
        if len(self.warnings) < 200:
            self.warnings.append({"source": path, "message": str(message)})

    def charge(self, length):
        if length < 0 or length > MAX_MEMBER or self.expanded + length > self.max_expanded or self.nodes >= self.max_nodes:
            raise ValueError("Límite de expansión del contenedor alcanzado")
        self.expanded += length
        self.nodes += 1


def _name(raw):
    # Names are virtual provenance, never paths supplied to the filesystem.
    return re.sub(r"[^A-Za-z0-9._-]", "_", raw.replace("\\", "/").rsplit("/", 1)[-1])[:80] or "entry"


def _children(data, logical, traversal):
    head = bytes(data[:16])
    if head.startswith(b"BND\x00"):
        if len(data) < 32:
            raise ValueError("Cabecera BND truncada")
        size, count = struct.unpack_from("<II", data, 12)
        if size != len(data) or count > 20000 or 32 + count * 16 > size:
            raise ValueError("Tabla BND inválida")
        for index in range(count):
            identifier, offset, length, name_offset = struct.unpack_from("<4I", data, 32 + index * 16)
            if offset < 32 + count * 16 or offset + length > size or not 0 <= name_offset < size:
                raise ValueError("Entrada BND fuera de límites")
            end = data.find(b"\0", name_offset, min(size, name_offset + 256))
            if end < 0:
                raise ValueError("Nombre BND sin terminador")
            name = bytes(data[name_offset:end]).decode("cp932", errors="replace")
            traversal.charge(length)
            yield f"{logical}!bnd/{index:05d}-{_name(name)}", bytes(data[offset:offset + length])
    elif head.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        if len(data) > MAX_MEMBER:
            raise ValueError("ZIP demasiado grande para el lector en memoria")
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 20000:
                raise ValueError("ZIP con demasiadas entradas")
            for index, entry in enumerate(entries):
                if entry.is_dir():
                    continue
                if entry.flag_bits & 1:
                    traversal.warn(logical, "Entrada ZIP cifrada omitida")
                    continue
                traversal.charge(entry.file_size)
                with archive.open(entry) as stream:
                    raw = stream.read(MAX_MEMBER + 1)
                if len(raw) != entry.file_size:
                    raise ValueError("Tamaño de entrada ZIP incorrecto")
                yield f"{logical}!zip/{index:05d}-{_name(entry.filename)}", raw
    elif head.startswith(b"\x1f\x8b") or _zlib_header(head):
        decoder = zlib.decompressobj(31 if head.startswith(b"\x1f\x8b") else 15)
        raw = decoder.decompress(data, min(MAX_MEMBER, traversal.max_expanded - traversal.expanded) + 1)
        if not decoder.eof or decoder.unconsumed_tail or (decoder.unused_data and any(decoder.unused_data)):
            raise ValueError("Flujo comprimido inválido, múltiple o demasiado grande")
        traversal.charge(len(raw))
        yield logical + "!decompressed", raw


def recognized_container(data):
    head = bytes(data[:16])
    return (head.startswith((b"BND\0", b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b"))
            or _zlib_header(head))


def _zlib_header(head):
    return len(head) >= 2 and head[0] & 15 == 8 and head[0] >> 4 <= 7 and int.from_bytes(head[:2], "big") % 31 == 0


def walk_payloads(data, logical, traversal, *, depth=0, progress=None):
    if progress:
        progress(logical)
    if not recognized_container(data):
        yield logical, data
        return
    if depth >= traversal.max_depth:
        traversal.warn(logical, "Límite de profundidad del contenedor alcanzado")
        return
    traversal.containers += 1
    try:
        for name, raw in _children(data, logical, traversal):
            yield from walk_payloads(raw, name, traversal, depth=depth + 1, progress=progress)
    except zlib.error as exc:
        if bytes(data[:2]) != b"\x1f\x8b":
            # A two-byte zlib-like prefix alone is not a verified container.
            traversal.containers -= 1
            yield logical, data
        else:
            traversal.warn(logical, exc)
    except (ValueError, zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError) as exc:
        traversal.warn(logical, exc)
        if bytes(data[:4]) == b"BND\0":
            # Even an unsupported BND layout may contain self-describing GIM/PNG.
            yield logical, data
