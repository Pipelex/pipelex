from pathlib import Path

from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.libraries.library_manager import MTHDS_METHODS_DIRNAME, find_methods_dirs_from_blueprints
from pipelex.mthds_parsing.parser import MthdsParser


def _bundle(*, domain: str = "host_files_tests", pipe_fields: str = "") -> str:
    return f"""
domain = "{domain}"
main_pipe = "summarize"

[pipe.summarize]
type        = "PipeLLM"
description = "Summarize the text"
inputs      = {{ text = "Text" }}
output      = "Text"
prompt      = "Summarize $text"
{pipe_fields}
"""


_BUNDLE = _bundle()


def _write_bundle(*, directory: Path, mthds: str = _BUNDLE) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(mthds, encoding="utf-8")
    return bundle_path


class TestHostBundleFiles:
    def test_only_a_bundle_read_from_a_file_here_has_a_host_file(self, tmp_path: Path) -> None:
        """A content string's label, however real a path it names, is not a file this host read the bundle from."""
        bundle_path = _write_bundle(directory=tmp_path)

        from_file = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=bundle_path)
        from_content = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_BUNDLE, mthds_source=str(bundle_path))

        assert from_file.host_bundle_file == bundle_path
        assert from_content.host_bundle_file is None
        assert from_content.source == str(bundle_path)

    def test_the_crate_carries_the_host_file_of_its_file_loaded_pipes_only(self, tmp_path: Path) -> None:
        """A `source` the bundle's text writes on a pipe, or a caller's label, never becomes a file to read beside."""
        bundle_path = _write_bundle(directory=tmp_path)
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        content_with_a_written_source = _bundle(domain="host_files_other", pipe_fields=f'source = "{bundle_path}"')

        crate = LibraryCrateFactory.make_from_blueprints(
            blueprints=[
                MthdsParser.make_pipelex_bundle_blueprint(bundle_path=bundle_path),
                MthdsParser.make_pipelex_bundle_blueprint(mthds_content=content_with_a_written_source, mthds_source=str(other_dir / "x.mthds")),
            ]
        )

        assert crate.host_bundle_files == {"host_files_tests.summarize": str(bundle_path)}
        assert crate.pipes["host_files_other.summarize"].source == str(bundle_path)
        assert crate.fingerprint == LibraryCrate.model_validate_json(crate.model_dump_json()).fingerprint

    def test_method_packages_are_searched_above_a_file_read_here_only(self, tmp_path: Path) -> None:
        """Walking up from a caller's label would search this host's directories wherever the caller pointed."""
        methods_dir = tmp_path / MTHDS_METHODS_DIRNAME
        methods_dir.mkdir(parents=True)
        bundle_dir = tmp_path / "project"
        bundle_dir.mkdir()
        bundle_path = _write_bundle(directory=bundle_dir)

        from_file = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=bundle_path)
        from_content = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_BUNDLE, mthds_source=str(bundle_path))

        assert methods_dir.resolve() in find_methods_dirs_from_blueprints([from_file])
        assert find_methods_dirs_from_blueprints([from_content]) == []
