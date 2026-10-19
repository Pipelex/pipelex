"""Pin: a method of a host's own library directories that refuses to load is the deployment's fault, not the caller's input.

A server loads its library directories beside a request's bundles, and those directories are the deployment's, not the
caller's (`library_dirs_are_callers` False). A pipe there that its factory refuses, or that names a model the deck does
not define, used to be answered as the caller's invalid input, a 422 carrying the host library's own text. It is now
`pipelex.config.invalid`, an operator fault, whose message is the operator's diagnostics alone. The same refusal in the
caller's own content stays the caller's: a 422 verdict with one item.
"""

import json
from pathlib import Path

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipeline.exceptions import HostLibraryLoadRefusalError, ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle

# Text of the host library's bundles that no caller's answer may carry.
_HOST_TEXT = "almanac"

# A factory refusal: a PipeExtract whose input is neither an image nor a document.
_FACTORY_REFUSAL_BUNDLE = """
domain      = "host_almanac_reading"
description = "Read the pages of a tide almanac"

[pipe.read_almanac_pages]
type        = "PipeExtract"
description = "Read each page of the tide almanac"
inputs      = { almanac_text = "Text" }
output      = "Page[]"
"""

# A model-choice refusal: a PipeLLM naming a model the deck does not define.
_MODEL_CHOICE_REFUSAL_BUNDLE = """
domain      = "host_almanac_notes"
description = "Write notes about a tide almanac"

[pipe.write_almanac_note]
type        = "PipeLLM"
description = "Write a note about the tide almanac"
inputs      = { almanac_text = "Text" }
output      = "Text"
model       = "gpt-5.6-almanac-lunna"
prompt      = "Write a note about this tide almanac: $almanac_text"
"""

# The caller's own bundle, which is valid.
_CALLER_BUNDLE = """
domain      = "caller_greeting"
description = "Greet someone"
main_pipe   = "greet"

[pipe.greet]
type        = "PipeCompose"
description = "Greet someone by name"
inputs      = { name = "Text" }
output      = "Text"
template    = "Hello $name"
"""

_REFUSING_BUNDLES = pytest.mark.parametrize(
    "refusing_bundle",
    [_FACTORY_REFUSAL_BUNDLE, _MODEL_CHOICE_REFUSAL_BUNDLE],
    ids=["factory_refusal", "model_choice_refusal"],
)


def _host_library_dir(*, directory: Path, refusing_bundle: str) -> Path:
    library_dir = directory / "host_library"
    library_dir.mkdir()
    (library_dir / "almanac.mthds").write_text(refusing_bundle, encoding="utf-8")
    return library_dir


def _assert_is_the_deployments_fault(*, error: PipelexError) -> None:
    caller = error.to_problem(view=ProblemView.CALLER)
    assert caller.code == PipelexErrorCode.CONFIG_INVALID
    assert caller.domain == ProblemDomain.OPERATOR
    assert caller.errors is None
    assert error_code_spec(PipelexErrorCode.CONFIG_INVALID).status == 500
    # The operator reads which method refused; the caller reads none of the host library's text.
    operator = error.to_problem(view=ProblemView.OPERATOR)
    assert operator.diagnostics is not None
    assert _HOST_TEXT in operator.diagnostics.message
    assert _HOST_TEXT not in json.dumps(caller.to_wire())


@pytest.mark.asyncio(loop_scope="class")
class TestHostLibraryLoadRefusals:
    @_REFUSING_BUNDLES
    async def test_a_host_library_refusal_at_validation_is_the_deployments_fault(self, tmp_path: Path, refusing_bundle: str) -> None:
        """Validating the caller's bundle beside a host library that refuses: no verdict, an operator fault."""
        library_dir = _host_library_dir(directory=tmp_path, refusing_bundle=refusing_bundle)

        with pytest.raises(HostLibraryLoadRefusalError) as exc_info:
            await validate_bundle(mthds_contents=[_CALLER_BUNDLE], library_dirs=[library_dir])

        _assert_is_the_deployments_fault(error=exc_info.value)

    @_REFUSING_BUNDLES
    async def test_a_host_library_refusal_at_run_is_the_deployments_fault(self, tmp_path: Path, refusing_bundle: str) -> None:
        """Running the caller's bundle beside a host library that refuses: an operator fault, never the caller's input."""
        library_dir = _host_library_dir(directory=tmp_path, refusing_bundle=refusing_bundle)

        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol(library_dirs=[str(library_dir)]).execute(
                pipe_code="greet", mthds_contents=[_CALLER_BUNDLE], inputs={"name": "Ada"}
            )

        assert not isinstance(exc_info.value, ValidateBundleError)
        _assert_is_the_deployments_fault(error=exc_info.value)

    @_REFUSING_BUNDLES
    async def test_the_same_refusal_in_the_callers_content_stays_the_callers(self, refusing_bundle: str) -> None:
        """The refusal in the caller's own content: a 422 verdict with one input item, as before."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[refusing_bundle])

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        assert problem.domain == ProblemDomain.METHOD
        assert error_code_spec(CoreCode.METHOD_INVALID).status == 422
        assert len(problem.errors or []) == 1
        assert len(exc_info.value.validation_error_items()) == 1

    @_REFUSING_BUNDLES
    async def test_a_refusal_in_the_callers_own_library_dirs_stays_the_callers(self, tmp_path: Path, refusing_bundle: str) -> None:
        """A local run whose library directories are the caller's own: the refusal is the caller's invalid bundle."""
        library_dir = _host_library_dir(directory=tmp_path, refusing_bundle=refusing_bundle)

        with pytest.raises(ValidateBundleError) as exc_info:
            await PipelexMTHDSProtocol(library_dirs=[str(library_dir)], library_dirs_are_callers=True).execute(
                pipe_code="greet", mthds_contents=[_CALLER_BUNDLE], inputs={"name": "Ada"}
            )

        assert exc_info.value.to_problem(view=ProblemView.CALLER).code == CoreCode.METHOD_INVALID
