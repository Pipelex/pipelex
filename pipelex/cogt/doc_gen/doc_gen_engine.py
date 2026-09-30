"""Which document engine prints a `PipeDocGen` step: the `doc_gen` model it names, or the deck's default for it.

An engine is a model of the `doc_gen` family, declared in a backend file with the sources it prints from as its
`inputs` and its format as its `outputs`, and its worker is registered by a plugin. A step may name one in its
`model`; a step that names none prints on the model deck's default for its format and source. The same resolution
runs when the method loads, so a step no engine here can print is refused before a run spends anything, and when
the step runs, where the resolved handle rides into the print stage as its routing key.
"""

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenModelChoice, DocGenSetting
from pipelex.cogt.doc_gen.exceptions import DocGenEngineMissingError, DocGenModelCapabilityError
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.runtime_hub import get_inference_backend_registry, get_model_deck


def prints_document(*, inference_model: InferenceModelSpec, doc_gen_format: DocGenFormat, source: DocGenSource) -> bool:
    """Whether a `doc_gen` model prints this format from this source, by the `inputs` and `outputs` it declares."""
    return str(source) in inference_model.inputs and str(doc_gen_format) in inference_model.outputs


def require_doc_gen_engine_installed(
    *,
    inference_model: InferenceModelSpec,
    doc_gen_format: DocGenFormat,
    source: DocGenSource,
    pipe_code: str | None,
) -> None:
    """Refuse a model whose engine no plugin registers in this runtime.

    The other model families find a missing worker only when they build it, at run time; a document engine is
    checked when the method loads too, so the refusal comes before any inference is spent.

    Raises:
        DocGenEngineMissingError: no installed plugin registers the model's sdk.
    """
    if not get_inference_backend_registry().has(family=InferenceFamily.DOC_GEN, sdk=inference_model.sdk):
        raise DocGenEngineMissingError(
            doc_gen_format=doc_gen_format, source=source, model=inference_model.name, sdk=inference_model.sdk, pipe_code=pipe_code
        )


def resolve_doc_gen_setting(
    *,
    doc_gen_choice: DocGenModelChoice | None,
    doc_gen_format: DocGenFormat,
    source: DocGenSource,
    pipe_code: str | None,
) -> DocGenSetting:
    """The engine that prints a step, pinned to the model handle it resolves to, checked to print the step here.

    Raises:
        DocGenEngineMissingError: the deck names no default for the step and the step names no engine, or no
            installed plugin registers the engine.
        ModelChoiceNotFoundError: the step names a reference the deck does not define.
        ModelNotFoundError: the reference resolves to no model served here.
        DocGenModelCapabilityError: the engine does not print the step's format from its source.
    """
    model_deck = get_model_deck()
    resolved_choice = doc_gen_choice
    if resolved_choice is None:
        resolved_choice = model_deck.get_doc_gen_choice_default(doc_gen_format=doc_gen_format, source=source)
    if resolved_choice is None:
        raise DocGenEngineMissingError(doc_gen_format=doc_gen_format, source=source, model=None, sdk=None, pipe_code=pipe_code)
    doc_gen_setting = model_deck.get_doc_gen_setting(doc_gen_choice=resolved_choice)
    inference_model = model_deck.get_required_inference_model(model_handle=doc_gen_setting.model, model_type=ModelType.DOC_GEN)
    if not prints_document(inference_model=inference_model, doc_gen_format=doc_gen_format, source=source):
        raise DocGenModelCapabilityError(doc_gen_format=doc_gen_format, source=source, model=inference_model.name, pipe_code=pipe_code)
    require_doc_gen_engine_installed(inference_model=inference_model, doc_gen_format=doc_gen_format, source=source, pipe_code=pipe_code)
    if inference_model.name != doc_gen_setting.model:
        doc_gen_setting = doc_gen_setting.model_copy(update={"model": inference_model.name})
    return doc_gen_setting
