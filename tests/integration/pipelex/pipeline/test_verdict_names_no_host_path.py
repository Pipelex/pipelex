"""Pin: a verdict a STRICT caller reads names no path on the host.

Every validation item is caller-facing, and STRICT disclosure keeps the items and the verdict's message
verbatim, so neither may carry a path on the host, in an item's ``source`` or in any message. Two origins
used to put one there:

- **An address-based dependency.** A package the bundle depends on by address is installed on the host,
  and its bundles were named by their install path. They are named by the package's address and the
  bundle's path inside the package instead, on every surface: the ``source`` of an item located inside the
  dependency, and the files a duplicate declaration inside it names.
- **The host's own library directories.** When submitted content is validated, the library directories
  loaded beside it are the host's: an item located in one of their files carries no ``source``, and a message
  naming one of their files names ``<host library file>`` instead. A run loads a host's directories
  untranslated, so their refusal is no verdict at all, and STRICT redacts it.

A bundle validated from a file keeps the full paths of its library directories: there they are the caller's.
"""

import json
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import DisclosureMode, PipelexError, ValidationErrorItem
from pipelex.config import get_config
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_bundle_translation import HOST_LIBRARY_FILE_PLACEHOLDER
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType

_DEPENDENCY_ADDRESS = "github.com/acme-tests/harbour-methods/tides"

_DEPENDENCY_MANIFEST = """
[package]
name        = "tides"
address     = "github.com/acme-tests/harbour-methods"
version     = "0.1.0"
description = "Tide notices for the harbour board, a package the tests depend on by address"

[exports.tides]
pipes = ["write_tide_notice"]
"""

_NOTICE_PIPE = """
[pipe.write_tide_notice]
type        = "PipeLLM"
description = "Write the tide notice for the harbour board"
inputs      = {{ tide_times = "Text" }}
output      = "Text"
{model_line}
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""

# A dependency bundle naming a model the deck does not define: the load refuses it with an item located
# on the dependency's pipe and file.
_DEPENDENCY_UNKNOWN_MODEL_BUNDLE = """
domain      = "tides"
description = "Write tide notices for the harbour board"
""" + _NOTICE_PIPE.format(model_line='model       = "@best-sonet"')

_DEPENDENCY_NOTICE_BUNDLE = """
domain      = "tides"
description = "Write tide notices for the harbour board"
""" + _NOTICE_PIPE.format(model_line="")

# The caller's bundle, which runs the dependency's pipe by the package's address.
_CALLER_BUNDLE = f"""
domain      = "harbour_notices"
description = "Post notices on the harbour board"
main_pipe   = "post_tide_notice"

[pipe.post_tide_notice]
type        = "PipeSequence"
description = "Post the tide notice on the harbour board"
inputs      = {{ tide_times = "Text" }}
output      = "Text"
steps       = [{{ pipe = "{_DEPENDENCY_ADDRESS}->tides.write_tide_notice", result = "tide_notice" }}]
"""

_VALID_CALLER_BUNDLE = """
domain      = "harbour_notices"
description = "Post notices on the harbour board"
main_pipe   = "write_board_notice"

[pipe.write_board_notice]
type        = "PipeLLM"
description = "Write the notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""

# A library bundle whose pipe outputs a concept its domain never declares.
_MISSPELLED_CONCEPT_LIBRARY_BUNDLE = """
domain      = "harbour_board"
description = "Notices of the harbour board"

[concept.BoardNotice]
description = "A notice pinned on the harbour board"

[pipe.pin_board_notice]
type        = "PipeLLM"
description = "Write a notice to pin on the harbour board"
inputs      = { tide_times = "Text" }
output      = "BoardNotise"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""

_BOARD_NOTICE_PIPE_BUNDLE = """
domain      = "harbour_board"
description = "Notices of the harbour board"

[pipe.pin_board_notice]
type        = "PipeLLM"
description = "Write a notice to pin on the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""


def _execution_config() -> Any:
    return get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, generate_usage=False, mock_inputs=True)


async def _run_setup(**kwargs: Any) -> None:
    await pipeline_run_setup(
        storage_scope="test/scope",
        user_id="test-user",
        execution_config=_execution_config(),
        pipe_run_mode=PipeRunMode.DRY,
        **kwargs,
    )


