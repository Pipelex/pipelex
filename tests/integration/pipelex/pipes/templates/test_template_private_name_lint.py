"""Template private-name lint: a template that reads a name starting with an underscore, other than an
input's metadata fields, is a typed validation error (`TEMPLATE_PRIVATE_NAME`) naming the pipe and the
template. The template sandbox refuses the same reads at render time; this lint locates them at load.
"""

from typing import Callable

import pytest
from pydantic import ValidationError

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.mthds_parsing.handle_pipe_errors import extract_wrapped_pipe_validation_error
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.validation_error_types import PipeValidationErrorType

_DOMAIN_CODE = "test_template_private_name_lint"

_CONSTRUCT_MTHDS = """
domain = "test_template_private_name_construct"
main_pipe = "file_the_receipt"

[concept.FiledReceipt]
description = "A receipt filed under the name it came in with"

[concept.FiledReceipt.structure]
filed_under = { type = "text", description = "The name the receipt was filed under", required = true }

[pipe.file_the_receipt]
type = "PipeCompose"
description = "File a receipt under the name it came in with"
inputs = { receipt = "Text" }
output = "FiledReceipt"

[pipe.file_the_receipt.construct]
filed_under = { template = "{{ receipt._stuff.stuff_name }}" }
"""

_CONSTRUCT_FROM_DUNDER_MTHDS = """
domain = "test_construct_from_private_segment"
main_pipe = "copy_the_environment"

[concept.Note]
description = "A note"

[concept.Note.structure]
body = { type = "text", description = "The body", required = true }

[concept.Copied]
description = "Whatever a path reached"

[concept.Copied.structure]
data = { type = "dict", key_type = "text", value_type = "text", description = "Anything", required = true }

[pipe.copy_the_environment]
type = "PipeCompose"
description = "Walk from an input into the process environment"
inputs = { note = "Note" }
output = "Copied"

[pipe.copy_the_environment.construct]
data = { from = "note.__class__.__init__.__globals__.sys.modules.os.environ" }
"""


def _make_pipe_llm(*, prompt: str, system_prompt: str | None = None) -> PipeLLM:
    return PipeFactory[PipeLLM].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="private_name_llm",
        blueprint=PipeLLMBlueprint(
            description="Private-name lint test pipe",
            inputs={"contract": "Text"},
            output="Text",
            prompt=prompt,
            system_prompt=system_prompt,
        ),
    )


def _assert_private_name_error(error: ValidationError, *, pipe_code: str, refused_name: str, template_label: str) -> PipeValidationError:
    wrapped = extract_wrapped_pipe_validation_error(error.errors()[0])
    assert wrapped is not None, "expected a wrapped PipeValidationError"
    assert wrapped.error_type == PipeValidationErrorType.TEMPLATE_PRIVATE_NAME
    assert wrapped.pipe_code == pipe_code
    assert f"'{refused_name}'" in str(wrapped)
    assert f"the {template_label} of pipe '{pipe_code}'" in str(wrapped)
    return wrapped


class TestTemplatePrivateNameLint:
    @pytest.mark.parametrize(
        ("topic", "prompt", "refused_name"),
        [
            ("raw_stuff_by_dot", "Summarise {{ contract._stuff }}", "_stuff"),
            ("raw_content_by_dot", "Summarise {{ contract._content }}", "_content"),
            ("dunder_chain", "{{ contract.__class__.__mro__ }} $contract", "__class__"),
        ],
    )
    def test_prompt_reading_a_private_name_is_rejected(self, topic: str, prompt: str, refused_name: str, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            _make_pipe_llm(prompt=prompt)
        wrapped = _assert_private_name_error(exc_info.value, pipe_code="private_name_llm", refused_name=refused_name, template_label="prompt")
        assert "_stuff_name" in str(wrapped), f"{topic}: the message lists the metadata fields a template may read"

    def test_system_prompt_is_linted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            _make_pipe_llm(prompt="Summarise $contract", system_prompt="You know {{ contract._stuff }}")
        _assert_private_name_error(exc_info.value, pipe_code="private_name_llm", refused_name="_stuff", template_label="system_prompt")

    def test_bracketed_key_is_left_to_the_render(self, load_empty_library: Callable[[], None]):
        """A bracketed key may be a plain dict's data (`record['_id']`), which only the render can tell."""
        load_empty_library()
        pipe_llm = _make_pipe_llm(prompt="Summarise {{ contract['_id'] }} $contract")
        assert pipe_llm.code == "private_name_llm"

    def test_metadata_fields_are_accepted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        pipe_llm = _make_pipe_llm(
            prompt="{{ contract._stuff_name }} {{ contract._content_class }} {{ contract._concept_code }} {{ contract._stuff_code }} $contract",
        )
        assert pipe_llm.code == "private_name_llm"

    def test_condition_expression_is_linted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeCondition].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="private_name_condition",
                blueprint=PipeConditionBlueprint(
                    description="Condition reaching for the wrapped stuff",
                    inputs={"verdict": "Text"},
                    output="Text",
                    expression="verdict._stuff.stuff_name",
                    outcomes={"yes": "continue"},
                    default_outcome="continue",
                ),
            )
        _assert_private_name_error(exc_info.value, pipe_code="private_name_condition", refused_name="_stuff", template_label="expression")

    def test_compose_template_is_linted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeCompose].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="private_name_compose",
                blueprint=PipeComposeBlueprint(
                    description="Compose reaching for the raw content",
                    inputs={"note": "Text"},
                    output="Text",
                    template="note: {{ note._content }}",
                ),
            )
        _assert_private_name_error(exc_info.value, pipe_code="private_name_compose", refused_name="_content", template_label="template")

    def test_search_prompt_is_linted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeSearch].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="private_name_search",
                blueprint=PipeSearchBlueprint(
                    description="Search reaching for the wrapped stuff",
                    inputs={"topic": "Text"},
                    output="SearchResult[]",
                    prompt="latest news about {{ topic._stuff }}",
                ),
            )
        _assert_private_name_error(exc_info.value, pipe_code="private_name_search", refused_name="_stuff", template_label="prompt")

    def test_img_gen_negative_prompt_is_linted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="private_name_img_gen",
                blueprint=PipeImgGenBlueprint(
                    description="Image prompt reaching for the wrapped stuff",
                    inputs={"style": "Text"},
                    output="Image",
                    prompt="a landscape in the style of $style",
                    negative_prompt="nothing like {{ style._stuff }}",
                ),
            )
        _assert_private_name_error(exc_info.value, pipe_code="private_name_img_gen", refused_name="_stuff", template_label="negative_prompt")

    @pytest.mark.asyncio(loop_scope="class")
    async def test_construct_field_template_is_linted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_CONSTRUCT_MTHDS])
        items = exc_info.value.to_error_report().validation_errors or []
        assert [(item.category, item.error_type) for item in items] == [
            (ValidationErrorCategory.PIPE_VALIDATION, PipeValidationErrorType.TEMPLATE_PRIVATE_NAME)
        ]
        assert "construct field 'filed_under'" in (items[0].message or "")

    @pytest.mark.asyncio(loop_scope="class")
    async def test_construct_from_path_with_a_private_segment_is_rejected(self, load_empty_library: Callable[[], None]):
        """A `from` path is walked with getattr at run time: a dunder segment would copy the process environment."""
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_CONSTRUCT_FROM_DUNDER_MTHDS])
        items = exc_info.value.to_error_report().validation_errors or []
        assert len(items) == 1
        assert "reads '__class__', a name starting with an underscore" in (items[0].message or "")
