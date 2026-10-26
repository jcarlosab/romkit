"""Grow indexed FMG strings without discarding original resource bytes."""
import struct

from romkit_core.errors import ValidationError
from .reader import MAX_TABLE_BYTES, fmg_candidates


def indexed_strings(raw, logical):
    fmg_candidates(raw, logical)
    count, table = struct.unpack_from('<2I', raw, 16)
    return tuple(None if offset == 0 else bytes(raw[offset:raw.index(0, offset)])
                 for offset in struct.unpack_from(f'<{count}I', raw, table))


def grow_fmg(raw, changes, logical):
    """Move only oversized strings; update every alias of their indexed pointer."""
    before = indexed_strings(raw, logical)
    count, table = struct.unpack_from('<2I', raw, 16)
    pointers = struct.unpack_from(f'<{count}I', raw, table)
    valid = {c.offset: c for c in fmg_candidates(raw, logical)}
    output = bytearray(raw)
    moved, targets = {}, {}
    for candidate, target in changes:
        expected = valid.get(candidate.offset)
        if expected is None or expected.text != candidate.text or expected.length_bytes != candidate.length_bytes:
            raise ValidationError(f'{logical}: texto original modificado o no indexado')
        start, end = candidate.offset, candidate.offset + candidate.length_bytes + 1
        if any(other != start and other < end and other + len(value) + 1 > start
               for other, value in zip(pointers, before) if other and value is not None):
            raise ValidationError(f'{logical}: cadenas indexadas solapadas; ampliación no implementada')
        if start in targets:
            raise ValidationError(f'{logical}: cambio duplicado de cadena')
        targets[start] = target
        if len(target) > candidate.length_bytes:
            required = len(output) + len(target) + 1
            if required > MAX_TABLE_BYTES:
                raise ValidationError(f'{logical}: FMG requiere {required} bytes; disponibles {MAX_TABLE_BYTES} (límite de seguridad)')
            moved[start] = len(output)
            output.extend(target + b'\0')
        else:
            output[start:end] = target + bytes(end - start - len(target))
    for row, pointer in enumerate(pointers):
        if pointer in moved:
            struct.pack_into('<I', output, table + row * 4, moved[pointer])
    struct.pack_into('<I', output, 4, len(output))
    after = indexed_strings(output, logical)
    if after != tuple(targets.get(pointer, value) for pointer, value in zip(pointers, before)):
        raise ValidationError(f'{logical}: falló la verificación FMG por índice')
    return bytes(output)
