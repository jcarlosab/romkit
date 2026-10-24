import hashlib
import json

from romkit_core.models import common as v

JSONL_FIELDS = {"id", "source", "target", "status", "context", "encoding", "constraints", "tokens"}


def stable_unit_id(logical_path: str, offset: int, encoding: str) -> str:
    v.safe_logical_path(logical_path)
    v.integer(offset, "offset")
    v.text(encoding, "encoding")
    identity = json.dumps([logical_path, offset, encoding], ensure_ascii=False, separators=(",", ":"))
    return "text." + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
