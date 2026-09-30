from typing import Any, cast

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_engine import prints_document
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.exceptions import BUILT_IN_DOC_GEN_CHOICE_KEY, BUILT_IN_DOC_GEN_MODEL, DOC_GEN_PLUGIN_MODEL_NAMES
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.deck_manifest import KitManagedArea, kit_backends_dir, kit_deck_dir, list_managed_kit_files
from pipelex.cogt.models.model_deck import DocGenDeckBlueprint
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.runtime_hub import get_model_deck
from pipelex.tools.misc.toml_utils import load_toml_from_path


class TestDocGenModels:
    def test_the_kit_s_deck_declares_the_built_in_engine_s_default_only(self) -> None:
        """Open Pipelex declares a default for a pdf from the auto-layout alone: the plugin declares every other one when it loads.

        Read from the kit's deck files rather than the booted deck, which an installed plugin's defaults join.
        """
        kit_deck_paths = [str(kit_deck_dir() / filename) for filename in sorted(list_managed_kit_files(area=KitManagedArea.DECK))]
        kit_deck_blueprint = load_model_deck_blueprint(kit_deck_paths)
        assert list(kit_deck_blueprint.doc_gen.choice_defaults) == [BUILT_IN_DOC_GEN_CHOICE_KEY]

    def test_the_built_in_engine_is_the_default_for_a_pdf_without_a_template(self) -> None:
        model_deck = get_model_deck()
        choice = model_deck.get_doc_gen_choice_default(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        assert choice is not None
        doc_gen_setting = model_deck.get_doc_gen_setting(doc_gen_choice=choice)
        assert doc_gen_setting.model == BUILT_IN_DOC_GEN_MODEL
        inference_model = model_deck.get_required_inference_model(model_handle=doc_gen_setting.model, model_type=ModelType.DOC_GEN)
        assert prints_document(inference_model=inference_model, doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)

    def test_the_kit_declares_none_of_the_plugin_s_engines(self) -> None:
        """The plugin declares its own models: the kit's internal.toml names none of them, so an open install serves none.

        Read from the kit's backend file rather than the booted deck, which an installed plugin's models join.
        """
        internal_backend = load_toml_from_path(kit_backends_dir() / "internal.toml")
        doc_gen_models: set[str] = set()
        for name, table in internal_backend.items():
            if isinstance(table, dict) and cast("dict[str, Any]", table).get("model_type") == ModelType.DOC_GEN:
                doc_gen_models.add(name)
        assert doc_gen_models == {BUILT_IN_DOC_GEN_MODEL}
        assert not DOC_GEN_PLUGIN_MODEL_NAMES & set(internal_backend)

    def test_a_default_under_a_key_no_step_makes_is_refused_when_the_deck_loads(self) -> None:
        with pytest.raises(ValidationError, match="a pptx is never composed from the auto-layout"):
            DocGenDeckBlueprint.model_validate({"choice_defaults": {"pptx.layout": "pipelex-pptx"}})
