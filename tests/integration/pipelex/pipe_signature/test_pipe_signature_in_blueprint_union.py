import pytest
from pydantic import ValidationError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint


class TestPipeSignatureBlueprintUnion:
    def test_bundle_blueprint_accepts_signature_pipe(self) -> None:
        signature_blueprint = PipeSignatureBlueprint(
            description="Summarize a document (contract only).",
            inputs={"doc": "SigUnionDoc"},
            output="SigUnionSummary",
        )
        bundle = PipelexBundleBlueprint(
            domain="sig_union_demo",
            concept={
                "SigUnionDoc": ConceptBlueprint(description="A document."),
                "SigUnionSummary": ConceptBlueprint(description="A summary."),
            },
            pipe={"summarize_doc": signature_blueprint},
        )
        assert bundle.pipe is not None
        loaded = bundle.pipe["summarize_doc"]
        assert isinstance(loaded, PipeSignatureBlueprint)

    def test_bundle_blueprint_rejects_unknown_pipe_type(self) -> None:
        with pytest.raises(ValidationError):
            PipelexBundleBlueprint.model_validate(
                {
                    "domain": "sig_union_demo",
                    "pipe": {
                        "broken": {
                            "type": "PipeNonsense",
                            "description": "Should not validate.",
                            "output": "Text",
                        },
                    },
                }
            )
