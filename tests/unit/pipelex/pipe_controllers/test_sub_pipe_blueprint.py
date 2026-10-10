from typing import Any

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
        assert "The step running pipe 'process' carries both `nb_output` and `multiple_output`: a step sets at most one of them." in str(
            exc_info.value
        )
        assert "PipeStepBlueprint" not in str(exc_info.value)

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
        assert "The step running pipe 'process' carries `batch_over` without `batch_as`:" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process",
                batch_as="item",
            )
        assert "The step running pipe 'process' carries `batch_as` without `batch_over`:" in str(exc_info.value)

    def test_rejects_batch_over_same_as_batch_as(self):
        """SubPipeBlueprint rejects batch_as == batch_over."""
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(
                pipe="process_item",
                result="processed",
                batch_over="items",
                batch_as="items",
            )

        refusal = exc_info.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(refusal, PipeValidationError)
        assert refusal.error_type == PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
        assert "The `batch_as` of the step running pipe 'process_item' is 'items', the same name as its `batch_over`:" in str(refusal)

    @pytest.mark.parametrize(
        "blueprint_fields",
        [
            pytest.param({"nb_output": 3, "multiple_output": True}, id="both-counts"),
            pytest.param({"batch_over": "items"}, id="batch-over-alone"),
            pytest.param({"batch_as": "item"}, id="batch-as-alone"),
            pytest.param({"batch_over": "items", "batch_as": "items"}, id="batch-as-is-batch-over"),
            pytest.param({"batch_over": "catalog..pages", "batch_as": "page"}, id="a-dotted-batch-over-that-is-not-a-path"),
        ],
    )
    def test_a_refusal_names_the_step_never_its_pipe_as_the_faulty_one(self, blueprint_fields: dict[str, Any]) -> None:
        """The faulty fields belong to the step, held by the sequence or parallel the error locates, not to the pipe the step runs."""
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint.model_validate({"pipe": "write_index_line", **blueprint_fields})

        message = str(exc_info.value)
        assert "the step running pipe 'write_index_line'" in message.lower()
        assert "In pipe" not in message

    def test_a_dotted_batch_over_that_is_not_a_path_is_named_on_its_step(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(pipe="write_index_line", batch_over="catalog..pages", batch_as="page")

        refusal = exc_info.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(refusal, PipeValidationError)
        assert refusal.error_type == PipeValidationErrorType.BINDING_STEP_INVALID
        assert refusal.variable_names == ["catalog..pages"]
        assert str(refusal).startswith(
            "The dotted `batch_over` 'catalog..pages' of the step running pipe 'write_index_line' is not a path. A dotted `batch_over` binds"
        )

    @pytest.mark.parametrize(
        "stored_name",
        [
            pytest.param("Pages", id="pascal-case"),
            pytest.param("catalog.pages", id="dotted"),
            pytest.param("_bound_catalog_pages", id="the-reserved-prefix"),
            pytest.param("_draft", id="underscore-led"),
            pytest.param("2nd_pages", id="digit-led"),
            pytest.param("page-views", id="hyphenated"),
            pytest.param("...", id="dots-only"),
        ],
    )
    @pytest.mark.parametrize("field_name", ["result", "batch_as"])
    def test_a_stored_name_that_is_not_a_plain_input_name_is_refused_as_invalid_input_name(self, field_name: str, stored_name: str) -> None:
        """A step stores its `result`, and each item under `batch_as`, for a later pipe to read through an input, so both are plain names."""
        step_fields: dict[str, str] = {"result": "descriptions", "batch_over": "pages", "batch_as": "page", field_name: stored_name}
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint.model_validate({"pipe": "describe_page", **step_fields})

        refusal = exc_info.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(refusal, PipeValidationError)
        assert refusal.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert refusal.variable_names == [stored_name]
        assert f"The `{field_name}` of the step running pipe 'describe_page', '{stored_name}', is not a plain input name" in str(refusal)

    @pytest.mark.parametrize(
        ("stored_name", "message_fragment"),
        [
            pytest.param("Pages", "Rename it to a plain name, such as 'pages',", id="pascal-case"),
            pytest.param("PagesOfTheCatalog", "Rename it to a plain name, such as 'pages_of_the_catalog',", id="a-longer-pascal-case-name"),
            pytest.param("catalog.pages", "cannot reach into a field with a dot. Rename it to a plain name, such as 'catalog_pages',", id="dotted"),
            pytest.param(
                "_bound_catalog_pages",
                "the `_bound_` prefix it starts with is reserved for the bound list of a dotted `batch_over`",
                id="the-reserved-prefix",
            ),
            pytest.param("_bound_catalog_pages", "Rename it to a plain name, such as 'catalog_pages',", id="the-reserved-prefix-suggestion"),
            pytest.param("page-views", "Rename it to a plain name, such as 'page_views',", id="hyphenated"),
            pytest.param("...", "Rename it to a plain name, and", id="no-suggestion"),
        ],
    )
    def test_the_refusal_explains_the_form_and_suggests_a_plain_name(self, stored_name: str, message_fragment: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(pipe="describe_page", result=stored_name)

        assert message_fragment in str(exc_info.value)

    def test_a_plain_batch_over_taking_the_reserved_prefix_is_refused_as_invalid_input_name(self) -> None:
        """A plain `batch_over` reads a name rather than storing one, but never a name the runtime binds under its reserved prefix."""
        with pytest.raises(ValidationError) as exc_info:
            SubPipeBlueprint(pipe="describe_page", batch_over="_bound_catalog_pages", batch_as="page")

        refusal = exc_info.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(refusal, PipeValidationError)
        assert refusal.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert refusal.variable_names == ["_bound_catalog_pages"]
        message = str(refusal)
        assert "The `batch_over` of the step running pipe 'describe_page', '_bound_catalog_pages', takes the `_bound_` prefix" in message
        assert "reserved for the bound list of a dotted `batch_over`" in message
        assert "Choose another name, such as 'catalog_pages'." in message

    @pytest.mark.parametrize(
        "stored_name",
        [
            pytest.param("pages", id="a-plain-name"),
            pytest.param("bound_pages", id="the-prefix-without-its-underscore"),
            pytest.param("catalog_bound_pages", id="the-prefix-inside-the-name"),
            pytest.param("page2", id="a-digit-after-the-first-letter"),
        ],
    )
    def test_a_plain_stored_name_is_accepted(self, stored_name: str) -> None:
        blueprint = SubPipeBlueprint(pipe="describe_page", result=stored_name, batch_over="catalog_pages", batch_as=stored_name)

        assert blueprint.result == blueprint.batch_as == stored_name

    @pytest.mark.parametrize(
        "batch_over",
        [
            pytest.param("PagesOfTheCatalog", id="pascal-case"),
            pytest.param("_draft_pages", id="underscore-led-outside-the-reserved-prefix"),
        ],
    )
    def test_a_plain_batch_over_is_held_only_to_the_reserved_prefix(self, batch_over: str) -> None:
        """A plain `batch_over` reads a name rather than storing one, so the standard holds it only off the reserved prefix."""
        blueprint = SubPipeBlueprint(pipe="describe_page", batch_over=batch_over, batch_as="page")

        assert blueprint.batch_over == batch_over
