"""Unit tests for typeless-signature normalization in the spec (authoring) layer.

Mirrors the blueprint-layer behavior: a `[pipe.x]` spec section with no `type` whose keys are exactly
the signature contract is normalized to a `PipeSignatureSpec`; a typeless section with any stray field
raises the teaching error; and an explicit `type = "PipeSignature"` is rejected with the migration
error (a signature has no type).
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_signature_spec import PipeSignatureSpec
from pipelex.pipe_machinery.pipe_blueprint import PipeType
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint


def _bundle_with_pipe(pipe_section: dict[str, Any], *, pipe_code: str = "summarize_doc") -> PipelexBundleSpec:
    return PipelexBundleSpec.model_validate(
        {
            "domain": "test_domain",
            "main_pipe": pipe_code,
            "pipe": {pipe_code: pipe_section},
        }
    )


class TestPipelexBundleSpecTypelessSignature:
    def test_typeless_contract_section_becomes_signature_spec(self) -> None:
        """A typeless contract-only section routes to PipeSignatureSpec and round-trips to a signature blueprint."""
        bundle_spec = _bundle_with_pipe(
            {
                "pipe_code": "summarize_doc",
                "description": "Produces a summary of a document.",
                "inputs": {"doc": "Document"},
                "output": "Summary",
            }
        )
        assert bundle_spec.pipe is not None
        sig_spec = bundle_spec.pipe["summarize_doc"]
        assert isinstance(sig_spec, PipeSignatureSpec)

        blueprint = sig_spec.to_blueprint()
        assert isinstance(blueprint, PipeSignatureBlueprint)
        assert blueprint.is_signature is True
        assert blueprint.description == "Produces a summary of a document."
        assert blueprint.inputs == {"doc": "Document"}
        assert blueprint.output == "Summary"

    def test_typeless_with_signature_for_hint_becomes_signature(self) -> None:
        """`signature_for` is a contract-legal optional key, so the section is still a signature."""
        bundle_spec = _bundle_with_pipe(
            {
                "pipe_code": "summarize_doc",
                "description": "Produces a summary of a document.",
                "inputs": {"doc": "Document"},
                "output": "Summary",
                "signature_for": "PipeLLM",
            }
        )
        assert bundle_spec.pipe is not None
        sig_spec = bundle_spec.pipe["summarize_doc"]
        assert isinstance(sig_spec, PipeSignatureSpec)
        assert sig_spec.signature_for is PipeType.PIPE_LLM

    def test_typeless_with_stray_field_raises_teaching_error(self) -> None:
        """A typeless section carrying an implementation field is a hard error that names the field and both fixes."""
        with pytest.raises(ValidationError) as exc_info:
            _bundle_with_pipe(
                {
                    "pipe_code": "summarize_doc",
                    "description": "Produces a summary of a document.",
                    "inputs": {"doc": "Document"},
                    "output": "Summary",
                    "prompt": "Summarize $doc",
                }
            )
        message = str(exc_info.value)
        assert "has no `type` but declares `prompt`" in message
        assert "To keep it a contract, remove `prompt`" in message

    def test_typeless_with_blueprint_only_source_field_raises_teaching_error(self) -> None:
        """`source` is a blueprint-only field absent from the spec surface, so a typeless section
        carrying it is a stray key (teaching error) — not injected then rejected with a raw pydantic
        `extra_forbidden` message.
        """
        with pytest.raises(ValidationError) as exc_info:
            _bundle_with_pipe(
                {
                    "pipe_code": "summarize_doc",
                    "description": "Produces a summary of a document.",
                    "inputs": {"doc": "Document"},
                    "output": "Summary",
                    "source": "somewhere.mthds",
                }
            )
        message = str(exc_info.value)
        assert "has no `type` but declares `source`" in message
        assert "Extra inputs are not permitted" not in message

    def test_stray_key_message_advertises_signature_for(self) -> None:
        """The teaching message names `signature_for` as a valid contract key (it is allowed), and does
        not leak the internal `source` / `pipe_code` keys the allowlists also admit.
        """
        with pytest.raises(ValidationError) as exc_info:
            _bundle_with_pipe(
                {
                    "pipe_code": "summarize_doc",
                    "description": "Produces a summary of a document.",
                    "output": "Summary",
                    "signature_for": "PipeLLM",
                    "model": "gpt",
                }
            )
        message = str(exc_info.value)
        assert "has no `type` but declares `model`" in message
        assert "`signature_for`" in message
        assert "`source`" not in message
        assert "`pipe_code`" not in message

    def test_signature_spec_survives_model_dump_revalidate_round_trip(self) -> None:
        """A bundle spec with a typeless signature must survive `model_dump()` → re-validate. The
        internal `type` / `pipe_category` discriminators must not serialize, else re-validation trips
        the explicit-tag migration error (`type`) or the stray-key teaching error (`pipe_category`).
        """
        bundle_spec = _bundle_with_pipe(
            {
                "pipe_code": "summarize_doc",
                "description": "Produces a summary of a document.",
                "inputs": {"doc": "Document"},
                "output": "Summary",
            }
        )
        dumped = bundle_spec.model_dump()
        sig_section = dumped["pipe"]["summarize_doc"]
        assert "type" not in sig_section
        assert "pipe_category" not in sig_section

        reloaded = PipelexBundleSpec.model_validate(dumped)
        assert reloaded.pipe is not None
        assert isinstance(reloaded.pipe["summarize_doc"], PipeSignatureSpec)

    def test_invalid_pipe_dict_key_rejected_at_spec_level(self) -> None:
        """A non-snake_case pipe dict key is rejected cleanly by the before-validator (mirrors the
        blueprint), instead of slipping through to fail later during `to_blueprint()`.
        """
        with pytest.raises(ValidationError, match="Pipe code 'BadKeyPipe' is not a valid pipe code"):
            PipelexBundleSpec.model_validate(
                {
                    "domain": "test_domain",
                    "main_pipe": "BadKeyPipe",
                    "pipe": {
                        "BadKeyPipe": {
                            "type": "PipeLLM",
                            "pipe_code": "good_pipe",
                            "description": "Writes some text.",
                            "inputs": {"topic": "Text"},
                            "output": "Text",
                            "prompt": "Write about $topic",
                        }
                    },
                }
            )

    def test_explicit_signature_tag_rejected(self) -> None:
        """`PipeSignature` is no longer a pipe type: writing it explicitly in a spec section is a
        migration error naming the pipe and pointing at the typeless form.
        """
        with pytest.raises(ValidationError) as exc_info:
            _bundle_with_pipe(
                {
                    "type": "PipeSignature",
                    "pipe_code": "summarize_doc",
                    "description": "Produces a summary of a document.",
                    "inputs": {"doc": "Document"},
                    "output": "Summary",
                }
            )
        message = str(exc_info.value)
        assert "summarize_doc" in message
        assert "is no longer a pipe type" in message
        assert "Delete the `type` line" in message

    def test_typed_section_left_untouched(self) -> None:
        """A section that names its own `type` is not normalized — it routes to its concrete spec."""
        bundle_spec = _bundle_with_pipe(
            {
                "type": "PipeLLM",
                "pipe_code": "write_text",
                "description": "Writes some text.",
                "inputs": {"topic": "Text"},
                "output": "Text",
                "prompt": "Write about $topic",
            },
            pipe_code="write_text",
        )
        assert bundle_spec.pipe is not None
        assert isinstance(bundle_spec.pipe["write_text"], PipeLLMSpec)

    def test_already_built_spec_instance_passes_through(self) -> None:
        """A pre-built spec instance (not a raw dict) is left untouched by the before-validator."""
        llm_spec = PipeLLMSpec(
            pipe_code="write_text",
            description="Writes some text.",
            inputs={"topic": "Text"},
            output="Text",
            prompt="Write about $topic",
            model="$writing-creative",
        )
        bundle_spec = PipelexBundleSpec(domain="test_domain", main_pipe="write_text", pipe={"write_text": llm_spec})
        assert bundle_spec.pipe is not None
        assert bundle_spec.pipe["write_text"] is llm_spec
