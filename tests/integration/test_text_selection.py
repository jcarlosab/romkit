from romkit_core.models.text_candidate import TextCandidate
from romkit_studio.models.candidate_table_model import CandidateTableModel


def test_bulk_selection_avoids_encoding_overlap_and_includes_terminator(qapp):
    def candidate(path, offset, length, confidence):
        return TextCandidate("resource", path, offset, "ascii", length, "Text", b"\0", confidence)
    candidates = [candidate("a.bin", 0, 8, .9), candidate("a.bin", 0, 4, 1),
                  candidate("a.bin", 4, 4, 1), candidate("a.bin", 5, 4, 1),
                  candidate("b.bin", 0, 4, 1)]
    model = CandidateTableModel()
    model.set_candidates(candidates)
    model.select_compatible()
    assert model.confirmed() == [candidates[1], candidates[3], candidates[4]]
    model.clear_confirmation()
    assert model.confirmed() == []


def test_removal_and_restore_keep_marks_on_the_right_rows(qapp):
    model = CandidateTableModel()
    candidates = [TextCandidate("r", "table.fmg", row * 10, "ascii", 4, f"Text {row}", b"\0", 1)
                  for row in range(5)]
    model.set_candidates(candidates)
    model.select_compatible()
    model.uncheck_rows([1])
    model.remove_rows([1, 3])
    assert model.candidates == (candidates[0], candidates[2], candidates[4])
    assert model.confirmed() == [candidates[0], candidates[2], candidates[4]]
    model.uncheck_rows([1])  # Change a surviving row after removal.
    model.restore_removal()
    assert model.candidates == tuple(candidates)
    assert model.confirmed() == [candidates[0], candidates[3], candidates[4]]
    model.remove_rows([0])
    model.set_candidates(candidates)
    assert not model.can_restore_removal
    model.select_compatible()
    model.set_candidates([])
    assert model.confirmed() == []
