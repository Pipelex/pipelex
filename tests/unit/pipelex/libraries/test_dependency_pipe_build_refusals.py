from pathlib import Path

import pytest
from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.core.pipes.exceptions import PipeLoadRefusalError, PipeOperatorModelChoiceError
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager import LibraryManager

_DEP_DOMAIN = "harbour_dep"

_SCORE_PIPE = """
[pipe.score_tide]
type        = "PipeLLM"
description = "Score how favourable the tide is for leaving harbour"
inputs      = {{ tide_times = "Text" }}
output      = "Text"
{model_line}
prompt      = "Score how favourable these tide times are for leaving harbour: $tide_times"
"""

_PRELIMINARY_TEXT_PIPE = """
[concept.TideFact]
description = "When the tide turns at one harbour"

[concept.TideFact.structure]
harbour = { type = "text", description = "The harbour's name", required = true }

[pipe.extract_tide]
type               = "PipeLLM"
description        = "Extract the tide fact from the harbour board's notice"
inputs             = { tide_times = "Text" }
output             = "TideFact"
structuring_method = "preliminary_text"
model_to_structure = "@best-sonet"
prompt             = "Extract the tide fact from this notice: $tide_times"
"""


def _dep_bundle(*, pipes: str) -> str:
    return f'domain = "{_DEP_DOMAIN}"\ndescription = "A dependency package the harbour board publishes"\n{pipes}'


class _InternalInputRefusalError(PipelexError):
    error_domain = ErrorDomain.INPUT


class TestDependencyPipeBuildRefusals:
    def _load_dependency(self, *, mocker: MockerFixture, tmp_path: Path, bundle: str) -> Path:
        """Load one dependency package through ``_load_single_dependency``, returning its bundle file."""
        mthds_file = tmp_path / "harbour_dep.mthds"
        mthds_file.write_text(bundle, encoding="utf-8")
        resolved_dep = ResolvedDependency(
            alias="harbour_dep",
            address="github.com/harbour-board/harbour-dep",
            manifest=MethodsManifest(address="github.com/harbour-board/harbour-dep", version="1.0.0", description="A dependency package"),
            package_root=tmp_path,
            mthds_files=[mthds_file],
            exported_pipe_codes=None,
        )
        library = LibraryFactory.make_empty()
        mocker.patch.object(get_library_manager(), "get_current_library", return_value=library)
        LibraryManager()._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            library=library,
            resolved_dep=resolved_dep,
        )
        return mthds_file

    def test_unknown_model_in_a_dependency_pipe_names_the_dependency_file(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A dependency pipe is built outside the main load loop, and its refusal still carries the file it is declared in."""
        bundle = _dep_bundle(pipes=_SCORE_PIPE.format(model_line='model       = "@best-sonet"'))

        with pytest.raises(PipeOperatorModelChoiceError) as raised:
            self._load_dependency(mocker=mocker, tmp_path=tmp_path, bundle=bundle)

        refusal = raised.value
        assert refusal.pipe_code == "score_tide"
        assert refusal.domain_code == _DEP_DOMAIN
        assert refusal.field_name == "model"
        assert refusal.model_choice == "@best-sonet"
        assert refusal.source == str(tmp_path / "harbour_dep.mthds")

    def test_unknown_model_in_a_dependency_helper_names_the_authored_pipe(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A ``preliminary_text`` helper of a dependency pipe is reported on the pipe and field its author wrote."""
        with pytest.raises(PipeOperatorModelChoiceError) as raised:
            self._load_dependency(mocker=mocker, tmp_path=tmp_path, bundle=_dep_bundle(pipes=_PRELIMINARY_TEXT_PIPE))

        refusal = raised.value
        assert refusal.pipe_code == "extract_tide"
        assert refusal.field_name == "model_to_structure"
        assert refusal.source == str(tmp_path / "harbour_dep.mthds")

    def test_other_input_refusal_in_a_dependency_pipe_is_located(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Any other refusal of the caller's input raised while building a dependency pipe is located on that pipe and file."""
        mocker.patch(
            "pipelex.pipe_operators.llm.pipe_llm.check_llm_choice_with_deck",
            side_effect=_InternalInputRefusalError("internal detail: registry slot 7 is stale"),
        )
        bundle = _dep_bundle(pipes=_SCORE_PIPE.format(model_line='model       = "@best-gpt"'))

        with pytest.raises(PipeLoadRefusalError) as raised:
            self._load_dependency(mocker=mocker, tmp_path=tmp_path, bundle=bundle)

        refusal = raised.value
        assert refusal.pipe_code == "score_tide"
        assert refusal.domain_code == _DEP_DOMAIN
        assert refusal.source == str(tmp_path / "harbour_dep.mthds")
        assert isinstance(refusal.__cause__, _InternalInputRefusalError)
