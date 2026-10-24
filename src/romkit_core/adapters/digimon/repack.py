"""Experimental BTX pool repacking, bounded by the existing string storage."""
import struct
from romkit_core.errors import ValidationError
from .text import resource_btx_candidates


def repack_resource(raw, logical, structure, changes, *, capacity=None):
    capacity = len(raw) if capacity is None else capacity
    valid = resource_btx_candidates(raw, logical, structure)
    indexed = {c.offset: c for c in valid}
    targets = {}
    for candidate, target in changes:
        expected = indexed.get(candidate.offset)
        if expected is None or expected.text != candidate.text or expected.length_bytes != candidate.length_bytes:
            raise ValidationError('El texto BTX original no coincide con el índice')
        text = target.decode('utf-16-le', errors='strict')
        if '\0' in text:
            raise ValidationError('Terminador interno en la traducción')
        targets[candidate.offset] = target
    tables, offset = [], 0
    limit = len(raw) if structure is None else structure
    while (offset := raw.find(b'BTX ', offset, limit)) >= 0:
        header = struct.unpack_from('<I', raw, offset + 8)[0]
        table = offset + header
        count = struct.unpack_from('<I', raw, table + 4)[0]
        records = []
        for row in range(count):
            pos = table + 8 + row * 8
            pointer = pos + struct.unpack_from('<I', raw, pos + 4)[0]
            end = pointer
            while raw[end:end + 2] != b'\0\0':
                end += 2
                if end + 2 > len(raw):
                    raise ValidationError('Cadena BTX truncada')
            records.append((pos, pointer, end))
        tables.append((header, table + 8 + count * 8, records))
        offset += 4
    output, covered = bytearray(raw), set()
    expected_tables = []
    for header, table_end, records in tables:
        pointers = sorted({p: end for _, p, end in records}.items())
        if not any(p in targets for p, _ in pointers):
            expected_tables.append([(pos, raw[p:end]) for pos,p,end in records])
            continue
        if not pointers:
            continue
        start, finish = pointers[0][0], pointers[-1][1] + 2
        # Repacking is allowed only for a contiguous, isolated pool. Never consume
        # opaque metadata or shared strings from another table, even if zero-filled.
        if start < table_end:
            raise ValidationError('El bloque BTX se solapa con su índice')
        for (pointer,end),(following,_) in zip(pointers,pointers[1:]):
            if end + 2 > following or any(raw[end + 2:following]):
                raise ValidationError('La tabla BTX comparte cadenas o intercala datos; no admite redistribución')
        for _, other_end, other_records in tables:
            if other_records is records:
                continue
            if any(start <= p < finish for _,p,_ in other_records) or start < other_end <= finish:
                raise ValidationError('El bloque BTX está compartido con otra tabla')
        packed, relocated = bytearray(), {}
        for index,(pointer,end) in enumerate(pointers):
            alignment = 4 if header == 12 else 2
            packed.extend(bytes((-(start + len(packed))) % alignment))
            relocated[pointer] = start + len(packed)
            packed.extend(targets.get(pointer, raw[pointer:end]))
            packed.extend(b'\0\0')
            if header == 16 and index < len(pointers) - 1:
                packed.extend(b'\0\0')
        if len(packed) > finish - start:
            metadata = struct.unpack_from('<I', raw)[0] if len(raw) >= 4 else 0
            # PSP tutorial wrapper: metadata offset, BTX at 4, 12-byte metadata
            # records. Relocate the opaque records intact, never consume them.
            standalone = (structure is None and raw[4:8] == b'BTX ' and len(tables) == 1
                and header == 12 and metadata == (finish + 3) // 4 * 4
                and len(raw) - metadata == len(records) * 12)
            new_metadata = (start + len(packed) + 3) // 4 * 4
            required = new_metadata + len(raw) - metadata
            if not standalone or required > capacity:
                raise ValidationError(f'{logical}: el bloque BTX necesita {len(packed)} bytes y dispone de {finish-start}. '
                    'No cabe en el espacio ampliable de este recurso; acorta otros textos de esta tabla')
            output = bytearray(raw[:start]) + packed + bytes(new_metadata - start - len(packed)) + raw[metadata:]
            struct.pack_into('<I', output, 0, new_metadata)
        else:
            output[start:finish] = packed + bytes(finish - start - len(packed))
        expected = []
        for pos,pointer,end in records:
            struct.pack_into('<I', output, pos + 4, relocated[pointer] - pos)
            expected.append((pos, targets.get(pointer, raw[pointer:end])))
            if pointer in targets:
                covered.add(pointer)
        expected_tables.append(expected)
    if covered != set(targets):
        raise ValidationError('No se localizaron todas las traducciones en las tablas BTX')
    for expected in expected_tables:
        for pos, text in expected:
            pointer = pos + struct.unpack_from('<I', output, pos + 4)[0]
            if output[pointer:pointer + len(text)] != text or output[pointer + len(text):pointer + len(text) + 2] != b'\0\0':
                raise ValidationError('Falló la verificación por registro BTX')
    resource_btx_candidates(output, logical, structure)
    if len(output) > capacity:
        raise ValidationError('El recurso BTX supera su capacidad de sector')
    return bytes(output)
