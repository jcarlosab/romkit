import json
import subprocess
import sys

import pytest

from romkit_core.errors import SerializationError, ValidationError
from romkit_core.models import (AnalysisStatus, InputImage, ProjectConfig, ResourceEntry,
                                TextConstraints, TranslationStatus, TranslationUnit, ValidationIssue)

HASH = "ab" * 32


@pytest.mark.unit
@pytest.mark.parametrize("model", [
    InputImage("game.iso", 42, HASH, "psp", "psp"),
    ResourceEntry("r1", "folder/text.bin", 12, HASH),
    ProjectConfig("psp", HASH, "ja", "es-ES"),
    TranslationUnit("dialogue.1", "Hello {name}", "Hola {name}", "translated", "Shop", "utf-8", TextConstraints(max_bytes=24), ("{name}",)),
    ValidationIssue("warning", "too_long", "Translation too long", "r1", "dialogue.1"),
])
def test_explicit_json_roundtrip(model):
    assert type(model).from_dict(json.loads(json.dumps(model.to_dict()))) == model
    assert type(model).from_json(model.to_json()) == model


@pytest.mark.unit
def test_project_toml_roundtrip():
    config = ProjectConfig("psp", HASH, "日本語 🎮", "es-ES")
    assert ProjectConfig.from_toml(config.to_toml()) == config


@pytest.mark.unit
def test_states_and_unknown_resources():
    assert ResourceEntry("r", "a.bin", 0, HASH).analysis_status is AnalysisStatus.UNKNOWN
    assert TranslationUnit("t", "Hi").status is TranslationStatus.UNTRANSLATED
    assert InputImage("game.iso", 0, HASH).detected_platform is None
    assert InputImage("game.iso", 0, HASH, selected_platform="future-platform").selected_platform == "future-platform"


@pytest.mark.unit
@pytest.mark.parametrize("factory", [
    lambda: InputImage("", 1, HASH), lambda: InputImage("a", -1, HASH),
    lambda: InputImage("a", True, HASH), lambda: InputImage("a", 1, "bad"),
    lambda: InputImage("a", 1, HASH, selected_platform=""),
    lambda: ResourceEntry("", "a", 0, HASH), lambda: ResourceEntry("r", "../a", 0, HASH),
    lambda: ResourceEntry("r", "a", 0, HASH, analysis_status="invalid"),
    lambda: ProjectConfig("psp", HASH, "", "es"), lambda: ProjectConfig("psp", HASH, "ja", "es", 2),
    lambda: TranslationUnit("t", "Hi", status="invalid"), lambda: TranslationUnit("t", "Hi", target=None),
    lambda: TranslationUnit("t", "Hi", tokens="token"), lambda: TextConstraints(max_bytes=-1),
    lambda: ValidationIssue("fatal", "code", "message"),
    lambda: TranslationUnit.from_dict({"source": "Hi"}),
    lambda: InputImage.from_dict({"path": "a", "size_bytes": 0, "sha256": HASH, "extra": 1}),
])
def test_invalid_input_is_explicit(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.unit
def test_malformed_documents():
    with pytest.raises(SerializationError):
        InputImage.from_json("{")
    with pytest.raises(SerializationError):
        ProjectConfig.from_toml("bad = [")


@pytest.mark.unit
def test_models_import_without_qt():
    result = subprocess.run([sys.executable, "-c", "import romkit_core.models; import sys; assert not any(n.startswith('PySide6') for n in sys.modules)"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
