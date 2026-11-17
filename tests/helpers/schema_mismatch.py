"""Builders for the tests of `model.output_schema_mismatch`, which the operator that ran the generation completes.

Each operator's test drives a failure the worker raised through the step and builds the problem in the caller's view
under the unit suite's sweep, which fails a test whose problem lacks a parameter its code requires.
"""

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import ProblemView
from pipelex.providers.google.google_exceptions import GoogleLLMWorkerError
from pipelex.system.job_metadata import JobMetadata, RunMetadata

# The model the worker attributed the failure to, at its chokepoint.
WORKER_MODEL = "worker-model"

_DETAIL = "The model '{model}' gave an answer that does not fit the concept '{concept}', after the runtime asked again."


class _Answer(BaseModel):
    title: str


def make_validation_error() -> ValidationError:
    """Pydantic's refusal of an answer, which carries no model."""
    with pytest.raises(ValidationError) as exc_info:
        _Answer.model_validate({})
    return exc_info.value


def make_rendered_schema_mismatch() -> LLMCompletionError:
    """An answer instructor could not fit to the schema, rendered and attributed as an LLM worker leaves it."""
    metadata = ProviderErrorMetadata(
        provider=ProviderName.OPENAI,
        sdk_exception_type="ValidationError",
        message="1 validation error for Answer: title: Field required",
        status_code=None,
    )
    classification = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)
    rendered = render_inference_error(
        metadata=metadata,
        classification=classification,
        family=InferenceErrorFamily.LLM,
        model_desc=WORKER_MODEL,
        model_handle=WORKER_MODEL,
    )
    assert isinstance(rendered, LLMCompletionError)
    rendered.fill_model_and_provider(WORKER_MODEL, backend_name="openai")
    return rendered


def make_gemini_type_mismatch() -> GoogleLLMWorkerError:
    """Gemini's check that its parsed answer is of the schema's type, attributed as its worker leaves it."""
    error = GoogleLLMWorkerError("Google Gemini API returned an object that is not of type Answer: a dict")
    error.fill_model_and_provider(WORKER_MODEL, backend_name="google")
    return error


def make_job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run"))


def assert_names_model_and_concept(*, failure: PipelexError, model: str, concept: str) -> None:
    """The caller's problem reports the code with both parameters, and reads the registry's sentence naming them."""
    caller = failure.to_problem(view=ProblemView.CALLER)
    assert caller.code == CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH
    assert caller.params is not None
    params = caller.params.as_wire()
    assert params["model"] == model
    assert params["concept"] == concept
    assert caller.detail == _DETAIL.format(model=model, concept=concept)
