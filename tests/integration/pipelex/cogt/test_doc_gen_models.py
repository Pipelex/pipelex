import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_engine import prints_document
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import DocGenDeckBlueprint
from pipelex.runtime_hub import get_model_deck


class TestDocGenModels:
    def test_the_deck_names_an_engine_that_prints_every_step_a_format_can_make(self) -> None:
        """Every format and source a step can ask for has a default in the kit's deck, on a model that declares it prints them."""
        model_deck = get_model_deck()
        for doc_gen_format in DocGenFormat:
            for source in DocGenSource.possible_for(doc_gen_format=doc_gen_format):
                choice = model_deck.get_doc_gen_choice_default(doc_gen_format=doc_gen_format, source=source)
                assert choice is not None, f"no default engine for a {doc_gen_format} {source.desc}"
                doc_gen_setting = model_deck.get_doc_gen_setting(doc_gen_choice=choice)
                inference_model = model_deck.get_required_inference_model(model_handle=doc_gen_setting.model, model_type=ModelType.DOC_GEN)
                assert prints_document(inference_model=inference_model, doc_gen_format=doc_gen_format, source=source)

    def test_the_built_in_engine_is_the_default_for_a_pdf_without_a_template(self) -> None:
        model_deck = get_model_deck()
        choice = model_deck.get_doc_gen_choice_default(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        assert choice is not None
        assert model_deck.get_doc_gen_setting(doc_gen_choice=choice).model == "reportlab-pdf"

    def test_a_default_under_a_key_no_step_makes_is_refused_when_the_deck_loads(self) -> None:
        with pytest.raises(ValidationError, match="a pptx is never composed from the auto-layout"):
            DocGenDeckBlueprint.model_validate({"choice_defaults": {"pptx.layout": "python-pptx"}})
