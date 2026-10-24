from dataclasses import dataclass
import mmap
from pathlib import Path

from romkit_core.errors import ValidationError
from romkit_core.models import ResourceEntry
from romkit_core.models.text_candidate import TextCandidate
from romkit_core.tasks import ProgressCallback, report
from .text_quality import plausible_text
from .containers import recognized_container


@dataclass(frozen=True)
class ScannerConfig:
    min_chars: int = 6
    min_printable_ratio: float = 0.95
    min_confidence: float = 0.85
    max_candidates: int = 1000
    max_text_bytes: int = 8192
    require_terminator: bool = False
    encodings: tuple[str, ...] = ("ascii", "utf-8", "utf-16-le", "utf-16-be", "shift_jis", "cp932")

    def __post_init__(self):
        from romkit_core.models import common as v
        for name in ("min_chars", "max_candidates", "max_text_bytes"):
            v.integer(getattr(self, name), name, minimum=1)
        for name in ("min_printable_ratio", "min_confidence"):
            if not isinstance(getattr(self, name), (float, int)) or not 0 <= getattr(self, name) <= 1:
                raise ValidationError(f"Invalid {name}")
        allowed = {"ascii", "utf-8", "utf-16-le", "utf-16-be", "shift_jis", "cp932"}
        if not self.encodings or not set(self.encodings) <= allowed:
            raise ValidationError("Unsupported scanner encoding")


class TextScanner:
    def __init__(self, config: ScannerConfig | None = None):
        self.config = config if config is not None else ScannerConfig()

    @staticmethod
    def _character(data, offset, encoding):
        value = data[offset]
        wide = encoding.startswith("utf-16")
        if wide:
            width = 2
            if offset + width > len(data):
                return None, 1
            codepoint = int.from_bytes(data[offset:offset + 2], "little" if encoding.endswith("le") else "big")
            if 0xD800 <= codepoint <= 0xDBFF:
                width = 4
        elif encoding == "ascii":
            width = 1
            if value > 127:
                return None, 1
        elif encoding == "utf-8":
            width = 1 if value < 128 else (2 if 0xC2 <= value <= 0xDF else (3 if 0xE0 <= value <= 0xEF else (4 if 0xF0 <= value <= 0xF4 else 0)))
            if width == 0:
                return None, 1
        else:
            width = 2 if 0x81 <= value <= 0x9F or 0xE0 <= value <= 0xFC else 1
        if offset + width > len(data):
            return None, 2 if wide else 1
        raw = bytes(data[offset:offset + width])
        try:
            char = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            return None, 2 if wide else 1
        if char == "\x00":
            return "\x00", width
        if len(char) != 1 or (not char.isprintable() and char not in "\r\n\t") or char == "\ufeff":
            return None, width
        return char, width

    def _candidate(self, data, resource, start, end, encoding, terminator):
        raw = bytes(data[start:end])
        try:
            text = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            return None
        if len(text) < self.config.min_chars or not text.strip() or len(raw) > self.config.max_text_bytes:
            return None
        if not plausible_text(text):
            return None
        plain_latin = all(ord(char) < 128 for char in text)
        printable = sum(char.isprintable() or (plain_latin and char in "\r\n\t") for char in text) / len(text)
        letters = sum(char.isalpha() for char in text) / len(text)
        if printable < self.config.min_printable_ratio or letters < 0.5:
            return None
        if self.config.require_terminator and not terminator:
            return None
        kana = any("\u3040" <= char <= "\u30ff" for char in text)
        natural = " " in text.strip() or kana or (plain_latin and len(text.split()) >= 2)
        latin = any("a" <= char.lower() <= "z" for char in text)
        confidence = 0.65 + (0.15 if terminator else 0) + (0.1 if natural else 0) + (0.05 if latin else 0)
        # Plain English files and control-delimited dialogue often have no NUL.
        # Require multiple words for this weaker boundary, keeping binary runs
        # from receiving the same evidence as a terminated string.
        words = text.split()
        if not terminator and plain_latin and latin and len(words) >= 2:
            confidence += 0.05
        if confidence + 1e-9 < self.config.min_confidence:
            return None
        return TextCandidate(resource.resource_id, resource.logical_path, start, encoding, len(raw), text, terminator,
                             min(confidence, 1), ("Escritura coherente", "Terminador observado" if terminator else "Sin terminador", f"Imprimibles: {printable:.0%}"))

    def scan(self, data: bytes | memoryview, resource: ResourceEntry, *, progress: ProgressCallback | None = None) -> list[TextCandidate]:
        candidates, seen = [], set()
        for encoding_index, encoding in enumerate(self.config.encodings):
            wide = encoding.startswith("utf-16")
            for alignment in range(2 if wide else 1):
                offset, start = alignment, None
                while offset < len(data):
                    if offset % 65536 == alignment:
                        report(progress, encoding_index * len(data) + offset, len(self.config.encodings) * len(data), "Buscando texto")
                    char, width = self._character(data, offset, encoding)
                    if char is None or char == "\x00":
                        if start is not None:
                            terminator = bytes(data[offset:offset + width]) if char == "\x00" else b""
                            candidate = self._candidate(data, resource, start, offset, encoding, terminator)
                            if candidate is not None:
                                key = candidate.offset, candidate.length_bytes, candidate.text
                                if key not in seen:
                                    seen.add(key)
                                    candidates.append(candidate)
                                    if len(candidates) >= self.config.max_candidates:
                                        return sorted(candidates, key=lambda item: (item.offset, item.encoding))
                        start = None
                    else:
                        if start is None:
                            start = offset
                        if offset - start > self.config.max_text_bytes:
                            # Discard the complete overlong run, including its suffix.
                            while offset < len(data):
                                char, width = self._character(data, offset, encoding)
                                if char is None or char == "\x00":
                                    break
                                offset += width
                            start = None
                    offset += width
                if start is not None and not self.config.require_terminator:
                    candidate = self._candidate(data, resource, start, len(data), encoding, b"")
                    if candidate is not None and (candidate.offset, candidate.length_bytes, candidate.text) not in seen:
                        seen.add((candidate.offset, candidate.length_bytes, candidate.text))
                        candidates.append(candidate)
        report(progress, len(data), len(data), "Búsqueda terminada")
        return sorted(candidates, key=lambda item: (item.offset, item.encoding))

    def scan_file(self, path: Path, resource: ResourceEntry, *, progress: ProgressCallback | None = None) -> list[TextCandidate]:
        if path.stat().st_size == 0:
            return []
        # One read-only mapping; candidates retain strings and metadata, not buffers.
        with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            head = bytes(data[:16])
            if head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM", b"RIFF",
                                b"OggS", b"fLaC", b"ID3", b"PSMF", b"\x7fELF", b"~PSP", b"\x00PSF",
                                b"MIG.", b"LDMU", b"DRB\x00")) or recognized_container(data):
                report(progress, 1, 1, "Recurso binario conocido: se omite la búsqueda de cadenas")
                return []
            return self.scan(data, resource, progress=progress)
