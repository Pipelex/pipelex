import pytest
from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.validation_error_types import PipeValidationErrorType


class TestSubPipeBlueprint:
    def test_validate_multiple_output_correct(self):
        blueprint = SubPipeBlueprint(pipe="process")
        assert blueprint.pipe == "process"
        assert blueprint.nb_output is None
        assert blueprint.multiple_output is None

        blueprint = SubPipeBlueprint(pipe="process", nb_output=3)
        assert blueprint.nb_output == 3
        assert blueprint.multiple_output is None

        blueprint = SubPipeBlueprint(pipe="process", multiple_output=True)
        assert blueprint.nb_output is None
        assert blueprint.multiple_output is True

    def test_validate_multiple_output_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process",
                nb_output=3,
                multiple_output=True,
            )
        assert "PipeStepBlueprint should have no more than '1' of nb_output or multiple_output" in str(exc_info.value)

    def test_validate_batch_params_correct(self):
        blueprint = SubPipeBlueprint(pipe="process")
        assert blueprint.batch_over is None
        assert blueprint.batch_as is None

        blueprint = SubPipeBlueprint(
            pipe="process",
            batch_over="items",
            batch_as="item",
        )
        assert blueprint.batch_over == "items"
        assert blueprint.batch_as == "item"

    def test_validate_batch_params_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process",
                batch_over="items",
            )
        assert "When 'batch_over' is specified, 'batch_as' must also be provided" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process",
                batch_as="item",
            )
        assert "When 'batch_as' is specified, 'batch_over' must also be provided" in str(exc_info.value)

    def test_rejects_batch_over_same_as_batch_as(self):
        """SubPipeBlueprint rejects batch_as == batch_over."""
        with pytest.raises(ValidationError, match="batch_as"):
            SubPipeBlueprint(
                pipe="process_item",
                result="processed",
                batch_over="items",
                batch_as="items",
            )

    @pytest.mark.parametrize(
        ("step_fields", "field_name", "reserved_name"),
        [
            pytest.param({"result": "_bound_catalog_pages"}, "result", "_bound_catalog_pages", id="result"),
            pytest.param({"batch_over": "catalog_pages", "batch_as": "_bound_page"}, "batch_as", "_bound_page", id="batch-as"),
            pytest.param({"batch_over": "_bound_catalog_pages", "batch_as": "page"}, "batch_over", "_bound_catalog_pages", id="plain-batch-over"),
        ],
    )
    def test_a_name_taking_the_reserved_prefix_is_refused_as_invalid_input_name(
        self, step_fields: dict[str, str], field_name: str, reserved_name: str
    ) -> None:
        """The `_bound_` prefix is the runtime's, for the list a dotted `batch_over` binds in a caller's working memory."""
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint.model_validate({"pipe": "describe_page", **step_fields})

        refusal = exc_info.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(refusal, PipeValidationError)
        assert refusal.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert refusal.variable_names == [reserved_name]
        message = str(refusal)
        assert f"The `{field_name}` of the step running pipe 'describe_page', '{reserved_name}', takes the `_bound_` prefix" in message
        assert "reserved for the bound list of a dotted `batch_over`" in message
        assert "Choose another name" in message

    def test_the_refusal_suggests_the_name_without_the_prefix(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(pipe="describe_page", result="_bound_catalog_pages")

        assert "Choose another name, such as 'catalog_pages'." in str(exc_info.value)

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("bound_pages", id="the-prefix-without-its-underscore"),
            pytest.param("_draft", id="another-underscore-led-name"),
            pytest.param("catalog_bound_pages", id="the-prefix-inside-the-name"),
        ],
    )
    def test_a_name_outside_the_reserved_prefix_is_accepted(self, name: str) -> None:
        blueprint = SubPipeBlueprint(pipe="describe_page", result=name, batch_over="pages", batch_as=name)

        assert blueprint.result == blueprint.batch_as == name
