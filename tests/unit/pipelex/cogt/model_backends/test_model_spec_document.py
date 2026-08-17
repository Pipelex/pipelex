"""A backend definition file is a document, not a model — and both of its readers say so here.

`[defaults]` and a per-model table are each half of an `InferenceModelSpecBlueprint`: `sdk` is
required and normally lives in `[defaults]`, so only their merge validates. The loader has always
known that; the migration surface needs the same two answers — a field-level projection of one root
table to fingerprint, and the loader's own verdict on a whole document — and `model_spec_document`
is where the two are stated once so they cannot drift.
"""

from typing import Any

import pytest

from pipelex.cogt.model_backends.model_spec_document import (
    InferenceModelSpecFileNode,
    describe_model_spec_document_rejection,
)
from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint


class TestABackendFileIsADocumentNotAModel:
    def test_no_field_of_the_file_node_projection_is_required(self) -> None:
        """The one guard the fingerprint's honesty rests on.

        Every root table of a backend file is a *partial* spec — `[defaults]` carries what the models
        share, a model table carries what it overrides — so a projection with a required field would
        claim of every table a key that most of them legitimately lack. This goes red the day a new
        required field lands on the blueprint, which is exactly when the projection needs a decision.
        """
        required = [name for name, field in InferenceModelSpecFileNode.model_fields.items() if field.is_required()]

        assert required == []

    def test_the_projection_holds_exactly_the_blueprint_fields(self) -> None:
        """It is a projection of the blueprint, not a model of its own: same keys, different requiredness."""
        assert set(InferenceModelSpecFileNode.model_fields) == set(InferenceModelSpecBlueprint.model_fields)

    def test_a_document_the_loader_accepts_is_accepted(self) -> None:
        document: dict[str, Any] = {
            "defaults": {"sdk": "openai", "model_type": "llm"},
            "gpt-4o": {"model_id": "gpt-4o-2024-11-20", "max_tokens": 4096},
            "o3": {"thinking_mode": "adaptive", "x-portkey-provider": "openai"},
        }

        assert describe_model_spec_document_rejection(document=document) is None

    def test_a_stale_key_in_the_defaults_block_is_refused_and_names_the_key(self) -> None:
        """The `[defaults]` half of what `#1104` left behind: one dead key there fails every model.

        `[defaults]` is copied wholesale into each model's blueprint dict — it is deliberately *not*
        passed through the header split — so a key the blueprint no longer knows is `extra_forbidden`
        on every table in the file rather than on one.
        """
        document: dict[str, Any] = {
            "defaults": {"sdk": "openai", "prompting_target": "openai"},
            "gpt-4o": {"model_id": "gpt-4o-2024-11-20"},
        }

        rejection = describe_model_spec_document_rejection(document=document)

        assert rejection is not None
        assert "prompting_target" in rejection
        assert "gpt-4o" in rejection

    def test_a_stale_key_on_one_model_is_refused_by_name(self) -> None:
        """The per-model half: not header-shaped, so it is a typo or a dead field, and fatal since #1109."""
        document: dict[str, Any] = {
            "defaults": {"sdk": "openai"},
            "gpt-4o": {"prompting_target": "openai"},
        }

        rejection = describe_model_spec_document_rejection(document=document)

        assert rejection is not None
        assert "prompting_target" in rejection

    def test_a_header_shaped_key_is_not_a_rejection(self) -> None:
        """The keys this surface must never touch: they are the author's headers, and the loader sends them."""
        document: dict[str, Any] = {
            "defaults": {"sdk": "openai"},
            "gpt-4o": {"x-portkey-config": "cfg-123", "anthropic-beta": "output-128k"},
        }

        assert describe_model_spec_document_rejection(document=document) is None

    def test_a_document_with_no_model_at_all_is_accepted(self) -> None:
        """`pipelex_gateway.toml` in the kit is comments only, and the loader loads it without complaint."""
        assert describe_model_spec_document_rejection(document={}) is None

    @pytest.mark.parametrize(
        "document",
        [
            {"defaults": "not a table"},
            {"defaults": {"sdk": "openai"}, "gpt-4o": "not a table"},
        ],
        ids=["defaults", "model"],
    )
    def test_a_root_key_whose_value_is_not_a_table_is_refused(self, document: dict[str, Any]) -> None:
        assert describe_model_spec_document_rejection(document=document) is not None
