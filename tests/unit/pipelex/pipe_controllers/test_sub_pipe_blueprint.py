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
