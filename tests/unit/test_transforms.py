import json
from pathlib import Path

import pytest

from romkit_core.errors import TransformError, ValidationError
from romkit_core.transforms import (Detection, TransformChain, TransformContext, TransformPipeline,
                                    TransformRegistry, TransformStep)
from romkit_core.workspace import WorkspaceManager

pytestmark = pytest.mark.unit
FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "transforms.json").read_text())


class XorFixtureTransform:
    """Controlled test fixture, not a game decryption algorithm."""
    id = "fixture-xor"

    def detect(self, data):
        return Detection(False)

    def decode(self, data, context):
        return bytes(value ^ context.parameters["key"] for value in data)

    def encode(self, data, context):
        return self.decode(data, context)


class RotateFixtureTransform:
    id = "fixture-rotate"

    def detect(self, data):
        return Detection(False)

    def decode(self, data, context):
        return data[1:] + data[:1]

    def encode(self, data, context):
        return data[-1:] + data[:-1]


class AddFixtureTransform:
    id = "fixture-add"

    def detect(self, data):
        return Detection(False)

    def decode(self, data, context):
        return bytes((value + 1) % 256 for value in data)

    def encode(self, data, context):
        return bytes((value - 1) % 256 for value in data)


@pytest.fixture
def pipeline():
    registry = TransformRegistry()
    for handler in (XorFixtureTransform(), RotateFixtureTransform(), AddFixtureTransform()):
        registry.register(handler)
    return TransformPipeline(registry)


@pytest.mark.parametrize("sample", FIXTURE["samples_hex"])
def test_fixture_roundtrip_and_reverse_order(pipeline, sample):
    original = bytes.fromhex(sample)
    steps = [TransformStep("fixture-xor", {"key": FIXTURE["xor_key"]}), TransformStep("fixture-add"), TransformStep("fixture-rotate")]
    result = pipeline.decode(memoryview(original), steps)
    assert pipeline.encode(result.data, result.chain) == original
    if original:
        assert result.data != original


def test_metadata_chain_roundtrip(pipeline, tmp_path):
    manager = WorkspaceManager(tmp_path)
    original = b"fixture"
    result = pipeline.decode(original, [TransformStep("fixture-xor", {"key": 42}), TransformStep("fixture-add")])
    manager.write_metadata("transforms/resource.json", result.chain.to_dict())
    loaded = TransformChain.from_dict(manager.read_metadata("transforms/resource.json"))
    assert loaded == TransformChain.from_json(result.chain.to_json())
    assert pipeline.encode(result.data, loaded) == original


def test_identity_and_empty_chain(pipeline):
    for steps in ([], [TransformStep("identity")]):
        result = pipeline.decode(b"data", steps)
        assert pipeline.encode(result.data, result.chain) == b"data"


def test_unknown_handler_resolves_before_any_processing(pipeline):
    calls = []
    class Spy(AddFixtureTransform):
        id = "spy"
        def decode(self, data, context):
            calls.append(data)
            return data
    pipeline.registry.register(Spy())
    chain = [TransformStep("spy"), TransformStep("missing")]
    with pytest.raises(TransformError, match="Unknown transform: missing"):
        pipeline.decode(b"original", chain)
    assert calls == []
    with pytest.raises(TransformError, match="Unknown"):
        pipeline.encode(b"original", TransformChain(tuple(chain)))


def test_handler_errors_never_return_partial_data(pipeline):
    with pytest.raises(TransformError, match="fixture-xor") as error:
        pipeline.decode(b"original", [TransformStep("fixture-add"), TransformStep("fixture-xor")])
    assert isinstance(error.value.__cause__, KeyError)


def test_snapshot_parameters_and_context(pipeline):
    params = {"key": 42, "nested": [1]}
    step = TransformStep("fixture-xor", params)
    params["nested"].append(2)
    assert step.parameters["nested"] == [1]
    context = TransformContext(step.parameters, "r1")
    context.parameters["nested"].append(3)
    assert step.parameters["nested"] == [1]


@pytest.mark.parametrize("data", [
    {"schema_version": 2, "steps": []}, {"schema_version": 1, "steps": "identity"},
    {"schema_version": 1, "steps": [{"handler_id": "identity", "extra": 1}]},
])
def test_invalid_chain_metadata(data):
    with pytest.raises(ValidationError):
        TransformChain.from_dict(data)


def test_registry_and_parameters_are_validated(pipeline):
    with pytest.raises(TransformError, match="already registered"):
        pipeline.registry.register(XorFixtureTransform())
    with pytest.raises(TransformError, match="implement"):
        pipeline.registry.register(object())
    with pytest.raises(ValidationError):
        TransformStep("identity", {"key": object()})
