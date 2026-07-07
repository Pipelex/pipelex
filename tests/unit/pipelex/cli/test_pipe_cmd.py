"""Unit tests for the agent CLI pipe command — CLI-specific behavior.

parse_pipe_spec tolerance tests (aliases, output dict, etc.) live in
tests/unit/pipelex/builder/operations/test_parse_pipe_spec.py.
pipe_spec_to_toml tests live in tests/unit/pipelex/builder/operations/test_pipe_spec_to_toml.py.
This file tests CLI-layer concerns: TOML serialization (_pipe_spec_to_toml which uses format_toml_string)
and integration of parse_pipe_spec with the CLI output path.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest
import typer

from pipelex.builder.operations.pipe_ops import parse_pipe_spec
from pipelex.cli.agent_cli.commands.pipe_cmd import (
    _pipe_spec_to_toml,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
    pipe_cmd,
)


class TestCliPipeCmd:
    """CLI-specific tests: pipe_type extraction from JSON and CLI TOML serialization."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "pipe_code": "my_llm_pipe",
        "description": "Test LLM pipe",
        "model": "$writing-creative",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write about $text",
    }

    # -- pipe_type alias in JSON (handled by pipe_cmd, not parse_pipe_spec) --

    def test_type_extracted_from_spec(self) -> None:
        """When type is in the spec dict it should be used (and popped)."""
        spec: dict[str, Any] = {
            "type": "PipeLLM",
            "pipe_code": "test",
            "description": "Test",
            "model": "$writing-creative",
            "inputs": {"text": "Text"},
            "output": "Text",
            "prompt": "Write about $text",
        }
        pipe_type = spec.pop("type")
        result = parse_pipe_spec(spec, pipe_type=pipe_type)
        assert result.pipe_code == "test"

    def test_typeless_spec_renders_signature_without_type_line(self) -> None:
        """No type resolved (typeless) → a signature; the CLI TOML omits the `type` line entirely."""
        spec = parse_pipe_spec(
            {"pipe_code": "summarize_doc", "description": "Summarize a doc.", "inputs": {"doc": "Document"}, "output": "Text"},
            pipe_type=None,
        )
        toml = _pipe_spec_to_toml(spec)
        assert "[pipe.summarize_doc]" in toml
        assert "type =" not in toml

    def test_explicit_null_type_rejected(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An explicit `"type": null` in the JSON spec is rejected — a signature is authored by omitting
        the `type` key, not by nulling it (teaching-consistent with the explicit-tag rejection). Present
        null must not silently collapse to a typeless signature.
        """
        spec = json.dumps({"pipe_code": "summarize_doc", "description": "d", "inputs": {"doc": "Document"}, "output": "Text", "type": None})
        with pytest.raises(typer.Exit):
            pipe_cmd(spec=spec)
        captured = capsys.readouterr()
        combined = captured.err + captured.out
        assert "ArgumentError" in combined
        assert "type" in combined

    def test_non_string_type_rejected_with_actionable_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A non-string JSON `type` (e.g. a list/dict — unhashable) must surface as an actionable
        ArgumentError naming the valid types, never a cryptic internal `TypeError: unhashable type`
        leaking from the membership test inside parse_pipe_spec.
        """
        spec = json.dumps({"pipe_code": "x", "description": "d", "inputs": {"doc": "Document"}, "output": "Text", "type": ["PipeCompose"]})
        with pytest.raises(typer.Exit):
            pipe_cmd(spec=spec)
        captured = capsys.readouterr()
        combined = captured.err + captured.out
        assert "ArgumentError" in combined
        assert "TypeError" not in combined
        assert "Invalid pipe type" in combined

    # -- CLI TOML serialization (uses format_toml_string) -----------------

    def test_llm_model_appears_in_toml(self) -> None:
        spec = parse_pipe_spec({**self._BASE_LLM}, pipe_type="PipeLLM")
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "$writing-creative"' in toml

    def test_llm_different_model_in_toml(self) -> None:
        spec = parse_pipe_spec({**self._BASE_LLM, "model": "$engineering-structured"}, pipe_type="PipeLLM")
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "$engineering-structured"' in toml

    def test_extract_model_in_toml(self) -> None:
        spec = parse_pipe_spec(
            {
                "pipe_code": "my_extract",
                "description": "Extract pipe",
                "inputs": {"doc": "Document"},
                "output": "Page[]",
                "model": "@default-extract-document",
            },
            pipe_type="PipeExtract",
        )
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "@default-extract-document"' in toml

    def test_img_gen_model_in_toml(self) -> None:
        spec = parse_pipe_spec(
            {
                "pipe_code": "my_img_gen",
                "description": "Image gen pipe",
                "inputs": {"prompt_text": "Text"},
                "output": "Image",
                "model": "$gen-image",
                "prompt": "Generate: $prompt_text",
            },
            pipe_type="PipeImgGen",
        )
        toml = _pipe_spec_to_toml(spec)
        assert 'model = "$gen-image"' in toml

    def test_toml_contains_pipe_section(self) -> None:
        spec = parse_pipe_spec({**self._BASE_LLM}, pipe_type="PipeLLM")
        toml = _pipe_spec_to_toml(spec)
        assert "[pipe.my_llm_pipe]" in toml
        assert 'type = "PipeLLM"' in toml

    def test_toml_contains_prompt(self) -> None:
        spec = parse_pipe_spec({**self._BASE_LLM}, pipe_type="PipeLLM")
        toml = _pipe_spec_to_toml(spec)
        assert 'prompt = "Write about $text"' in toml

    def test_sequence_toml_has_steps(self) -> None:
        spec = parse_pipe_spec(
            {
                "pipe_code": "my_seq",
                "description": "A sequence",
                "inputs": {"doc": "Document"},
                "output": "Text",
                "steps": [
                    {"pipe": "step_one", "result": "intermediate"},
                    {"pipe": "step_two", "result": "final"},
                ],
            },
            pipe_type="PipeSequence",
        )
        toml = _pipe_spec_to_toml(spec)
        assert "step_one" in toml
        assert "step_two" in toml

    def test_search_fields_appear_in_toml(self) -> None:
        """PipeSearch type-specific fields (prompt, model, filters) must round-trip to TOML."""
        spec = parse_pipe_spec(
            {
                "pipe_code": "my_search",
                "description": "Search pipe",
                "inputs": {"topic": "Text"},
                "output": "Text",
                "model": "$search-default",
                "prompt": "Latest news about $topic",
                "from_date": "2025-01-01",
                "to_date": "2025-06-01",
                "include_domains": ["reuters.com", "bbc.com"],
                "exclude_domains": ["example.com"],
                "max_results": 5,
            },
            pipe_type="PipeSearch",
        )
        toml = _pipe_spec_to_toml(spec)
        assert 'type = "PipeSearch"' in toml
        assert 'model = "$search-default"' in toml
        assert 'prompt = "Latest news about $topic"' in toml
        assert 'from_date = "2025-01-01"' in toml
        assert 'to_date = "2025-06-01"' in toml
        assert "reuters.com" in toml
        assert "bbc.com" in toml
        assert "example.com" in toml
        assert "max_results = 5" in toml

    def test_search_optional_filters_omitted_in_toml(self) -> None:
        """Unset PipeSearch filters must not appear in the TOML (only prompt is required)."""
        spec = parse_pipe_spec(
            {
                "pipe_code": "bare_search",
                "description": "Minimal search pipe",
                "inputs": {"topic": "Text"},
                "output": "Text",
                "prompt": "About $topic",
            },
            pipe_type="PipeSearch",
        )
        toml = _pipe_spec_to_toml(spec)
        assert 'prompt = "About $topic"' in toml
        assert "model =" not in toml
        assert "from_date" not in toml
        assert "to_date" not in toml
        assert "include_domains" not in toml
        assert "exclude_domains" not in toml
        assert "max_results" not in toml

    def test_llm_no_model_omits_model_in_toml(self) -> None:
        """When model is None, no model line should appear in the TOML."""
        spec = parse_pipe_spec(
            {
                "pipe_code": "my_pipe",
                "description": "No model specified",
                "inputs": {"text": "Text"},
                "output": "Text",
                "prompt": "Write about $text",
            },
            pipe_type="PipeLLM",
        )
        toml = _pipe_spec_to_toml(spec)
        assert "model =" not in toml

    # -- End-to-end: combined tolerance through CLI layer ------------------

    def test_model_with_dict_output_both_tolerated(self) -> None:
        """The agent sends model preset and output as dict — both should be tolerated."""
        spec: dict[str, Any] = {
            "pipe_code": "generate_prompt",
            "description": "Generate an image prompt from an idea",
            "model": "$writing-creative",
            "inputs": {"idea": "Text"},
            "output": {"type": "Text"},
            "prompt": "Generate a creative image prompt based on $idea",
        }
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        assert result.model == "$writing-creative"  # type: ignore[attr-defined]
        assert result.output == "Text"

    def test_toml_output_has_correct_model(self) -> None:
        """The TOML should contain the model preset directly."""
        spec: dict[str, Any] = {
            "pipe_code": "generate_prompt",
            "description": "Generate an image prompt from an idea",
            "model": "$writing-creative",
            "inputs": {"idea": "Text"},
            "output": {"type": "Text"},
            "prompt": "Generate a creative image prompt based on $idea",
        }
        result = parse_pipe_spec(spec, pipe_type="PipeLLM")
        toml = _pipe_spec_to_toml(result)
        assert 'model = "$writing-creative"' in toml
        assert 'output = "Text"' in toml
