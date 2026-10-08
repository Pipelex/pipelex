"""A kernel op pins its setting to the handle it resolved, written so the leaf lookup reads that same handle back.

A served handle may be spelled like a reference (`@named`): pinned bare, the leaf lookup would read it as the alias
`named`, or as nothing at all, rather than as the model the op resolved.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.doc_gen.doc_gen_engine import resolve_doc_gen_setting
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.kernel.judgment_ops import resolve_judgment_setting
from pipelex.kernel.search_ops import resolve_search_setting
from pipelex.system.runtime import ProblemReaction

_LITERAL_HANDLE = "@named"

# The deck field prefix of each model type's bindings (`search_aliases`, ...).
_BINDING_PREFIXES: dict[ModelType, str] = {
    ModelType.SEARCH: "search",
    ModelType.JUDGMENT: "judgment",
    ModelType.DOC_GEN: "doc_gen",
}


def _model_spec(*, name: str, model_type: ModelType) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test_backend",
        name=name,
        sdk="test_sdk",
        model_type=model_type,
        model_id=f"test_model_{name}",
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
        # A document engine declares the source it prints from and the format it prints.
        inputs=[str(DocGenSource.LAYOUT)],
        outputs=[str(DocGenFormat.PDF)],
    )


def _make_deck(*, model_type: ModelType, is_alias_colliding: bool) -> ModelDeck:
    """A deck serving `@named` and `other` as `model_type`, with an alias bound to `@named`, and optionally an alias `named` bound to `other`."""
    prefix = _BINDING_PREFIXES[model_type]
    aliases = {"to-literal": f"handle:{_LITERAL_HANDLE}"}
    if is_alias_colliding:
        aliases["named"] = "other"
    bindings: dict[str, Any] = {f"{prefix}_aliases": aliases}
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(
            model_specs=[
                _model_spec(name=_LITERAL_HANDLE, model_type=model_type),
                _model_spec(name="other", model_type=model_type),
            ]
        ),
        llm_default_temperature=0.7,
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="gpt-4o-mini", temperature=0.7),
            for_object=LLMSetting(model="gpt-4o-mini", temperature=0.1),
        ),
        extract_choice_default="extract-engine",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_choice_default="img-painter",
        search_choice_default="@default-search",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
        **bindings,
    )


def _pinned_model(*, mocker: MockerFixture, model_deck: ModelDeck, model_type: ModelType, choice: str) -> str:
    """The model the op pins its setting to, the deck patched where the op reads it."""
    match model_type:
        case ModelType.SEARCH:
            mocker.patch("pipelex.kernel.search_ops.get_model_deck", return_value=model_deck)
            return resolve_search_setting(search_choice=choice).model
        case ModelType.JUDGMENT:
            mocker.patch("pipelex.kernel.judgment_ops.get_model_deck", return_value=model_deck)
            return resolve_judgment_setting(judgment_choice=choice, pipe_code="judge").model
        case ModelType.DOC_GEN:
            mocker.patch("pipelex.cogt.doc_gen.doc_gen_engine.get_model_deck", return_value=model_deck)
            mocker.patch(
                "pipelex.cogt.doc_gen.doc_gen_engine.get_inference_backend_registry", return_value=mocker.Mock(has=mocker.Mock(return_value=True))
            )
            return resolve_doc_gen_setting(
                doc_gen_choice=choice, doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, pipe_code="print"
            ).model
        case ModelType.LLM | ModelType.TEXT_EXTRACTOR | ModelType.IMG_GEN:
            pytest.fail(f"{model_type} has no op pinning its resolved handle")


class TestResolvedHandlePinning:
    @pytest.mark.parametrize("model_type", [ModelType.SEARCH, ModelType.JUDGMENT, ModelType.DOC_GEN])
    @pytest.mark.parametrize("is_alias_colliding", [False, True], ids=["no-colliding-alias", "colliding-alias"])
    @pytest.mark.parametrize("choice", [f"handle:{_LITERAL_HANDLE}", "@to-literal"], ids=["literal-handle", "alias-to-the-literal-handle"])
    def test_the_leaf_lookup_reads_back_the_handle_the_op_resolved(
        self,
        mocker: MockerFixture,
        model_type: ModelType,
        is_alias_colliding: bool,
        choice: str,
    ) -> None:
        model_deck = _make_deck(model_type=model_type, is_alias_colliding=is_alias_colliding)

        pinned_model = _pinned_model(mocker=mocker, model_deck=model_deck, model_type=model_type, choice=choice)

        assert pinned_model == f"handle:{_LITERAL_HANDLE}"
        assert model_deck.get_required_inference_model(model_handle=pinned_model, model_type=model_type).name == _LITERAL_HANDLE

    @pytest.mark.parametrize("model_type", [ModelType.SEARCH, ModelType.JUDGMENT, ModelType.DOC_GEN])
    def test_an_ordinary_handle_is_pinned_bare(self, mocker: MockerFixture, model_type: ModelType) -> None:
        model_deck = _make_deck(model_type=model_type, is_alias_colliding=False)
        model_deck_with_alias = model_deck.model_copy(update={f"{_BINDING_PREFIXES[model_type]}_aliases": {"best": "other"}})

        pinned_model = _pinned_model(mocker=mocker, model_deck=model_deck_with_alias, model_type=model_type, choice="@best")

        assert pinned_model == "other"
