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

    def test_typeless_contract_section_normalizes_to_signature(self) -> None:
        """A `[pipe.x]` with no `type` and only contract keys IS a signature (the tag is injected)."""
        bundle = PipelexBundleBlueprint.model_validate(
            {
                "domain": "sig_union_demo",
                "pipe": {
                    "summarize_doc": {
                        "description": "Summarize a document (contract only).",
                        "inputs": {"doc": "SigUnionDoc"},
                        "output": "SigUnionSummary",
                    },
                },
            }
        )
        assert bundle.pipe is not None
        loaded = bundle.pipe["summarize_doc"]
        assert isinstance(loaded, PipeSignatureBlueprint)
        assert loaded.is_signature is True
        assert loaded.pipe_category is None

    def test_typeless_contract_without_inputs_is_valid(self) -> None:
        """`inputs` is optional on a signature: `{description, output}` alone is a valid contract."""
        bundle = PipelexBundleBlueprint.model_validate(
            {
                "domain": "sig_union_demo",
                "pipe": {
                    "emit_summary": {
                        "description": "Produce a summary from nothing (contract only).",
                        "output": "SigUnionSummary",
                    },
                },
            }
        )
        assert bundle.pipe is not None
        loaded = bundle.pipe["emit_summary"]
        assert isinstance(loaded, PipeSignatureBlueprint)
        assert loaded.inputs is None

    def test_explicit_signature_tag_rejected(self) -> None:
        """`PipeSignature` is no longer a pipe type: writing it explicitly is a migration error that
        names the pipe and points the author at the typeless form.
        """
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint.model_validate(
                {
                    "domain": "sig_union_demo",
                    "pipe": {
                        "summarize_doc": {
                            "type": "PipeSignature",
                            "description": "Summarize a document (contract only).",
                            "inputs": {"doc": "SigUnionDoc"},
                            "output": "SigUnionSummary",
                        },
                    },
                }
            )
        message = str(exc_info.value)
        assert "summarize_doc" in message
        assert "is no longer a pipe type" in message
        assert "Delete the `type` line" in message

    def test_typeless_section_with_impl_field_raises_teaching_error(self) -> None:
        """A typeless section carrying an implementation field is a hard error naming the field and
        giving both fixes — never silently treated as a signature, never a bare pydantic dump.
        """
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint.model_validate(
                {
                    "domain": "sig_union_demo",
                    "pipe": {
                        "summarize_doc": {
                            "description": "Looks like an implementation but names no type.",
                            "inputs": {"doc": "SigUnionDoc"},
                            "output": "SigUnionSummary",
                            "prompt": "Summarize $doc.",
                        },
                    },
                }
            )
        message = str(exc_info.value)
        # Names the offending pipe and field.
        assert "summarize_doc" in message
        assert "`prompt`" in message
        # States the rule and both escape routes (add a type / remove the field), without guessing a type.
        assert "may declare only" in message
        assert "add the appropriate `type`" in message
        assert "remove `prompt`" in message

    def test_typeless_section_missing_required_contract_field_still_errors(self) -> None:
        """A typeless section whose keys are all contract-legal but that omits a REQUIRED contract
        field (here `output`) is normalized to a signature and then fails the signature's own
        required-field validation. The safety invariant holds: it is never silently accepted as a
        mock, and the missing field is named. (Categorizing this bare pydantic residual into a
        structured item is a deferred, pre-existing general gap — see wip/pipe-signature-not-a-type.md.)
        """
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint.model_validate(
                {
                    "domain": "sig_union_demo",
                    "pipe": {
                        "summarize_doc": {
                            "description": "A contract-only section that forgot to declare its output.",
                            "signature_for": "PipeLLM",
                        },
                    },
                }
            )
        assert "output" in str(exc_info.value)
