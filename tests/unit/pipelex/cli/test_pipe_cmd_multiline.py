"""Unit tests for multi-line TOML string output in pipe command."""

from __future__ import annotations

from typing import Any, ClassVar

from pipelex.cli.agent_cli.commands.pipe_cmd import (
    _parse_pipe_spec_from_json,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
    _pipe_spec_to_toml,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
)


class TestMultilineTomlStrings:
    """Verify that multi-line string fields use TOML triple-quoted strings."""

    _BASE_LLM: ClassVar[dict[str, Any]] = {
        "pipe_code": "my_llm_pipe",
        "description": "Test LLM pipe",
        "llm_talent": "creative-writer",
        "inputs": {"text": "Text"},
        "output": "Text",
    }

    def test_multiline_prompt_uses_triple_quotes(self) -> None:
        """A prompt with newlines should use TOML multi-line basic strings."""
        spec = _parse_pipe_spec_from_json(
            "PipeLLM",
            {**self._BASE_LLM, "prompt": "Write a story about @text.\nMake it vivid.\nInclude dialogue."},
        )
        toml = _pipe_spec_to_toml(spec)
        assert '"""' in toml
        assert "\\n" not in toml
        assert "Make it vivid." in toml

    def test_single_line_prompt_stays_basic_string(self) -> None:
        """A prompt without newlines should remain a regular quoted string."""
        spec = _parse_pipe_spec_from_json(
            "PipeLLM",
            {**self._BASE_LLM, "prompt": "Write about @text"},
        )
        toml = _pipe_spec_to_toml(spec)
        assert 'prompt = "Write about @text"' in toml
        assert '"""' not in toml

    def test_multiline_system_prompt(self) -> None:
        """A system_prompt with newlines should use TOML multi-line basic strings."""
        spec = _parse_pipe_spec_from_json(
            "PipeLLM",
            {
                **self._BASE_LLM,
                "prompt": "Write about @text",
                "system_prompt": "You are a helpful assistant.\nBe concise.\nAvoid jargon.",
            },
        )
        toml = _pipe_spec_to_toml(spec)
        assert "Be concise." in toml
        assert toml.count('"""') >= 2  # opening and closing triple quotes

    def test_multiline_template(self) -> None:
        """A PipeCompose template with newlines should use TOML multi-line basic strings."""
        spec = _parse_pipe_spec_from_json(
            "PipeCompose",
            {
                "pipe_code": "my_compose",
                "description": "Compose output",
                "inputs": {"name": "Text", "body": "Text"},
                "output": "Text",
                "target_format": "plain",
                "template": "Dear $name,\n\n@body\n\nBest regards.",
            },
        )
        toml = _pipe_spec_to_toml(spec)
        assert '"""' in toml
        assert "\\n" not in toml
        assert "Dear $name," in toml

    def test_multiline_img_gen_prompt(self) -> None:
        """A PipeImgGen prompt with newlines should use TOML multi-line basic strings."""
        spec = _parse_pipe_spec_from_json(
            "PipeImgGen",
            {
                "pipe_code": "my_img_gen",
                "description": "Image gen pipe",
                "inputs": {"idea": "ImgGenPrompt"},
                "output": "Image",
                "img_gen_talent": "gen-image",
                "prompt": "Generate an image:\n$idea\nPhotorealistic style.",
            },
        )
        toml = _pipe_spec_to_toml(spec)
        assert '"""' in toml
        assert "\\n" not in toml
        assert "Photorealistic style." in toml
