"""Unit tests for PipeCompose TOML serialization via pipe_spec_to_toml."""

from typing import Any, ClassVar

import pytest

from pipelex.builder.operations.pipe_ops import pipe_spec_to_toml
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec


class _TomlTestCases:
    """Test data for PipeCompose → TOML serialization."""

    CONSTRUCT_WITH_FROM_MAPPINGS: ClassVar[tuple[str, dict[str, Any]]] = (
        "construct_with_from_mappings",
        {
            "pipe_code": "compose_sheet",
            "description": "Compose interview sheet",
            "inputs": {"analysis": "MatchAnalysis", "questions": "InterviewQuestion[]"},
            "output": "InterviewSheet",
            "construct": {
                "score": {"from": "analysis.overall_score"},
                "questions": {"from": "questions"},
            },
        },
    )

    CONSTRUCT_WITH_STATIC_VALUES: ClassVar[tuple[str, dict[str, Any]]] = (
        "construct_with_static_values",
        {
            "pipe_code": "compose_report",
            "description": "Compose a report",
            "inputs": {"title": "native.Text"},
            "output": "Report",
            "construct": {
                "title": {"from": "title"},
                "version": "1.0",
                "page_count": 42,
            },
        },
    )

    TEMPLATE_MODE: ClassVar[tuple[str, dict[str, Any]]] = (
        "template_mode",
        {
            "pipe_code": "render_greeting",
            "description": "Render a greeting",
            "inputs": {"name": "native.Text"},
            "output": "native.Text",
            "target_format": "markdown",
            "template": "Hello $name!",
        },
    )


class TestPipeComposeToToml:
    """Tests for pipe_spec_to_toml with PipeCompose specs."""

    @pytest.mark.parametrize(
        ("_test_name", "spec_data"),
        [
            _TomlTestCases.CONSTRUCT_WITH_FROM_MAPPINGS,
            _TomlTestCases.CONSTRUCT_WITH_STATIC_VALUES,
            _TomlTestCases.TEMPLATE_MODE,
        ],
    )
    def test_pipe_spec_to_toml_does_not_crash(
        self,
        _test_name: str,
        spec_data: dict[str, Any],
    ) -> None:
        """All PipeCompose modes should serialize to TOML without errors."""
        pipe_spec = PipeComposeSpec.model_validate({**spec_data, "type": "PipeCompose"})
        result = pipe_spec_to_toml(pipe_spec)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_construct_mode_has_construct_section(self) -> None:
        """Construct mode should produce a [pipe.<code>.construct] section with inline tables."""
        spec_data = _TomlTestCases.CONSTRUCT_WITH_FROM_MAPPINGS[1]
        pipe_spec = PipeComposeSpec.model_validate({**spec_data, "type": "PipeCompose"})
        result = pipe_spec_to_toml(pipe_spec)

        assert "[pipe.compose_sheet.construct]" in result
        assert 'score = {from = "analysis.overall_score"}' in result
        assert 'questions = {from = "questions"}' in result
        # Template mode fields should NOT appear
        assert "target_format" not in result
        assert "template" not in result

    def test_construct_with_static_values(self) -> None:
        """Non-dict values in construct spec should be serialized directly."""
        spec_data = _TomlTestCases.CONSTRUCT_WITH_STATIC_VALUES[1]
        pipe_spec = PipeComposeSpec.model_validate({**spec_data, "type": "PipeCompose"})
        result = pipe_spec_to_toml(pipe_spec)

        assert "[pipe.compose_report.construct]" in result
        assert 'title = {from = "title"}' in result
        assert 'version = "1.0"' in result
        assert "page_count = 42" in result

    def test_template_mode_has_target_format_and_template(self) -> None:
        """Template mode should produce target_format and template fields."""
        spec_data = _TomlTestCases.TEMPLATE_MODE[1]
        pipe_spec = PipeComposeSpec.model_validate({**spec_data, "type": "PipeCompose"})
        result = pipe_spec_to_toml(pipe_spec)

        assert 'target_format = "markdown"' in result
        assert 'template = "Hello $name!"' in result
        # Construct section should NOT appear
        assert "construct" not in result.split("template")[0]  # no construct key before template
