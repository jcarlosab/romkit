from io import BytesIO
import random
import struct
import zlib

import pytest
from romkit_core.errors import ValidationError
from romkit_core.project.delta import create_bps, verify_bps, number
from romkit_core.tasks import TaskCancelled


def decode_reference(patch, source):
    # Independent small BPS decoder following the public specification.
    stream = BytesIO(patch)
    def integer():
        result, shift = 0, 1
        while True:
            value = stream.read(1)[0]
            result += (value & 127) * shift
            if value & 128:
                return result
            shift *= 128
            result += shift
    assert stream.read(4) == b'BPS1'
    assert integer() == len(source)
    target_size = integer()
    stream.read(integer())
    output = bytearray()
    while len(output) < target_size:
        action = integer()
        length, mode = (action >> 2) + 1, action & 3
        if mode == 0:
            output.extend(source[len(output):len(output)+length])
        elif mode == 1:
            output.extend(stream.read(length))
        else:
            raise AssertionError('Unexpected copy opcode')
    assert stream.tell() == len(patch) - 12
    assert struct.unpack('<III',stream.read(12)) == (zlib.crc32(source), zlib.crc32(output), zlib.crc32(patch[:-4]))
    return bytes(output)


@pytest.mark.parametrize('source,target', [(b'',b''),(b'a',b'b'),(b'abc',b'abcdef'),(b'abcdef',b'ab'),
    (b'a'*140000,b'a'*65000+b'changed'+b'a'*70000),
    (random.Random(1).randbytes(10000),random.Random(2).randbytes(12000))], ids=['empty','replace','grow','shrink','blocks','random'])
def test_bps_standard_roundtrip(tmp_path,source,target):
    first, second, patch = (tmp_path/name for name in ('original.iso','translated.iso','patch.bps'))
    first.write_bytes(source)
    second.write_bytes(target)
    result = create_bps(first,second,patch)
    assert result.size == patch.stat().st_size
    assert decode_reference(patch.read_bytes(),source) == target
    assert first.read_bytes() == source and second.read_bytes() == target


def test_bps_checksums_existing_output_and_cancel(tmp_path):
    first, second, patch = (tmp_path/name for name in ('first','second','patch'))
    first.write_bytes(b'original')
    second.write_bytes(b'translated')
    with pytest.raises(ValidationError):
        create_bps(first,second,patch,expected_source_sha256='00'*32)
    assert not patch.exists()
    def cancel(value):
        raise TaskCancelled()
    with pytest.raises(TaskCancelled):
        create_bps(first,second,patch,progress=cancel)
    assert not patch.exists() and not list(tmp_path.glob('.romkit-bps-*'))
    create_bps(first,second,patch)
    with pytest.raises(ValidationError):
        create_bps(first,second,patch)
    raw = bytearray(patch.read_bytes())
    raw[-1] ^= 1
    patch.write_bytes(raw)
    with pytest.raises(ValidationError,match='CRC'):
        verify_bps(patch,first,second)


def test_spec_varints():
    assert number(0) == b'\x80'
    assert number(127) == b'\xff'
    assert number(128) == b'\x00\x80'
