"""Unit tests for the doctor command markdown formatter."""

from __future__ import annotations

from typing import Any, ClassVar

from pipelex.cli.agent_cli.commands.doctor_cmd import (
    _format_doctor_markdown,  # pyright: ignore[reportPrivateUsage]
)


class TestFormatDoctorMarkdown:
    """Tests for _format_doctor_markdown output."""

    _HEALTHY_RESULT: ClassVar[dict[str, Any]] = {
        "success": True,
        "all_healthy": True,
        "config_location": {
            "config_dir": "/home/user/.pipelex",
            "is_project_local": False,
            "project_root": None,
            "global_config_dir": "/home/user/.pipelex",
        },
        "checks": {
            "config_files": {"healthy": True, "message": "All config files present", "missing_count": 0},
            "pending_migrations": {
                "healthy": True,
                "finding": "up_to_date",
                "message": "Every configuration file is at the current schema",
                "migratable_files": [],
                "attention_files": [],
            },
            "telemetry": {"healthy": True, "message": "Telemetry configured"},
            "backend_credentials": {"healthy": True, "message": "All backends healthy", "backends": []},
            "models": {"healthy": True, "message": "Models valid", "backend_files": []},
        },
    }

    _UNHEALTHY_RESULT: ClassVar[dict[str, Any]] = {
        "success": True,
        "all_healthy": False,
        "config_location": {
            "config_dir": "/project/.pipelex",
            "is_project_local": True,
            "project_root": "/project",
            "global_config_dir": "/home/user/.pipelex",
        },
        "checks": {
            "config_files": {"healthy": True, "message": "OK", "missing_count": 0},
            "pending_migrations": {
                "healthy": False,
                "finding": "pending",
                "message": "1 configuration file(s) can be brought up to date by 'pipelex migrate'",
                "migratable_files": ["/home/user/.pipelex/telemetry.toml"],
                "attention_files": [],
            },
            "telemetry": {"healthy": False, "message": "Config format outdated"},
            "backend_credentials": {
                "healthy": False,
                "message": "1 backend has issues",
                "backends": [
                    {"backend_name": "openai", "all_credentials_valid": True},
                    {"backend_name": "anthropic", "all_credentials_valid": False, "missing_vars": ["ANTHROPIC_API_KEY"]},
                ],
            },
            "models": {
                "healthy": True,
                "message": "Models valid",
                "backend_files": [
                    {"backend_name": "openai", "file_path": ".pipelex/inference/backends/openai.toml", "is_valid": True},
                ],
            },
        },
        "recommended_actions": [
            "Set environment variable: ANTHROPIC_API_KEY",
        ],
    }

    def test_healthy_output_contains_status_and_checkmark(self) -> None:
        """Healthy result should show 'All healthy' with checkmark emoji."""
        output = _format_doctor_markdown(self._HEALTHY_RESULT)
        assert "All healthy \u2705" in output

    def test_healthy_output_shows_global_location(self) -> None:
        """Global config should be labeled as 'global'."""
        output = _format_doctor_markdown(self._HEALTHY_RESULT)
        assert "/home/user/.pipelex (global)" in output

    def test_healthy_output_has_no_recommended_actions(self) -> None:
        """Healthy result should not include a Recommended Actions section."""
        output = _format_doctor_markdown(self._HEALTHY_RESULT)
        assert "Recommended Actions" not in output

    def test_pending_migrations_section_lists_the_files_a_migration_would_touch(self) -> None:
        """The row an agent reads when nothing has failed yet — a boot would never have said it."""
        rendered = _format_doctor_markdown(self._UNHEALTHY_RESULT)

        assert "## Configuration Migrations" in rendered
        assert "1 configuration file(s) can be brought up to date" in rendered
        assert "`/home/user/.pipelex/telemetry.toml`: out of date" in rendered

    def test_unhealthy_output_shows_warning_status(self) -> None:
        """Unhealthy result should show 'Issues found' with warning emoji."""
        output = _format_doctor_markdown(self._UNHEALTHY_RESULT)
        assert "Issues found \u26a0\ufe0f" in output

    def test_unhealthy_output_shows_project_local(self) -> None:
        """Project-local config should be labeled as 'project-local'."""
        output = _format_doctor_markdown(self._UNHEALTHY_RESULT)
        assert "/project/.pipelex (project-local)" in output

    def test_unhealthy_output_lists_missing_credentials(self) -> None:
        """Missing credentials should appear in the backend credentials section."""
        output = _format_doctor_markdown(self._UNHEALTHY_RESULT)
        assert "ANTHROPIC_API_KEY" in output
        assert "**openai**: All credentials valid" in output

    def test_unhealthy_output_includes_recommended_actions(self) -> None:
        """Recommended actions should appear as a numbered list."""
        output = _format_doctor_markdown(self._UNHEALTHY_RESULT)
        assert "1. Set environment variable: ANTHROPIC_API_KEY" in output

    def test_invalid_model_file_shows_error(self) -> None:
        """Invalid model file should show error message in output."""
        result: dict[str, Any] = {
            **self._HEALTHY_RESULT,
            "all_healthy": False,
            "checks": {
                **self._HEALTHY_RESULT["checks"],
                "models": {
                    "healthy": False,
                    "message": "Issues found",
                    "backend_files": [
                        {
                            "backend_name": "bad_backend",
                            "file_path": ".pipelex/inference/backends/bad.toml",
                            "is_valid": False,
                            "error_message": "Parse error on line 5",
                        },
                    ],
                },
            },
        }
        output = _format_doctor_markdown(result)
        assert "Invalid \u2014 Parse error on line 5" in output

    def test_credentials_invalid_without_details_shows_fallback(self) -> None:
        """Backend with invalid credentials but no missing/placeholder vars shows fallback text."""
        result: dict[str, Any] = {
            **self._HEALTHY_RESULT,
            "all_healthy": False,
            "checks": {
                **self._HEALTHY_RESULT["checks"],
                "backend_credentials": {
                    "healthy": False,
                    "message": "Issues",
                    "backends": [
                        {"backend_name": "mystery", "all_credentials_valid": False},
                    ],
                },
            },
        }
        output = _format_doctor_markdown(result)
        assert "**mystery**: credentials invalid" in output
