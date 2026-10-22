"""Pin: a verdict a caller reads names no path on the host.

Every validation item is the caller's, and so is the caller's view of the verdict's problem, so neither may
carry a path on the host, in an item's ``source`` or in any message or detail. Two origins used to put one
there:

- **An address-based dependency.** A package the bundle depends on by address is installed on the host,
  and its bundles were named by their install path. They are named by the package's address and the
  bundle's path inside the package instead, on every surface: the ``source`` of an item located inside the
  dependency, and the files a duplicate declaration inside it names.
- **The host's own library directories.** When submitted content is validated or run, the library
  directories loaded beside it are the host's. A method of theirs that refuses to load is the deployment's
  fault, a ``HostLibraryLoadRefusalError`` and no verdict at all, whose message is the operator's alone. A verdict on the
  caller's own content keeps their files out too: an item located in one of them carries no ``source``,
  and a message naming one of them names ``<host library file>`` instead.

A bundle validated from a file keeps the full paths of its library directories: there they are the caller's, as
they are for a runtime told its library directories are the caller's own (``library_dirs_are_callers``).
"""

import json
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from mthds.protocol.problem.registry import ProblemDomain
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError, ValidationErrorItem
from pipelex.config import get_config
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.exceptions import HostLibraryTreeError
from pipelex.pipeline.exceptions import HostLibraryLoadRefusalError, ValidateBundleError
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol
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

# A library sequence declaring an output its last step does not produce: refused while the library is validated,
# located on the sequence from the pipe-source map.
_OUTPUT_MISMATCH_LIBRARY_BUNDLE = """
domain      = "harbour_board"
description = "Notices of the harbour board"

[pipe.post_board_notice]
type        = "PipeSequence"
description = "Post a notice on the harbour board"
inputs      = { tide_times = "Text" }
output      = "Image"
steps       = [{ pipe = "write_board_notice", result = "board_notice" }]

[pipe.write_board_notice]
type        = "PipeLLM"
description = "Write a notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
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


# The caller's bundle whose sequence calls a pipe by a code that is a slip from the host's `pin_board_notice`.
_MISTYPED_STEP_CALLER_BUNDLE = """
domain      = "harbour_notices"
description = "Post notices on the harbour board"
main_pipe   = "post_board_notice"

[pipe.post_board_notice]
type        = "PipeSequence"
description = "Write the notice, then post it"
inputs      = { tide_times = "Text" }
output      = "Text"
steps       = [{ pipe = "pin_board_notic", result = "notice" }]

[pipe.write_board_notice]
type        = "PipeLLM"
description = "Write the notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""


# A host library bundle whose PipeFunc's tree holds a module named like a standard-library module: the
# refusal names the module, the tree file and the bundle, never the tree's directory on the host.
_HOST_PIPE_FUNC_BUNDLE = """
domain      = "harbour_board"
description = "Format notices for the harbour board"

[pipe.format_board_notice]
type          = "PipeFunc"
description   = "Format the notice for the harbour board"
inputs        = { notice = "Text" }
output        = "Text"
function_name = "board_formatting.format_board_notice"
"""

_HOST_PIPE_FUNC_MODULE = """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def format_board_notice(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="board")
"""


def _execution_config() -> Any:
    return get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, generate_usage=False, mock_inputs=True)


