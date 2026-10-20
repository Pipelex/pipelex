"""Catalog transport, command output and validated backend exports."""

import json
from pathlib import Path
from typing import Any

import click
import httpx
import pytest
import tomli
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from pipelex.cli.dev_cli._dev_cli import app
from pipelex.cli.dev_cli.commands.openrouter.catalog import OpenRouterModel


class TestOpenRouterCommand:
    @pytest.mark.usefixtures("mocked_catalog")
    def test_json_filter(self) -> None:
        result = CliRunner().invoke(app, ["openrouter", "list-models", "-f", "TEXT.V1", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert [model["id"] for model in payload["models"]] == ["acme/text.v1:free"]
        assert not result.stderr

    @pytest.mark.usefixtures("mocked_catalog")
    @pytest.mark.parametrize(("sort_key", "first_id"), [("name", "acme/image"), ("context_length", "acme/text.v1:free"), ("created", "acme/image")])
    def test_sort_json(self, sort_key: str, first_id: str) -> None:
        result = CliRunner().invoke(app, ["openrouter", "list-models", "--sort", sort_key, "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["models"][0]["id"] == first_id

    @pytest.mark.usefixtures("mocked_catalog")
    def test_markdown(self) -> None:
        result = CliRunner().invoke(app, ["openrouter", "list-models"])
        assert result.exit_code == 0, result.output
        assert "| Context tokens |" in result.stdout
        assert r"Text \| Model" in result.stdout
        assert "Unknown" in result.stdout
        assert "Internal Development Tools" not in result.stdout

    @pytest.mark.usefixtures("mocked_catalog")
    def test_export_refuses_overwrite(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            args = ["openrouter", "list-models", "--save", "--json", "-f", "text.v1"]
            first = runner.invoke(app, args)
            assert first.exit_code == 0, first.output
            path = Path(json.loads(first.stdout)["saved_to"])
            original = path.read_text(encoding="utf-8")
            second = runner.invoke(app, args)
            assert second.exit_code == 1
            assert not second.stdout
            assert json.loads(second.stderr)["ok"] is False
            assert path.read_text(encoding="utf-8") == original

    def test_export_reports_skipped_modalities(self, mocker: MockerFixture, catalog_models: list[dict[str, Any]]) -> None:
        models = [OpenRouterModel.model_validate(model) for model in catalog_models]
        models.append(OpenRouterModel.model_validate({"id": "acme/audio", "architecture": {"output_modalities": ["speech"]}}))
        mocker.patch("pipelex.cli.dev_cli.commands.openrouter.openrouter_cmd.fetch_models", return_value=models)
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(app, ["openrouter", "list-models", "--save", "--json"])
            assert result.exit_code == 0, result.output
            payload = json.loads(result.stdout)
            assert payload["skipped_model_ids"] == ["acme/audio"]
            assert len(payload["models"]) == len(models)
            assert "acme/audio" not in tomli.loads(Path(payload["saved_to"]).read_text(encoding="utf-8"))

    @pytest.mark.parametrize("payload", [{"wrong": []}, {"data": [{"id": 123}]}, {"data": "invalid"}])
    def test_malformed_response(self, mocker: MockerFixture, payload: dict[str, Any]) -> None:
        client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)))
        mocker.patch("pipelex.cli.dev_cli.commands.openrouter.catalog.httpx.Client", return_value=client)
        result = CliRunner().invoke(app, ["openrouter", "list-models", "--json"])
        assert result.exit_code == 1
        assert not result.stdout
        assert json.loads(result.stderr) == {"ok": False, "error": "OpenRouter returned malformed catalog metadata"}

    def test_http_failure(self, mocker: MockerFixture) -> None:
        client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(503, text="private upstream body")))
        mocker.patch("pipelex.cli.dev_cli.commands.openrouter.catalog.httpx.Client", return_value=client)
        result = CliRunner().invoke(app, ["openrouter", "list-models"])
        assert result.exit_code == 1
        assert "HTTP 503" in result.stderr
        assert "private upstream body" not in result.output

    @pytest.mark.parametrize("color", [False, True])
    def test_help(self, color: bool) -> None:
        assert "openrouter" in CliRunner().invoke(app, ["--help"]).stdout
        result = CliRunner().invoke(app, ["openrouter", "list-models", "--help"], color=color)
        assert result.exit_code == 0
        assert "--save" in click.unstyle(result.stdout)
