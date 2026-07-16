"""Unit tests for PipelexBundleSpec.to_blueprint conversion: concepts, pipe ordering, and error wrapping."""

from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.builder.exceptions import PipelexBundleSpecBlueprintError
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def make_llm_spec(pipe_code: str) -> PipeLLMSpec:
    return PipeLLMSpec(
        pipe_code=pipe_code,
        description=f"Generate text for {pipe_code}",
        inputs={"topic": "Text"},
        output="Text",
        prompt="Write about $topic",
        model="$writing-creative",
    )


def make_sequence_spec(pipe_code: str, step_codes: list[str]) -> PipeSequenceSpec:
    steps = [SubPipeSpec(pipe_code=step_code, result=f"{step_code}_result") for step_code in step_codes]
    return PipeSequenceSpec(
        pipe_code=pipe_code,
        description=f"Sequence {pipe_code}",
        inputs={"topic": "Text"},
        output="Text",
        steps=steps,
    )


def make_captured_validation_error() -> ValidationError:
    """Capture a real pydantic ValidationError from an intentionally invalid model construction."""
    try:
        ConceptBlueprint.model_validate({})
    except ValidationError as exc:
        return exc
    pytest.fail("ConceptBlueprint.model_validate({}) should have raised a ValidationError")


class TestPipelexBundleSpecToBlueprint:
    def test_concept_spec_value_converted_to_concept_blueprint(self) -> None:
        """A ConceptSpec value converts to its own blueprint, preserving description, structure and refines."""
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            main_pipe="write_text",
            concept={
                "Article": ConceptSpec(concept_code="Article", description="A written article", refines="Text"),
                "Person": ConceptSpec(
                    concept_code="Person",
                    description="A person",
                    structure={
                        "full_name": ConceptStructureSpec(
                            the_field_name="full_name",
                            description="Full name of the person",
                            type=ConceptStructureSpecFieldType.TEXT,
                            required=True,
                        ),
                    },
                ),
            },
            pipe={"write_text": make_llm_spec("write_text")},
        )

        blueprint = bundle_spec.to_blueprint()

        assert blueprint.concept is not None
        assert blueprint.concept["Article"] == ConceptBlueprint(description="A written article", structure=None, refines="Text")
        expected_field = ConceptStructureBlueprint(
            description="Full name of the person",
            type=ConceptStructureBlueprintFieldType.TEXT,
            required=True,
        )
        assert blueprint.concept["Person"] == ConceptBlueprint(description="A person", structure={"full_name": expected_field}, refines=None)

    def test_string_concept_value_passes_through_as_description(self) -> None:
        """A string concept value passes through to the blueprint dict unchanged, where it means the concept's description."""
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            main_pipe="write_text",
            concept={"Summary": "A short summary of a document"},
            pipe={"write_text": make_llm_spec("write_text")},
        )

        blueprint = bundle_spec.to_blueprint()

        assert blueprint.concept is not None
        assert blueprint.concept["Summary"] == "A short summary of a document"

    def test_string_concept_value_survives_normal_validation(self) -> None:
        """model_validate on a dict payload keeps a string concept value as a plain str via the `ConceptSpec | str` union."""
        bundle_spec = PipelexBundleSpec.model_validate(
            {
                "domain": "test_domain",
                "main_pipe": "write_text",
                "concept": {"Summary": "A short summary of a document"},
                "pipe": {"write_text": make_llm_spec("write_text").model_dump()},
            }
        )

        assert bundle_spec.concept is not None
        assert bundle_spec.concept["Summary"] == "A short summary of a document"

    @pytest.mark.parametrize("empty_concepts", [None, {}])
    def test_no_concepts_yields_none_concept_on_blueprint(self, empty_concepts: dict[str, Any] | None) -> None:
        """Concept set to None or left empty produces a blueprint with concept=None."""
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            main_pipe="write_text",
            concept=empty_concepts,
            pipe={"write_text": make_llm_spec("write_text")},
        )

        blueprint = bundle_spec.to_blueprint()

        assert blueprint.concept is None

    def test_pipes_sorted_controller_first_then_step_order(self) -> None:
        """Pipes fed in scrambled dict order come out controller-first, then in step order, with header fields preserved."""
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            description="A sequenced bundle",
            system_prompt="Be precise",
            main_pipe="main_seq",
            pipe={
                "step_two": make_llm_spec("step_two"),
                "step_one": make_llm_spec("step_one"),
                "main_seq": make_sequence_spec("main_seq", step_codes=["step_one", "step_two"]),
            },
        )

        blueprint = bundle_spec.to_blueprint()

        assert blueprint.domain == "test_domain"
        assert blueprint.description == "A sequenced bundle"
        assert blueprint.system_prompt == "Be precise"
        assert blueprint.main_pipe == "main_seq"
        assert blueprint.pipe is not None
        assert list(blueprint.pipe.keys()) == ["main_seq", "step_one", "step_two"]
        assert blueprint.pipe["main_seq"].type == "PipeSequence"
        assert blueprint.pipe["step_one"].type == "PipeLLM"
        assert blueprint.pipe["step_two"].type == "PipeLLM"

    def test_pipe_spec_validation_error_wrapped_with_pipe_code(self, mocker: "MockerFixture") -> None:
        """A ValidationError from a pipe spec's to_blueprint is wrapped, naming the failing pipe code."""
        captured_error = make_captured_validation_error()
        mocker.patch.object(PipeLLMSpec, "to_blueprint", side_effect=captured_error)
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            main_pipe="write_text",
            pipe={"write_text": make_llm_spec("write_text")},
        )

        with pytest.raises(PipelexBundleSpecBlueprintError, match="Failed to create pipe blueprint from spec for pipe code write_text"):
            bundle_spec.to_blueprint()

    def test_bundle_blueprint_construction_failure_wrapped(self) -> None:
        """A spec that yields an invalid bundle blueprint (native concept shadowing) raises the wrapped error."""
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            main_pipe="write_text",
            concept={"Text": "Shadowing a native concept"},
            pipe={"write_text": make_llm_spec("write_text")},
        )

        with pytest.raises(PipelexBundleSpecBlueprintError, match="Failed to create pipelex bundle blueprint"):
            bundle_spec.to_blueprint()
