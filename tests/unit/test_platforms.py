from dataclasses import dataclass

import pytest

from romkit_core.errors import PlatformError, ValidationError
from romkit_core.models import InputImage
from romkit_core.platforms import ExtractionResult, PlatformImage, PlatformRegistry, ProbeResult

pytestmark = pytest.mark.unit


@dataclass
class FakeBackend:
    id: str = "fake"
    display_name: str = "Fixture platform"
    result: ProbeResult = ProbeResult(True, 0.8, ("Fixture signature",))

    def probe(self, path):
        return self.result

    def open_image(self, path):
        return PlatformImage(self.id, InputImage(path, 0, "00" * 32))

    def list_resources(self, image):
        return []

    def extract(self, image, destination):
        return ExtractionResult(destination)


def test_backend_registration_and_manual_resolution(tmp_path):
    registry = PlatformRegistry()
    backend = FakeBackend(result=ProbeResult(False))
    registry.register(backend)
    assert registry.resolve("fake") is backend
    assert registry.available() == (backend,)
    assert registry.detect(tmp_path / "unknown.iso") == []
    with pytest.raises(PlatformError, match="already registered"):
        registry.register(backend)
    with pytest.raises(PlatformError, match="Unknown platform"):
        registry.resolve("missing")


def test_candidates_sorted_with_no_unsupported_claims(tmp_path):
    registry = PlatformRegistry()
    for id, result in [
        ("low", ProbeResult(True, 0.2, ("Header",))),
        ("high", ProbeResult(True, 0.9, ("Magic",))),
        ("no-evidence", ProbeResult(True, 1)),
        ("zero", ProbeResult(True, 0, ("Hint",))),
        ("incompatible", ProbeResult(False, 1, ("Wrong magic",))),
    ]:
        registry.register(FakeBackend(id=id, result=result))
    original = tmp_path / "test.iso"
    original.write_bytes(b"untouched")
    before = original.read_bytes(), original.stat().st_mtime_ns
    assert [candidate.backend_id for candidate in registry.detect(original)] == ["high", "low"]
    assert (original.read_bytes(), original.stat().st_mtime_ns) == before


@pytest.mark.parametrize("confidence", [-1, 2, True, float("nan"), float("inf"), "0.5"])
def test_invalid_confidence(confidence):
    with pytest.raises(ValidationError):
        ProbeResult(True, confidence)


def test_backend_failure_and_incomplete_contract_are_explicit(tmp_path):
    registry = PlatformRegistry()
    with pytest.raises(PlatformError, match="implement"):
        registry.register(object())
    registry.register(FakeBackend(result=None))
    with pytest.raises(PlatformError, match="Invalid probe"):
        registry.detect(tmp_path / "a")


def test_probe_error_identifies_backend(tmp_path):
    class BrokenBackend(FakeBackend):
        def probe(self, path):
            raise OSError("cannot read")
    registry = PlatformRegistry()
    registry.register(BrokenBackend())
    with pytest.raises(PlatformError, match="fake") as error:
        registry.detect(tmp_path / "a")
    assert isinstance(error.value.__cause__, OSError)
