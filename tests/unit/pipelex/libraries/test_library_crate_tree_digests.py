from pathlib import Path

from pipelex.core.method_trees.method_file_store import HeldFile, tree_of_held_files
from pipelex.core.method_trees.tree_bundle import TreeBundle, TreeBundleRef
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from tests.unit.pipelex.libraries.test_library_crate_data import BlueprintSamples


def _placed_blueprint(*, files: dict[str, bytes], tree_path: str | None) -> PipelexBundleBlueprint:
    blueprint = BlueprintSamples.SCORING_BUNDLE.model_copy(deep=True)
    tree = tree_of_held_files(files={path: HeldFile.of_bytes(data=data) for path, data in files.items()})
    blueprint.place_in_tree(tree_bundle=TreeBundle(tree=tree, tree_path=tree_path))
    return blueprint


_FILES = {
    "main.mthds": b'domain = "scoring"\n',
    "funcs/score.py": b"def compute_score(working_memory): ...\n",
    "templates/report.docx": bytes(range(256)),
}


class TestLibraryCrateTreeDigests:
    """A crate names the tree each pipe's bundle belongs to by its digest, and carries none of the tree's files."""

    def test_a_bundle_in_no_tree_names_none(self) -> None:
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[BlueprintSamples.SCORING_BUNDLE.model_copy(deep=True)])

        assert crate.tree_bundles == {}
        assert crate.tree_digests() == []

    def test_each_pipe_names_its_tree_by_digest_and_its_bundle_by_tree_path(self) -> None:
        blueprint = _placed_blueprint(files=_FILES, tree_path="main.mthds")
        tree_bundle = blueprint.tree_bundle
        assert tree_bundle is not None

        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[blueprint])

        assert crate.tree_bundles
        expected_ref = TreeBundleRef(tree_digest=tree_bundle.tree.digest, tree_path="main.mthds")
        assert all(tree_bundle_ref == expected_ref for tree_bundle_ref in crate.tree_bundles.values())
        assert crate.tree_digests() == [tree_bundle.tree.digest]

    def test_bundles_parsed_from_content_strings_name_their_tree_with_no_tree_path(self) -> None:
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[_placed_blueprint(files=_FILES, tree_path=None)])

        assert {tree_bundle_ref.tree_path for tree_bundle_ref in crate.tree_bundles.values()} == {None}

    def test_the_crate_carries_no_file_nor_host_path(self, tmp_path: Path) -> None:
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[_placed_blueprint(files=_FILES, tree_path="main.mthds")])
        crate_json = crate.model_dump_json()

        assert "compute_score(working_memory): ..." not in crate_json
        assert "funcs/score.py" not in crate_json
        assert str(tmp_path) not in crate_json
        assert set(LibraryCrate.model_fields) >= {"tree_bundles"}
        assert not {"pipe_func_files", "bundle_resources", "method_trees"} & set(LibraryCrate.model_fields)

    def test_tree_references_round_trip_and_stay_out_of_the_fingerprint(self) -> None:
        bare = LibraryCrateFactory.make_from_blueprints(blueprints=[BlueprintSamples.SCORING_BUNDLE.model_copy(deep=True)])
        placed = LibraryCrateFactory.make_from_blueprints(blueprints=[_placed_blueprint(files=_FILES, tree_path="main.mthds")])
        other_tree = LibraryCrateFactory.make_from_blueprints(
            blueprints=[
                _placed_blueprint(files={**_FILES, "funcs/score.py": b"def compute_score(working_memory): return 42\n"}, tree_path="main.mthds")
            ]
        )

        restored = LibraryCrate.model_validate_json(placed.model_dump_json())
        assert restored.tree_bundles == placed.tree_bundles
        assert bare.fingerprint != ""
        assert bare.fingerprint == placed.fingerprint == other_tree.fingerprint
        assert placed.tree_digests() != other_tree.tree_digests()
