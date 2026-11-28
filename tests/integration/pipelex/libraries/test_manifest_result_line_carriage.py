from collections.abc import Callable
from pathlib import Path

from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint

_LINE = "Scored {{ output.text }}"


def _bundle(domain: str) -> str:
    return f"""\
domain = "{domain}"
description = "A {domain} method"

[pipe.score]
type = "PipeCompose"
description = "Score the data"
inputs = {{ data = "Text" }}
output = "Text"
template = "Score of $data"

[pipe.helper]
type = "PipeCompose"
description = "Help"
inputs = {{ data = "Text" }}
output = "Text"
template = "Help with $data"
"""


def _manifest(*, domain: str, result_line: str | None) -> str:
    line = f'result_line = "{result_line}"\n' if result_line is not None else ""
    return f"""\
[package]
address = "github.com/pipelex-tests/{domain}"
version = "1.0.0"
description = "A method wording its result line"
main_pipe = "score"
{line}
[exports.{domain}]
pipes = ["score"]
"""


def _method_dir(*, root: Path, domain: str, result_line: str | None) -> Path:
    method_dir = root / domain
    method_dir.mkdir()
    (method_dir / "METHODS.toml").write_text(_manifest(domain=domain, result_line=result_line), encoding="utf-8")
    (method_dir / f"{domain}.mthds").write_text(_bundle(domain), encoding="utf-8")
    return method_dir


def _bundle_file_blueprint(method_dir: Path, domain: str) -> PipelexBundleBlueprint:
    return MthdsParser.make_pipelex_bundle_blueprint(bundle_path=method_dir / f"{domain}.mthds")


def _result_lines(library_id: str) -> dict[str, str | None]:
    pipe_library = get_library_manager().get_library(library_id=library_id).pipe_library
    return {pipe_ref: pipe.result_line for pipe_ref, pipe in pipe_library.root.items() if pipe.domain_code in {"scoring", "grading"}}


class TestManifestResultLineCarriage:
    def test_a_bundle_file_run_alone_takes_the_line_of_the_manifest_above_it(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """A bundle file loaded through its blueprints, as `pipelex run bundle` loads it, puts the line on its main pipe alone."""
        method_dir = _method_dir(root=tmp_path, domain="scoring", result_line=_LINE)
        library_id = load_empty_library()
        get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[_bundle_file_blueprint(method_dir, "scoring")])

        assert _result_lines(library_id) == {"scoring.score": _LINE, "scoring.helper": None}

    def test_a_library_rebuilt_from_the_crate_keeps_the_line(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """The crate carries the line by pipe ref, so a library a worker rebuilds from it words its runs the same."""
        method_dir = _method_dir(root=tmp_path, domain="scoring", result_line=_LINE)
        library_manager = get_library_manager()
        source_library_id = load_empty_library()
        library_manager.load_from_blueprints(library_id=source_library_id, blueprints=[_bundle_file_blueprint(method_dir, "scoring")])
        crate = library_manager.get_crate(source_library_id)
        assert crate is not None
        assert crate.result_lines == {"scoring.score": _LINE}
        restricted = crate.restricted_to_pipe(pipe_ref="scoring.score")
        assert restricted is not None
        assert restricted.result_lines == {"scoring.score": _LINE}
        transported = LibraryCrate.model_validate_json(crate.model_dump_json())
        library_manager.teardown(library_id=source_library_id)

        rebuilt_library_id = load_empty_library()
        library_manager.load_from_crate(library_id=rebuilt_library_id, crate=transported)

        assert _result_lines(rebuilt_library_id) == {"scoring.score": _LINE, "scoring.helper": None}

    def test_content_strings_take_the_line_of_the_manifest_submitted_beside_them(self, load_empty_library: Callable[[], str]):
        """Bundles sent as strings, with the method's other files, are worded by the `METHODS.toml` among those files."""
        library_manager = get_library_manager()
        library_id = load_empty_library()
        library_manager.add_submitted_files(
            library_id=library_id, submitted_files={"METHODS.toml": _manifest(domain="scoring", result_line=_LINE).encode("utf-8")}
        )
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_bundle("scoring"))
        library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])

        assert _result_lines(library_id) == {"scoring.score": _LINE, "scoring.helper": None}

    def test_each_package_of_one_load_takes_its_own_line(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """Two packages loaded together are each worded by their own manifest, never by the first one's."""
        scoring_dir = _method_dir(root=tmp_path, domain="scoring", result_line=_LINE)
        grading_dir = _method_dir(root=tmp_path, domain="grading", result_line="Graded {{ output.text }}")
        library_id = load_empty_library()
        get_library_manager().load_libraries(library_id=library_id, library_dirs=[scoring_dir, grading_dir])

        assert _result_lines(library_id) == {
            "scoring.score": _LINE,
            "scoring.helper": None,
            "grading.score": "Graded {{ output.text }}",
            "grading.helper": None,
        }

    def test_a_method_without_a_result_line_keeps_its_fingerprint(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """The line joins the fingerprint only when there is one: a method without it hashes as it did without a manifest."""
        plain_root = tmp_path / "plain"
        worded_root = tmp_path / "worded"
        plain_root.mkdir()
        worded_root.mkdir()
        blueprints = {
            "bare": MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_bundle("scoring")),
            "plain": _bundle_file_blueprint(_method_dir(root=plain_root, domain="scoring", result_line=None), "scoring"),
            "worded": _bundle_file_blueprint(_method_dir(root=worded_root, domain="scoring", result_line=_LINE), "scoring"),
        }
        library_manager = get_library_manager()
        crates: dict[str, LibraryCrate] = {}
        library_id: str | None = None
        for name, blueprint in blueprints.items():
            if library_id is not None:
                # The fixture tears down the last library it opened, and each earlier one is torn down here.
                library_manager.teardown(library_id=library_id)
            library_id = load_empty_library()
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
            crate = library_manager.get_crate(library_id)
            assert crate is not None
            crates[name] = crate

        assert crates["plain"].result_lines == {}
        assert crates["plain"].fingerprint == crates["bare"].fingerprint
        assert crates["worded"].result_lines == {"scoring.score": _LINE}
        assert crates["worded"].fingerprint != crates["bare"].fingerprint
