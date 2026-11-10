import tomllib
from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.runtime_hub import get_optional_document_converter
from pipelex.tools.document_conversion.document_conversion_config import DocumentConversionBackend, DocumentConversionConfig
from pipelex.tools.document_conversion.document_converter_factory import make_optional_document_converter_from_config
from pipelex.tools.document_conversion.exceptions import DocumentConverterMisconfiguredError
from pipelex.tools.document_conversion.gotenberg_converter import GotenbergConverter
from pipelex.tools.document_conversion.soffice_converter import SofficeConverter

_REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent
_PACKAGED_CONFIG_PATH = _REPO_ROOT / "pipelex" / "pipelex.toml"


def _packaged_table() -> dict[str, Any]:
    packaged: dict[str, Any] = tomllib.loads(_PACKAGED_CONFIG_PATH.read_text(encoding="utf-8"))
    table: dict[str, Any] = packaged["runtime"]["document_conversion"]
    return table


def _config(*, backend: str, gotenberg_url: str = "", soffice_binary: str = "soffice") -> DocumentConversionConfig:
    table = _packaged_table()
    table["backend"] = backend
    table["gotenberg"]["url"] = gotenberg_url
    table["soffice"]["binary"] = soffice_binary
    return DocumentConversionConfig.model_validate(table)


class TestDocumentConverterFactory:
    def test_the_packaged_default_converts_nothing(self) -> None:
        config = DocumentConversionConfig.model_validate(_packaged_table())

        assert config.backend == DocumentConversionBackend.NONE
        assert config.max_source_bytes == 50_000_000
        assert config.gotenberg.timeout_seconds == 360
        assert config.soffice.timeout_seconds == 120
        assert make_optional_document_converter_from_config(config=config) is None

    def test_a_booted_runtime_has_no_converter_by_default(self) -> None:
        assert get_optional_document_converter() is None

    def test_gotenberg_with_a_url_is_built(self) -> None:
        converter = make_optional_document_converter_from_config(config=_config(backend="gotenberg", gotenberg_url="http://localhost:3000"))

        assert isinstance(converter, GotenbergConverter)
        assert converter.converter_name == "gotenberg"

    def test_soffice_found_on_the_path_is_built(self, mocker: MockerFixture) -> None:
        which = mocker.patch("pipelex.tools.document_conversion.document_converter_factory.shutil.which", return_value="/usr/bin/soffice")

        converter = make_optional_document_converter_from_config(config=_config(backend="soffice"))

        assert isinstance(converter, SofficeConverter)
        which.assert_called_once_with("soffice")

    def test_a_relative_soffice_path_is_made_absolute(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.tools.document_conversion.document_converter_factory.shutil.which", return_value="tools/soffice")

        converter = make_optional_document_converter_from_config(config=_config(backend="soffice", soffice_binary="tools/soffice"))

        assert isinstance(converter, SofficeConverter)
        assert converter.binary_path == (Path.cwd() / "tools" / "soffice").resolve()
        assert converter.binary_path.is_absolute()

    @pytest.mark.parametrize("timeout_seconds", [120, 60])
    def test_a_gotenberg_timeout_not_past_its_budget_is_refused(self, timeout_seconds: float) -> None:
        table = _packaged_table()
        table["gotenberg"]["timeout_seconds"] = timeout_seconds
        table["gotenberg"]["budget_seconds"] = 120

        with pytest.raises(ValidationError, match=r"timeout_seconds .* must exceed budget_seconds"):
            DocumentConversionConfig.model_validate(table)

    @pytest.mark.parametrize(
        ("backend", "gotenberg_url", "soffice_binary"),
        [
            ("gotenberg", "", "soffice"),
            ("gotenberg", "   ", "soffice"),
            ("soffice", "", "no-such-soffice-binary-anywhere"),
            ("soffice", "", ""),
            ("gotenberg", "localhost:3000", "soffice"),
            ("gotenberg", "banana", "soffice"),
            ("gotenberg", "ftp://gotenberg:3000", "soffice"),
            ("gotenberg", "http://", "soffice"),
            ("gotenberg", "http://gotenberg:port", "soffice"),
        ],
        ids=[
            "gotenberg-without-url",
            "gotenberg-blank-url",
            "soffice-not-found",
            "soffice-blank-binary",
            "gotenberg-url-without-scheme",
            "gotenberg-url-not-a-url",
            "gotenberg-url-not-http",
            "gotenberg-url-without-host",
            "gotenberg-url-bad-port",
        ],
    )
    def test_a_backend_named_but_unusable_is_misconfigured(self, backend: str, gotenberg_url: str, soffice_binary: str) -> None:
        config = _config(backend=backend, gotenberg_url=gotenberg_url, soffice_binary=soffice_binary)

        with pytest.raises(DocumentConverterMisconfiguredError) as exc_info:
            make_optional_document_converter_from_config(config=config)

        problem = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.RUNTIME_MISCONFIGURED
        assert problem.diagnostics is not None
        assert problem.diagnostics.params == {"component": "runtime.document_conversion"}
