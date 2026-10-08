"""Which document engine prints a `PipeDocGen` step: the `doc_gen` model it names, or the deck's default for it.

An engine is a model of the `doc_gen` family, declared with the sources it prints from as its `inputs` and its format
as its `outputs`, in the kit's `internal.toml` for the built-in engine or by the plugin that ships it for the others,
and its worker is registered by a plugin. A step may name one in its
`model`; a step that names none prints on the model deck's default for its format and source. The same resolution
runs when the method loads, so a step no engine here can print is refused before a run spends anything, and when
the step runs, where the resolved handle rides into the print stage as its routing key.

A missing engine is refused naming its remedy. Core knows the name of the built-in engine, `reportlab-pdf`, and the
names of the engines the Pipelex document generation plugin declares when it loads, so a step that asks for one
this installation does not declare is told to run `pipelex update` or to install the plugin, rather than that its
model is unknown.
"""

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenModelChoice, DocGenSetting
from pipelex.cogt.doc_gen.exceptions import KNOWN_DOC_GEN_MODEL_NAMES, DocGenEngineGap, DocGenEngineMissingError, DocGenModelCapabilityError
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import ModelReferenceKind, ensure_model_reference, write_model_handle
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
            gap=DocGenEngineGap.NOT_REGISTERED,
            doc_gen_format=doc_gen_format,
            source=source,
            model=inference_model.name,
            sdk=inference_model.sdk,
            pipe_code=pipe_code,
        )


def _refuse_undeclared_known_engine(*, model_handle: str, doc_gen_format: DocGenFormat, source: DocGenSource, pipe_code: str | None) -> None:
    """Refuse the built-in engine or one of the plugin's, named by its model name, where this installation does not declare it.

    Only these names have a remedy to name: the plugin declares its own engines, and `pipelex update` refreshes the
    kit's `internal.toml`, which declares the built-in one. Any other handle is left to the deck's own checks.

    Raises:
        DocGenEngineMissingError: the handle is a known engine name the model deck does not serve.
    """
    if model_handle not in KNOWN_DOC_GEN_MODEL_NAMES:
        return
    if get_model_deck().get_optional_inference_model(model_handle=model_handle, model_type=ModelType.DOC_GEN) is not None:
        return
    raise DocGenEngineMissingError(
        gap=DocGenEngineGap.NOT_DECLARED,
        doc_gen_format=doc_gen_format,
        source=source,
        model=model_handle,
        sdk=None,
        pipe_code=pipe_code,
    )


def require_doc_gen_engine_declared(
    *,
    doc_gen_choice: DocGenModelChoice,
    doc_gen_format: DocGenFormat,
    source: DocGenSource,
    pipe_code: str | None,
) -> None:
    """Refuse a choice that names the built-in engine or one of the plugin's directly, where this installation does not declare it.

    Runs before the deck resolves the choice, which would otherwise refuse such a name as an unknown model and name
    no remedy. An alias, a waterfall or a preset resolves through the deck first, and the model it lands on is
    checked by `get_doc_gen_inference_model`.

    Raises:
        DocGenEngineMissingError: the choice is a known engine name the model deck does not serve.
    """
    model_handle: str
    if isinstance(doc_gen_choice, DocGenSetting):
        model_handle = doc_gen_choice.model
    else:
        ref = ensure_model_reference(doc_gen_choice)
        match ref.kind:
            case ModelReferenceKind.HANDLE:
                model_handle = ref.name
            case ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL | ModelReferenceKind.PRESET:
                return
    _refuse_undeclared_known_engine(model_handle=model_handle, doc_gen_format=doc_gen_format, source=source, pipe_code=pipe_code)


def get_doc_gen_inference_model(
    *,
    model_handle: str,
    doc_gen_format: DocGenFormat,
    source: DocGenSource,
    pipe_code: str | None,
) -> InferenceModelSpec:
    """The `doc_gen` model a handle resolves to, refusing a known engine this installation does not declare with its remedy.

    Raises:
        DocGenEngineMissingError: the handle is the built-in engine or one of the plugin's, and the deck does not serve it.
        ModelNotFoundError: any other handle that resolves to no model served here.
    """
    _refuse_undeclared_known_engine(model_handle=model_handle, doc_gen_format=doc_gen_format, source=source, pipe_code=pipe_code)
    return get_model_deck().get_required_inference_model(model_handle=model_handle, model_type=ModelType.DOC_GEN)


def resolve_doc_gen_setting(
    *,
    doc_gen_choice: DocGenModelChoice | None,
    doc_gen_format: DocGenFormat,
    source: DocGenSource,
    pipe_code: str | None,
) -> DocGenSetting:
    """The engine that prints a step, pinned to the model handle it resolves to, checked to print the step here.

    Raises:
        DocGenEngineMissingError: the deck names no default for the step and the step names no engine, the engine is
            the built-in one or one of the plugin's and this installation does not declare it, or no installed plugin
            registers the engine.
        ModelChoiceNotFoundError: the step names a reference the deck does not define.
        ModelNotFoundError: the reference resolves to no model served here.
        DocGenModelCapabilityError: the engine does not print the step's format from its source.
    """
    model_deck = get_model_deck()
    resolved_choice = doc_gen_choice
    if resolved_choice is None:
        resolved_choice = model_deck.get_doc_gen_choice_default(doc_gen_format=doc_gen_format, source=source)
    if resolved_choice is None:
        raise DocGenEngineMissingError(
            gap=DocGenEngineGap.NO_DEFAULT, doc_gen_format=doc_gen_format, source=source, model=None, sdk=None, pipe_code=pipe_code
        )
    require_doc_gen_engine_declared(doc_gen_choice=resolved_choice, doc_gen_format=doc_gen_format, source=source, pipe_code=pipe_code)
    doc_gen_setting = model_deck.get_doc_gen_setting(doc_gen_choice=resolved_choice)
    inference_model = get_doc_gen_inference_model(
        model_handle=doc_gen_setting.model, doc_gen_format=doc_gen_format, source=source, pipe_code=pipe_code
    )
    if not prints_document(inference_model=inference_model, doc_gen_format=doc_gen_format, source=source):
        raise DocGenModelCapabilityError(doc_gen_format=doc_gen_format, source=source, model=inference_model.name, pipe_code=pipe_code)
    require_doc_gen_engine_installed(inference_model=inference_model, doc_gen_format=doc_gen_format, source=source, pipe_code=pipe_code)
    # Pinned as a reference that parses back to the resolved handle, whatever its spelling, since every lookup reads it again.
    resolved_handle = write_model_handle(name=inference_model.name)
    if resolved_handle != doc_gen_setting.model:
        doc_gen_setting = doc_gen_setting.model_copy(update={"model": resolved_handle})
    return doc_gen_setting
