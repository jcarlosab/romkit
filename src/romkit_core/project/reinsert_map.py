from dataclasses import dataclass

from romkit_core.models.text_candidate import TextCandidate


@dataclass(frozen=True)
class ReinsertEntry:
    unit_id: str
    candidate: TextCandidate

    def to_dict(self):
        c = self.candidate
        return {"id": self.unit_id, "resource_id": c.resource_id, "logical_path": c.logical_path,
                "offset": c.offset, "length_bytes": c.length_bytes, "encoding": c.encoding,
                "terminator": c.terminator.hex(), "transforms": c.transforms.to_dict()}
