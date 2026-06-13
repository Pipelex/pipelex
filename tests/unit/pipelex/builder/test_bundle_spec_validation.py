"""Unit tests for PipelexBundleSpec pydantic validation rules."""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec


def make_llm_spec(pipe_code: str = "write_text") -> PipeLLMSpec:
    return PipeLLMSpec(
        pipe_code=pipe_code,
        description=f"Generate text for {pipe_code}",
        inputs={"topic": "Text"},
        output="Text",
        prompt="Write about $topic",
        model="$writing-creative",
    )


class TestPipelexBundleSpecValidation:
    @pytest.mark.parametrize("bad_domain", ["Bad Domain", "UpperCase", "has-dashes", "1starts_with_digit"])
    def test_invalid_domain_code_rejected(self, bad_domain: str) -> None:
        """An invalid domain code is rejected with an explicit error message."""
        with pytest.raises(ValidationError, match="not a valid domain code"):
            PipelexBundleSpec(domain=bad_domain, main_pipe="write_text", pipe={"write_text": make_llm_spec()})

    def test_main_pipe_absent_from_pipe_dict_rejected(self) -> None:
        """A main_pipe that is not a key of the pipe dict is rejected."""
        with pytest.raises(ValidationError, match="Main pipe 'missing_pipe' could not be found in bundle spec"):
            PipelexBundleSpec(domain="test_domain", main_pipe="missing_pipe", pipe={"write_text": make_llm_spec()})

    @pytest.mark.parametrize("empty_pipes", [{}, None])
    def test_main_pipe_with_no_pipes_rejected(self, empty_pipes: dict[str, Any] | None) -> None:
        """A main_pipe declared while the pipe dict is empty or None is rejected."""
        with pytest.raises(ValidationError, match="Main pipe 'write_text' could not be found in bundle spec"):
            PipelexBundleSpec(domain="test_domain", main_pipe="write_text", pipe=empty_pipes)

    def test_valid_spec_constructs(self) -> None:
        """A well-formed spec constructs and exposes its declared fields."""
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            description="A test bundle",
            system_prompt="You are concise",
            main_pipe="write_text",
            pipe={"write_text": make_llm_spec()},
        )

        assert bundle_spec.domain == "test_domain"
        assert bundle_spec.description == "A test bundle"
        assert bundle_spec.system_prompt == "You are concise"
        assert bundle_spec.main_pipe == "write_text"
        assert bundle_spec.pipe is not None
        assert list(bundle_spec.pipe.keys()) == ["write_text"]
        assert bundle_spec.pipe["write_text"].description == "Generate text for write_text"
        assert bundle_spec.concept == {}