async def _run_setup(**kwargs: Any) -> None:
    await pipeline_run_setup(
        storage_scope="test/scope",
        read_scope=None,
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


def _caller_payload(error: PipelexError) -> dict[str, Any]:
    """What a caller reads of a failure: its problem in the caller's view and, for a verdict, the validation items beside it."""
    payload: dict[str, Any] = {"problem": error.to_problem(view=ProblemView.CALLER).to_wire()}
    if isinstance(error, ValidateBundleError):
        payload["validation_errors"] = [item.model_dump(mode="json", exclude_none=True) for item in error.validation_error_items()]
    return payload


def _assert_names_no_host_path(*, payload: dict[str, Any], tmp_path: Path) -> None:
    serialized = json.dumps(payload)
    for marker in _host_path_markers(tmp_path):
        assert marker not in serialized, f"what the caller reads names a path on the host ({marker}): {serialized}"


def _assert_the_host_s_fault(*, error: PipelexError, tmp_path: Path) -> None:
    """The host's own directories are the operator's configuration: no verdict, no item, and nothing of the operator's message."""
    caller = error.to_problem(view=ProblemView.CALLER)
    assert caller.code == PipelexErrorCode.CONFIG_INVALID
    assert caller.domain == ProblemDomain.OPERATOR
    assert caller.errors is None
    assert error.message not in json.dumps(caller.to_wire())
    _assert_names_no_host_path(payload=_caller_payload(error), tmp_path=tmp_path)


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

        items = verdict.validation_error_items() or []
        (item,) = [item for item in items if item.error_type == PipeValidationErrorType.UNKNOWN_MODEL]
        assert item.pipe_code == "write_tide_notice"
        # The package's address, then the bundle's path inside the package: never where the host installed it.
        assert item.source == f"{_DEPENDENCY_ADDRESS}/notices/tide_notices.mthds", surface.description
        _assert_names_no_host_path(payload=_caller_payload(verdict), tmp_path=tmp_path)

    @pytest.mark.parametrize("surface", _SURFACES, ids=[surface.surface_id for surface in _SURFACES])
    async def test_a_duplicate_declaration_in_a_dependency_names_its_files_by_address(
        self, surface: _Surface, installed_methods_dir: Path, tmp_path: Path
    ) -> None:
        _install_dependency(
            methods_dir=installed_methods_dir,
            bundles={"notices/tide_notices.mthds": _DEPENDENCY_NOTICE_BUNDLE, "notices/tide_notices_copy.mthds": _DEPENDENCY_NOTICE_BUNDLE},
        )

        verdict = await _verdict_on(surface=surface, caller_bundle=_CALLER_BUNDLE, tmp_path=tmp_path)

        items: list[ValidationErrorItem] = verdict.validation_error_items() or []
        # One item per bundle declaring it, each located on its bundle and naming the other by the dependency's address.
        first_file = f"{_DEPENDENCY_ADDRESS}/notices/tide_notices.mthds"
        copy_file = f"{_DEPENDENCY_ADDRESS}/notices/tide_notices_copy.mthds"
        assert sorted((item.source, item.message) for item in items) == [
            (first_file, f"Pipe 'tides.write_tide_notice' is declared here and in '{copy_file}'."),
            (copy_file, f"Pipe 'tides.write_tide_notice' is declared here and in '{first_file}'."),
        ], surface.description
        _assert_names_no_host_path(payload=_caller_payload(verdict), tmp_path=tmp_path)

    @pytest.mark.parametrize("surface", _SURFACES, ids=[surface.surface_id for surface in _SURFACES])
    async def test_a_dependency_s_tree_refusal_names_the_package_by_its_address(
        self, surface: _Surface, installed_methods_dir: Path, tmp_path: Path
    ) -> None:
        package_dir = _install_dependency(methods_dir=installed_methods_dir, bundles={"notices/tide_notices.mthds": _DEPENDENCY_NOTICE_BUNDLE})
        # The membership rule refuses a symbolic link, so the package's tree cannot be listed.
        (package_dir / "notices" / "linked_notices.mthds").symlink_to(package_dir / "notices" / "tide_notices.mthds")

        verdict = await _verdict_on(surface=surface, caller_bundle=_CALLER_BUNDLE, tmp_path=tmp_path)

        assert "github.com/acme-tests/harbour-methods" in verdict.message, surface.description
        assert "notices/linked_notices.mthds" in verdict.message, surface.description
        assert "max_files" not in verdict.message, "no advice about this host's limits reaches the caller"
        _assert_names_no_host_path(payload=_caller_payload(verdict), tmp_path=tmp_path)

    @pytest.mark.parametrize(
        "surface",
        [surface for surface in _SURFACES if surface.surface_id.endswith("_beside_host_library")],
        ids=lambda surface: surface.surface_id,
    )
    async def test_a_host_library_tree_that_cannot_be_listed_is_the_host_s_fault(self, surface: _Surface, tmp_path: Path) -> None:
        """Beside submitted content, the host's own directories are no input of the caller's: no verdict, and no host path."""
        host_library_dir = _valid_host_library(tmp_path=tmp_path)
        (host_library_dir / "linked_board.mthds").symlink_to(host_library_dir / "harbour_board.mthds")

        with pytest.raises(HostLibraryTreeError) as raised:
            await _load_on(surface=surface, caller_bundle=_VALID_CALLER_BUNDLE, tmp_path=tmp_path)

        _assert_the_host_s_fault(error=raised.value, tmp_path=tmp_path)

    async def test_a_callers_library_tree_that_cannot_be_listed_is_their_verdict(self, tmp_path: Path) -> None:
        library_dir = _valid_host_library(tmp_path=tmp_path)
        (library_dir / "linked_board.mthds").symlink_to(library_dir / "harbour_board.mthds")
        runtime = PipelexMTHDSProtocol(
            library_dirs=[str(library_dir)],
            library_dirs_are_callers=True,
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=_execution_config(),
        )

        with pytest.raises(ValidateBundleError) as raised:
            await runtime.validate(mthds_contents=[_VALID_CALLER_BUNDLE])

        assert "linked_board.mthds" in raised.value.message

    @pytest.mark.parametrize(
        "host_library_files",
        [
            {"harbour_board.mthds": _MISSPELLED_CONCEPT_LIBRARY_BUNDLE},
            {"harbour_board.mthds": _OUTPUT_MISMATCH_LIBRARY_BUNDLE},
            {"harbour_board.mthds": _BOARD_NOTICE_PIPE_BUNDLE, "harbour_board_copy.mthds": _BOARD_NOTICE_PIPE_BUNDLE},
            {"harbour_board.mthds": _HOST_PIPE_FUNC_BUNDLE, "board_formatting.py": _HOST_PIPE_FUNC_MODULE, "json.py": "SHADOW = True\n"},
        ],
        ids=["unresolved_concept", "sequence_output_mismatch", "duplicate_declaration", "pipe_func_refused"],
    )
    async def test_a_host_library_refusal_beside_submitted_content_is_the_host_s_fault(
        self, host_library_files: dict[str, str], tmp_path: Path
    ) -> None:
        """A method of the host's own directories that refuses to load is the deployment's fault: no verdict, and no host path."""
        host_library_dir = tmp_path / "host" / "library"
        for file_name, content in host_library_files.items():
            _write(path=host_library_dir / file_name, content=content)

        with pytest.raises(HostLibraryLoadRefusalError) as raised:
            await validate_bundle(mthds_contents=[_VALID_CALLER_BUNDLE], library_dirs=[host_library_dir])

        _assert_the_host_s_fault(error=raised.value, tmp_path=tmp_path)

    async def test_a_verdict_on_the_callers_content_names_no_host_library_file(self, tmp_path: Path) -> None:
        """The caller's content declaring a pipe the host's directories declare too: the caller's verdict, naming no host file."""
        host_library_dir = tmp_path / "host" / "library"
        _write(path=host_library_dir / "harbour_board.mthds", content=_BOARD_NOTICE_PIPE_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_contents=[_BOARD_NOTICE_PIPE_BUNDLE], library_dirs=[host_library_dir])

        # The host's own declaration is no item of the caller's: the caller's declaration is, naming the host's file by a placeholder.
        (item,) = raised.value.validation_error_items() or []
        assert "harbour_board.pin_board_notice" in item.message
        assert HOST_LIBRARY_FILE_PLACEHOLDER in item.message
        _assert_names_no_host_path(payload=_caller_payload(raised.value), tmp_path=tmp_path)

    async def test_a_mistyped_selection_is_offered_no_pipe_of_the_host_s_library(self, tmp_path: Path) -> None:
        with pytest.raises(PipelexError) as raised:
            await _run_setup(
                mthds_contents=[_VALID_CALLER_BUNDLE], library_dirs=[str(_valid_host_library(tmp_path=tmp_path))], pipe_code="pin_board_notic"
            )

        assert raised.value.caller_params() == {"pipe": "pin_board_notic", "suggestions": ["harbour_notices.write_board_notice"]}

    async def test_a_mistyped_reference_is_offered_no_pipe_of_the_host_s_library(self, tmp_path: Path) -> None:
        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_contents=[_MISTYPED_STEP_CALLER_BUNDLE], library_dirs=[_valid_host_library(tmp_path=tmp_path)])

        (item,) = raised.value.validation_error_items() or []
        assert item.params is not None
        assert item.params["candidates"] == ["harbour_notices.post_board_notice", "harbour_notices.write_board_notice"]
        assert "pin_board_notice" not in item.message

    async def test_a_run_answers_a_host_library_refusal_without_a_host_path(self, tmp_path: Path) -> None:
        host_library_dir = tmp_path / "host" / "library"
        _write(path=host_library_dir / "harbour_board.mthds", content=_MISSPELLED_CONCEPT_LIBRARY_BUNDLE)

        with pytest.raises(PipelexError) as raised:
            await _run_setup(mthds_contents=[_VALID_CALLER_BUNDLE], library_dirs=[str(host_library_dir)])

        assert not isinstance(raised.value, ValidateBundleError), "a host's library directories load untranslated on a run"
        _assert_the_host_s_fault(error=raised.value, tmp_path=tmp_path)

    async def test_a_bundle_file_keeps_the_paths_of_its_library_directories(self, tmp_path: Path) -> None:
        library_dir = tmp_path / "caller" / "library"
        library_file = _write(path=library_dir / "harbour_board.mthds", content=_MISSPELLED_CONCEPT_LIBRARY_BUNDLE)
        caller_file = _write(path=tmp_path / "caller" / "harbour_notices.mthds", content=_VALID_CALLER_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=caller_file, library_dirs=[library_dir])

        items = raised.value.validation_error_items() or []
        concept_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT]
        assert concept_items, f"expected an unresolved_concept item, got {items!r}"
        assert all(item.source == str(library_file) for item in concept_items)

    async def test_a_runtime_told_its_library_is_the_hosts_answers_its_refusal_as_the_hosts_fault(self, tmp_path: Path) -> None:
        library_dir = tmp_path / "library"
        _write(path=library_dir / "harbour_board.mthds", content=_MISSPELLED_CONCEPT_LIBRARY_BUNDLE)
        runtime = PipelexMTHDSProtocol(
            library_dirs=[str(library_dir)],
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=_execution_config(),
        )

        with pytest.raises(HostLibraryLoadRefusalError) as raised:
            await runtime.validate(mthds_contents=[_VALID_CALLER_BUNDLE])

        _assert_the_host_s_fault(error=raised.value, tmp_path=tmp_path)

    async def test_a_runtime_told_its_library_is_the_callers_validates_content_against_it(self, tmp_path: Path) -> None:
        library_dir = tmp_path / "library"
        library_file = _write(path=library_dir / "harbour_board.mthds", content=_MISSPELLED_CONCEPT_LIBRARY_BUNDLE)
        runtime = PipelexMTHDSProtocol(
            library_dirs=[str(library_dir)],
            library_dirs_are_callers=True,
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=_execution_config(),
        )

        with pytest.raises(ValidateBundleError) as raised:
            await runtime.validate(mthds_contents=[_VALID_CALLER_BUNDLE])

        items = raised.value.validation_error_items() or []
        concept_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT]
        assert concept_items, f"expected an unresolved_concept item, got {items!r}"
        assert all(item.source == str(library_file) for item in concept_items)
