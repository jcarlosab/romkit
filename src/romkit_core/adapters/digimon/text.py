"""Read indexed UTF-16LE BTX tables in PSP ARCV resources.

Format reference: SydMontague/DecodeTools, res/payload/BTXPayload.java.
Pointers are relative to the start of each eight-byte ID/pointer record.
"""
import hashlib
import struct

from romkit_core.errors import ValidationError
from romkit_core.models.text_candidate import TextCandidate
from romkit_core.tasks import report
from .archive import iter_arcv


def btx_candidates(data, logical_path, at=0, *, limit=None, table_limit=None):
    limit = len(data) if limit is None else limit
    table_limit = limit if table_limit is None else table_limit
    def invalid():
        return ValidationError(f"Tabla BTX inválida: {logical_path}@{at:x}")
    if not 0 <= at <= limit <= len(data) or at + 12 > limit or data[at:at + 4] != b"BTX ":
        raise invalid()
    version, header = struct.unpack_from("<II", data, at + 4)
    table = at + header
    if version != 1 or header not in (12, 16) or table + 8 > limit:
        raise invalid()
    languages, count = struct.unpack_from("<II", data, table)
    start = table + 8 + count * 8
    if languages != 1 or count > 50000 or start > min(limit, table_limit):
        raise invalid()
    pointers = []
    for row in range(count):
        pos = table + 8 + row * 8
        ident, relative = struct.unpack_from("<II", data, pos)
        pointer = pos + relative
        if pointer % 2 or not start <= pointer < limit:
            raise invalid()
        pointers.append((ident, pointer))
    candidates, seen = [], set()
    resource_id = hashlib.sha256(logical_path.encode()).hexdigest()
    for ident, pointer in pointers:
        if pointer in seen:
            continue
        seen.add(pointer)
        end = pointer
        while end + 2 <= min(limit, pointer + 16384) and data[end:end + 2] != b"\0\0":
            end += 2
        if end + 2 > limit or data[end:end + 2] != b"\0\0":
            raise invalid()
        try:
            text = data[pointer:end].decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as exc:
            raise invalid() from exc
        if text.strip():
            candidates.append(TextCandidate(resource_id, logical_path, pointer, "utf-16-le", end - pointer,
                text, b"\0\0", 1.0, ("Tabla BTX indexada", f"ID {ident}", f"BTX @{at:x}")))
    return candidates


def resource_btx_candidates(raw, logical, structure=None):
    if raw[:4] != b"KCAP" and raw[:4] != b"BTX " and raw[4:8] != b"BTX ":
        return []
    limit = structure if structure is not None else len(raw)
    found, offset = [], 0
    while (offset := raw.find(b"BTX ", offset, limit)) >= 0:
        found.extend(btx_candidates(raw, logical, offset, table_limit=limit))
        offset += 4
    return found


def scan_arcv_text(index_path, logical_index, *, progress=None):
    candidates, origins = [], []
    for index, (name, raw, base, structure) in enumerate(iter_arcv(index_path)):
        report(progress, index, 50000, f"Leyendo tablas BTX · {name}")
        # Audio/texture payloads must never be interpreted as dialogue.
        logical = logical_index + ".contents/" + name
        found = resource_btx_candidates(raw, logical, structure)
        if found:
            candidates.extend(found)
            origins.append({"logical_path": logical, "archive": logical_index, "member": name,
                            "format": "btx", "sha256": hashlib.sha256(raw).hexdigest(),
                            "reinsert_supported": True})
    return candidates, origins
