"""Pin: a pipe factory's refusal is a verdict.

A pipe factory refuses a blueprint it cannot build, such as a ``PipeExtract`` whose input is neither an
image nor a document. Its error classes declared no domain, so the validation translation did not
recognise them and they escaped every validator raw. They are now the method's fault, so the refusal
validates to one item located on the pipe and its file, which reads the sentence its code renders; the
refusal's own message, naming the input and the next step, stays on the verdict's cause chain. The agent
CLI's ``validate_all_core`` translated its load only after the failed library was torn down, so its items
lost their file; they keep it now.
"""

import json
from pathlib import Path

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, StepKind

from pipelex.base_exceptions import PipelexError, ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.validate._validate_core import validate_all_core
from pipelex.core.pipes.exceptions import PipeLoadRefusalError
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.pipe_controllers.condition.exceptions import PipeConditionFactoryError
from pipelex.pipe_controllers.parallel.exceptions import PipeParallelFactoryError
from pipelex.pipe_operators.compose.exceptions import PipeComposeFactoryError
from pipelex.pipe_operators.extract.exceptions import PipeExtractFactoryError
from pipelex.pipe_operators.llm.exceptions import PipeLLMFactoryError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle

_DOMAIN = "almanac_reading"

_TEXT_INPUT_EXTRACT_BUNDLE = f"""
domain      = "{_DOMAIN}"
description = "Read the pages of a tide almanac"
main_pipe   = "read_almanac_pages"

[pipe.read_almanac_pages]
type        = "PipeExtract"
description = "Read each page of the tide almanac"
inputs      = {{ almanac_text = "Text" }}
output      = "Page[]"
"""

_SEQUENCE_OUTPUT_MISMATCH_BUNDLE = f"""
domain      = "{_DOMAIN}"
description = "Read the pages of a tide almanac"

[pipe.summarize_almanac]
type        = "PipeSequence"
description = "Summarize the tide almanac"
inputs      = {{ almanac_text = "Text" }}
output      = "Text[]"
steps       = [{{ pipe = "write_summary", result = "summary" }}]

[pipe.write_summary]
type        = "PipeLLM"
description = "Write the summary of the tide almanac"
inputs      = {{ almanac_text = "Text" }}
output      = "Text"
prompt      = "Summarize this tide almanac: $almanac_text"
"""

_INHERITED_SYSTEM_PROMPT_BUNDLE = """
domain        = "almanac_notes"
description   = "Write notes about a tide almanac"
system_prompt = "You write for {% if %} harbour users."

[pipe.write_note]
type        = "PipeLLM"
description = "Write a note about the tide almanac"
inputs      = { almanac_text = "Text" }
output      = "Text"
prompt      = "Write a note about this tide almanac: $almanac_text"
"""


_NEXT_STEP = "Declare this input as an Image or a Document, or as a concept that refines one of them."

_FACTORY_REFUSAL_CLASSES: list[type[PipelexError]] = [
    PipeLLMFactoryError,
    PipeComposeFactoryError,
    PipeExtractFactoryError,
    PipeConditionFactoryError,
    PipeParallelFactoryError,
]


def _write_bundle(*, directory: Path, content: str = _TEXT_INPUT_EXTRACT_BUNDLE) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(content, encoding="utf-8")
    return bundle_path


def _assert_located_extract_item(*, items: list[ValidationErrorItem], bundle_path: Path) -> None:
    (item,) = items
    assert item.category == ValidationErrorCategory.PIPE_VALIDATION
    assert item.pipe_code == "read_almanac_pages"
    assert item.domain_code == _DOMAIN
    assert item.source == str(bundle_path)
    # The code's sentence names the refused input: the parameters the raise site gives.
    assert "almanac_text" in item.message


def _caller_payload(error: ValidateBundleError) -> str:
    """What a caller reads of a verdict: its problem in the caller's view and its validation items."""
    items = [item.model_dump(mode="json", exclude_none=True) for item in error.validation_error_items()]
    return json.dumps({"problem": error.to_problem(view=ProblemView.CALLER).to_wire(), "validation_errors": items})


@pytest.mark.asyncio(loop_scope="class")
class TestFactoryRefusalVerdicts:
    @pytest.mark.parametrize("error_class", _FACTORY_REFUSAL_CLASSES, ids=[error_class.__name__ for error_class in _FACTORY_REFUSAL_CLASSES])
    async def test_factory_refusal_is_the_method_s_fault(self, error_class: type[PipelexError]) -> None:
        problem = error_class("The pipe cannot be built from this blueprint.").to_problem(view=ProblemView.CALLER)

        assert problem.domain == ProblemDomain.METHOD
        assert problem.next_step.kind == StepKind.CHANGE_METHOD
        assert error_code_spec(CoreCode(problem.code)).status == 422

    async def test_validate_bundle_locates_the_extract_refusal_with_its_next_step(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[tmp_path])

        assert isinstance(raised.value.__cause__, PipeLoadRefusalError)
        assert isinstance(raised.value.__cause__.__cause__, PipeExtractFactoryError)
        _assert_located_extract_item(items=raised.value.validation_error_items(), bundle_path=bundle_path)
        problem = raised.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        (problem_item,) = problem.errors or []
        assert problem_item.code == CoreCode.METHOD_SCHEMA_VIOLATION
        # The factory's own message, naming the input and the next step, is on the chain for the operator.
        refusal_message = str(raised.value.__cause__.__cause__)
        assert "The input 'almanac_text' of PipeExtract 'read_almanac_pages' is a native.Text" in refusal_message
        assert _NEXT_STEP in refusal_message

    async def test_agent_validate_all_locates_a_wiring_refusal_on_its_file(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_SEQUENCE_OUTPUT_MISMATCH_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_all_core(library_dirs=[tmp_path])

        (item,) = raised.value.validation_error_items() or []
        assert item.pipe_code == "summarize_almanac"
        assert item.source == str(bundle_path)

    async def test_an_inherited_system_prompt_refusal_quotes_no_token_of_it(self, tmp_path: Path) -> None:
        content = _INHERITED_SYSTEM_PROMPT_BUNDLE.replace("You write for {% if %} harbour users.", "You write for {% quay_ledger %} harbour users.")
        bundle_path = _write_bundle(directory=tmp_path, content=content)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[tmp_path])

        # Jinja2's diagnosis names the unknown tag; the verdict must not.
        assert "quay_ledger" not in _caller_payload(raised.value)

    async def test_an_inherited_system_prompt_refusal_names_the_domain(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_INHERITED_SYSTEM_PROMPT_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[tmp_path])

        (item,) = raised.value.validation_error_items() or []
        assert item.pipe_code == "write_note"
        assert item.source == str(bundle_path)
        # The item reads the code's sentence over the pipe and the parse failure; the refusal names the domain for the operator.
        assert "'write_note'" in item.message
        assert "line 1" in item.message
        refusal_message = str(raised.value.__cause__.__cause__ if raised.value.__cause__ else None)
        assert "system prompt of domain 'almanac_notes', which it inherits, for pipe 'write_note' in domain" in refusal_message
        assert refusal_message.endswith("it does not parse at line 1 of that prompt.")
        # The inherited prompt may be a host's, so its text never rides the verdict the caller reads.
        assert "harbour users" not in _caller_payload(raised.value)