def _write(*, path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _host_path_markers(tmp_path: Path) -> list[str]:
    """The spellings of the test's directory on this host, any of which in a payload is a host path."""
    return sorted({str(tmp_path), str(tmp_path.resolve())})


def _strict_payload(verdict: ValidateBundleError) -> dict[str, Any]:
    return verdict.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)


def _assert_names_no_host_path(*, payload: dict[str, Any], tmp_path: Path) -> None:
    serialized = json.dumps(payload)
    for marker in _host_path_markers(tmp_path):
        assert marker not in serialized, f"the STRICT payload names a path on the host ({marker}): {serialized}"


class _Surface(NamedTuple):
    surface_id: str
    description: str


_SURFACES = [
    _Surface(surface_id="validate_contents", description="validating submitted content"),
    _Surface(surface_id="validate_contents_beside_host_library", description="validating submitted content beside a host's library"),
    _Surface(surface_id="validate_file", description="validating a bundle file"),
    _Surface(surface_id="run_contents", description="running submitted content"),
    _Surface(surface_id="run_contents_beside_host_library", description="running submitted content beside a host's library"),
]


@pytest.fixture(name="installed_methods_dir")
def installed_methods_dir_fixture(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Install methods in the test's own directory only, never in the machine's ones."""
    project_methods_dir = tmp_path / "host" / "installed-methods"
    project_methods_dir.mkdir(parents=True)
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", tmp_path / "host" / "global-methods")
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", project_methods_dir)
    return project_methods_dir


def _install_dependency(*, methods_dir: Path, bundles: dict[str, str]) -> Path:
    package_dir = methods_dir / "tides"
    _write(path=package_dir / "METHODS.toml", content=_DEPENDENCY_MANIFEST)
    for path_in_package, content in bundles.items():
        _write(path=package_dir / path_in_package, content=content)
    return package_dir


def _valid_host_library(*, tmp_path: Path) -> Path:
    host_library_dir = tmp_path / "host" / "library"
    _write(path=host_library_dir / "harbour_board.mthds", content=_BOARD_NOTICE_PIPE_BUNDLE)
    return host_library_dir


async def _load_on(*, surface: _Surface, caller_bundle: str, tmp_path: Path) -> None:
    match surface.surface_id:
        case "validate_contents":
            await validate_bundle(mthds_contents=[caller_bundle])
        case "validate_contents_beside_host_library":
            await validate_bundle(mthds_contents=[caller_bundle], library_dirs=[_valid_host_library(tmp_path=tmp_path)])
        case "validate_file":
            caller_file = _write(path=tmp_path / "caller" / "harbour_notices.mthds", content=caller_bundle)
            await validate_bundle(mthds_file_path=caller_file)
        case "run_contents":
            await _run_setup(mthds_contents=[caller_bundle])
        case "run_contents_beside_host_library":
            await _run_setup(mthds_contents=[caller_bundle], library_dirs=[str(_valid_host_library(tmp_path=tmp_path))])
        case _:
            pytest.fail(f"unknown surface {surface.surface_id}")


async def _verdict_on(*, surface: _Surface, caller_bundle: str, tmp_path: Path) -> ValidateBundleError:
    with pytest.raises(ValidateBundleError) as raised:
        await _load_on(surface=surface, caller_bundle=caller_bundle, tmp_path=tmp_path)
    return raised.value


@pytest.mark.asyncio(loop_scope="class")
class TestVerdictNamesNoHostPath:
    @pytest.mark.parametrize("surface", _SURFACES, ids=[surface.surface_id for surface in _SURFACES])
    async def test_a_dependency_refusal_is_located_by_the_packages_address(
        self, surface: _Surface, installed_methods_dir: Path, tmp_path: Path
    ) -> None:
        _install_dependency(methods_dir=installed_methods_dir, bundles={"notices/tide_notices.mthds": _DEPENDENCY_UNKNOWN_MODEL_BUNDLE})

        verdict = await _verdict_on(surface=surface, caller_bundle=_CALLER_BUNDLE, tmp_path=tmp_path)

        items = verdict.to_error_report().validation_errors or []
        (item,) = [item for item in items if item.error_type == PipeValidationErrorType.UNKNOWN_MODEL]
        assert item.pipe_code == "write_tide_notice"
        # The package's address, then the bundle's path inside the package: never where the host installed it.
        assert item.source == f"{_DEPENDENCY_ADDRESS}/notices/tide_notices.mthds", surface.description
        _assert_names_no_host_path(payload=_strict_payload(verdict), tmp_path=tmp_path)

    @pytest.mark.parametrize("surface", _SURFACES, ids=[surface.surface_id for surface in _SURFACES])
    async def test_a_duplicate_declaration_in_a_dependency_names_its_files_by_address(
        self, surface: _Surface, installed_methods_dir: Path, tmp_path: Path
    ) -> None:
        _install_dependency(
            methods_dir=installed_methods_dir,
            bundles={"notices/tide_notices.mthds": _DEPENDENCY_NOTICE_BUNDLE, "notices/tide_notices_copy.mthds": _DEPENDENCY_NOTICE_BUNDLE},
        )

        verdict = await _verdict_on(surface=surface, caller_bundle=_CALLER_BUNDLE, tmp_path=tmp_path)

        items: list[ValidationErrorItem] = verdict.to_error_report().validation_errors or []
        (item,) = items
        assert f"'{_DEPENDENCY_ADDRESS}/notices/tide_notices.mthds'" in item.message, surface.description
        assert f"'{_DEPENDENCY_ADDRESS}/notices/tide_notices_copy.mthds'" in item.message, surface.description
        _assert_names_no_host_path(payload=_strict_payload(verdict), tmp_path=tmp_path)

    async def test_a_host_library_item_carries_no_source_on_submitted_content(self, tmp_path: Path) -> None:
        host_library_dir = tmp_path / "host" / "library"
        _write(path=host_library_dir / "harbour_board.mthds", content=_MISSPELLED_CONCEPT_LIBRARY_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_contents=[_VALID_CALLER_BUNDLE], library_dirs=[host_library_dir])

        items = raised.value.to_error_report().validation_errors or []
        concept_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT]
        assert concept_items, f"expected an unresolved_concept item, got {items!r}"
        assert all(item.pipe_code == "pin_board_notice" for item in concept_items)
        # Located by its pipe and domain, never by its file on the host.
        assert all(item.source is None for item in items)
        _assert_names_no_host_path(payload=_strict_payload(raised.value), tmp_path=tmp_path)

    async def test_a_host_library_message_names_no_host_file_on_submitted_content(self, tmp_path: Path) -> None:
        host_library_dir = tmp_path / "host" / "library"
        _write(path=host_library_dir / "harbour_board.mthds", content=_BOARD_NOTICE_PIPE_BUNDLE)
        _write(path=host_library_dir / "harbour_board_copy.mthds", content=_BOARD_NOTICE_PIPE_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_contents=[_VALID_CALLER_BUNDLE], library_dirs=[host_library_dir])

        (item,) = raised.value.to_error_report().validation_errors or []
        assert "harbour_board.pin_board_notice" in item.message
        assert item.message.count(HOST_LIBRARY_FILE_PLACEHOLDER) >= 2
        _assert_names_no_host_path(payload=_strict_payload(raised.value), tmp_path=tmp_path)

    async def test_a_run_answers_a_host_library_refusal_without_a_host_path(self, tmp_path: Path) -> None:
        host_library_dir = tmp_path / "host" / "library"
        _write(path=host_library_dir / "harbour_board.mthds", content=_MISSPELLED_CONCEPT_LIBRARY_BUNDLE)

        with pytest.raises(PipelexError) as raised:
            await _run_setup(mthds_contents=[_VALID_CALLER_BUNDLE], library_dirs=[str(host_library_dir)])

        assert not isinstance(raised.value, ValidateBundleError), "a host's library directories load untranslated on a run"
        strict_payload = raised.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "validation_errors" not in strict_payload
        _assert_names_no_host_path(payload=strict_payload, tmp_path=tmp_path)

    async def test_a_bundle_file_keeps_the_paths_of_its_library_directories(self, tmp_path: Path) -> None:
        library_dir = tmp_path / "caller" / "library"
        library_file = _write(path=library_dir / "harbour_board.mthds", content=_MISSPELLED_CONCEPT_LIBRARY_BUNDLE)
        caller_file = _write(path=tmp_path / "caller" / "harbour_notices.mthds", content=_VALID_CALLER_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=caller_file, library_dirs=[library_dir])

        items = raised.value.to_error_report().validation_errors or []
        concept_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT]
        assert concept_items, f"expected an unresolved_concept item, got {items!r}"
        assert all(item.source == str(library_file) for item in concept_items)
