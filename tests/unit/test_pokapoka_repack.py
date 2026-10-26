import struct
import pytest
from pokapoka_builder import make_fmg
from romkit_core.adapters.pokapoka.reader import fmg_candidates
from romkit_core.adapters.pokapoka.repack import grow_fmg, indexed_strings
from romkit_core.errors import ValidationError


def test_long_string_updates_aliases_and_preserves_metadata_and_pending():
    raw = bytearray(make_fmg(['Hi', 'Ignored', 'Pending']))
    raw[44:48] = raw[40:44]
    candidate = fmg_candidates(raw, 'table')[0]
    output = grow_fmg(raw, [(candidate, b'A longer translation')], 'table')
    assert indexed_strings(output, 'table') == (b'A longer translation', b'A longer translation', b'Pending')
    assert output[8:40] == raw[8:40]
    assert output[52:len(raw)] == raw[52:]
    assert struct.unpack_from('<I', output, 4)[0] == len(output)


def test_no_change_is_byte_identical_and_overlap_is_rejected():
    raw = make_fmg(['Hello', 'Pending'])
    candidate = fmg_candidates(raw, 'table')[0]
    assert grow_fmg(raw, [(candidate, b'Hello')], 'table') == raw
    overlap = bytearray(raw)
    struct.pack_into('<I', overlap, 44, candidate.offset + 1)
    with pytest.raises(ValidationError, match='solapadas'):
        grow_fmg(overlap, [(candidate, b'A much longer string')], 'table')
