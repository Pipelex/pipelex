import pytest
from pydantic import ValidationError

from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint, PipeCategory, PipeType


class ConcretePipeBlueprint(PipeBlueprint):
    pass


class TestPipeBlueprintValidation:
    def test_validate_pipe_type_correct(self):
        for pipe_type_enum in PipeType:
            blueprint = ConcretePipeBlueprint(
                type=pipe_type_enum,
                pipe_category=pipe_type_enum.category,
                description="lorem ipsum",
                output="Text",
            )
            assert blueprint.type == pipe_type_enum

    def test_validate_pipe_type_incorrect(self):
        invalid_types = ["InvalidType", "PipeTest", "RandomPipe", "NotAPipe", ""]
        for invalid_type in invalid_types:
            with pytest.raises(ValidationError) as exc_info:
                ConcretePipeBlueprint(
                    type=invalid_type,
                    pipe_category="PipeOperator",
                    description="lorem ipsum",
                    output="Text",
                )
            assert "Invalid pipe type" in str(exc_info.value)

    def test_validate_pipe_category_correct(self):
        for category_enum in PipeCategory:
            match category_enum:
                case PipeCategory.PIPE_OPERATOR:
                    pipe_type = PipeType.PIPE_LLM
                case PipeCategory.PIPE_CONTROLLER:
                    pipe_type = PipeType.PIPE_SEQUENCE
            blueprint = ConcretePipeBlueprint(
                type=pipe_type,
                pipe_category=category_enum,
                description="lorem ipsum",
                output="Text",
            )
            assert blueprint.pipe_category == category_enum

    def test_validate_pipe_category_incorrect(self):
        invalid_categories = ["InvalidCategory", "Operator", "Controller", "PipeOp", "RandomCategory", ""]
        for invalid_category in invalid_categories:
            with pytest.raises(ValidationError) as exc_info:
                ConcretePipeBlueprint(
                    type="PipeLLM",
                    pipe_category=invalid_category,
                    description="lorem ipsum",
                    output="Text",
                )
            assert "Invalid pipe category" in str(exc_info.value)

    def test_validate_inputs_blueprint_correct(self):
        blueprint = ConcretePipeBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="lorem ipsum",
            inputs={"text": "Text", "prompt": "Text"},
            output="Text",
        )
        assert blueprint.inputs == {"text": "Text", "prompt": "Text"}

        blueprint = ConcretePipeBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="lorem ipsum",
            inputs=None,
            output="Text",
        )
        assert blueprint.inputs is None

        blueprint = ConcretePipeBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="lorem ipsum",
            inputs={"items": "Text[]", "count": "Number[2]"},
            output="Text",
        )
        assert blueprint.inputs == {"items": "Text[]", "count": "Number[2]"}

    def test_validate_inputs_blueprint_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            ConcretePipeBlueprint(
                type="PipeLLM",
                pipe_category="PipeOperator",
                description="lorem ipsum",
                # NOTE: a trailing "!" is now valid grammar (force marker); use a genuinely
                # malformed spec to exercise the syntax rejection
                inputs={"text": "Invalid@Format"},
                output="Text",
            )
        assert "Invalid input syntax" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            ConcretePipeBlueprint(
                type="PipeLLM",
                pipe_category="PipeOperator",
                description="lorem ipsum",
                inputs={"text": "invalid_concept"},
                output="Text",
            )
        assert "Invalid concept string or code" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            ConcretePipeBlueprint(
                type="PipeLLM",
                pipe_category="PipeOperator",
                description="lorem ipsum",
                inputs={"text": "Text"},
                # NOTE: a trailing "!" is now valid grammar but rejected on outputs (force marker
                # is a use-site assertion); a genuinely malformed spec still hits the syntax error
                output="Invalid@Concept",
            )
        assert "Invalid concept specification syntax" in str(exc_info.value)

    def test_extra_fields_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            ConcretePipeBlueprint(
                type="PipeLLM",
                pipe_category="PipeOperator",
                description="lorem ipsum",
                output="Text",
                extra_field="should not be allowed",  # type: ignore[call-arg]
            )
        assert "extra fields" in str(exc_info.value).lower() or "Extra inputs are not permitted" in str(exc_info.value)

    def test_missing_mandatory_fields_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            ConcretePipeBlueprint(pipe_category="PipeOperator", output="Text")  # type: ignore[call-arg]
        assert "type" in str(exc_info.value).lower()

        with pytest.raises(ValidationError) as exc_info:
            ConcretePipeBlueprint(
                type="PipeLLM",
                output="Text",
            )  # type: ignore[call-arg]
        assert "pipe_category" in str(exc_info.value).lower() or "pipe_category" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            ConcretePipeBlueprint(
                type="PipeLLM",
                pipe_category="PipeOperator",
            )  # type: ignore[call-arg]
        assert "output" in str(exc_info.value).lower()
