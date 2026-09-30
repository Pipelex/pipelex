import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_engine import prints_document
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource, doc_gen_choice_key
from pipelex.cogt.doc_gen.exceptions import BUILT_IN_DOC_GEN_CHOICE_KEY, BUILT_IN_DOC_GEN_MODEL, DOC_GEN_PLUGIN_MODEL_NAMES
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import DocGenDeckBlueprint
from pipelex.runtime_hub import get_model_deck


class TestDocGenModels:
    def test_the_kit_s_deck_declares_the_built_in_engine_s_default_only(self) -> None:
        """Open Pipelex declares a default for a pdf from the auto-layout alone: the plugin declares every other one when it loads."""
        model_deck = get_model_deck()
        declared_keys: list[str] = []
        for doc_gen_format in DocGenFormat:
            for source in DocGenSource.possible_for(doc_gen_format=doc_gen_format):
                if model_deck.get_doc_gen_choice_default(doc_gen_format=doc_gen_format, source=source) is not None:
                    declared_keys.append(doc_gen_choice_key(doc_gen_format=doc_gen_format, source=source))
        assert declared_keys == [BUILT_IN_DOC_GEN_CHOICE_KEY]

    def test_the_built_in_engine_is_the_default_for_a_pdf_without_a_template(self) -> None:
        model_deck = get_model_deck()
        choice = model_deck.get_doc_gen_choice_default(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        assert choice is not None
        doc_gen_setting = model_deck.get_doc_gen_setting(doc_gen_choice=choice)
        assert doc_gen_setting.model == BUILT_IN_DOC_GEN_MODEL
        inference_model = model_deck.get_required_inference_model(model_handle=doc_gen_setting.model, model_type=ModelType.DOC_GEN)
        assert prints_document(inference_model=inference_model, doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)

    def test_the_kit_declares_none_of_the_plugin_s_engines(self) -> None:
        """The plugin declares its own models: the kit's internal.toml names none of them, so an open install serves none."""
        model_deck = get_model_deck()
        doc_gen_models = {name for name, model in model_deck.inference_models.items() if model.model_type == ModelType.DOC_GEN}
        assert doc_gen_models == {BUILT_IN_DOC_GEN_MODEL}
        assert not DOC_GEN_PLUGIN_MODEL_NAMES & set(model_deck.inference_models)

    def test_a_default_under_a_key_no_step_makes_is_refused_when_the_deck_loads(self) -> None:
        with pytest.raises(ValidationError, match="a pptx is never composed from the auto-layout"):
            DocGenDeckBlueprint.model_validate({"choice_defaults": {"pptx.layout": "pipelex-pptx"}})
