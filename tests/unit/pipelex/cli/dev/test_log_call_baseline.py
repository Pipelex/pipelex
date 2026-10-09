from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.log_call_guard import (
    BASELINE_FILE,
    LogCallGuardError,
    OffendingCall,
    StaleEntry,
    build_baseline,
    collect_offending_calls,
    compare_with_baseline,
    find_offending_calls_in_source,
    load_baseline,
    prune_baseline,
    render_baseline,
    write_baseline,
)

#: Anchored on `tests/` by name rather than by a parent count, for the reason `test_hub_layering_guard.py` gives.
_REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

PILOT_MODULE = "pipelex/libraries/library_manager.py"
SAMPLE_PATH = "pipelex/core/sample_module.py"

INTERPOLATED = 'from pipelex import log\n\ndef load(alias):\n    log.warning(f"Loaded {alias}")\n'
CONVERTED = 'from pipelex import log\n\ndef load(alias):\n    log.warning("Loaded a dependency", fields={"dependency_alias": alias})\n'
MOVED = 'from pipelex import log\n\ndef fetch(alias):\n    log.warning(f"Loaded {alias}")\n'
REWORDED = 'from pipelex import log\n\ndef load(alias):\n    log.warning(f"Loaded the dependency {alias}")\n'
TWICE = 'from pipelex import log\n\ndef load(alias):\n    log.warning(f"Loaded {alias}")\n    log.warning(f"Loaded {alias}")\n'

LISTED_SIGNATURE = 'warning: f"Loaded {alias}"'
LISTED_KEY = f"{SAMPLE_PATH}::load"


def _offending(source: str) -> list[OffendingCall]:
    return find_offending_calls_in_source(source=source, relative_path=SAMPLE_PATH)


def _write_tree(*, root: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class TestLogCallBaseline:
    def test_a_baselined_call_passes(self) -> None:
        comparison = compare_with_baseline(offending=_offending(INTERPOLATED), baseline={LISTED_KEY: [LISTED_SIGNATURE]})
        assert comparison.is_clean

    def test_a_call_the_baseline_does_not_list_fails(self) -> None:
        comparison = compare_with_baseline(offending=_offending(INTERPOLATED), baseline={})
        assert [(call.key, call.signature) for call in comparison.unlisted] == [(LISTED_KEY, LISTED_SIGNATURE)]
        assert comparison.stale == []

    @pytest.mark.parametrize(
        ("topic", "source", "expected_unlisted"),
        [
            ("the call now complies", CONVERTED, []),
            ("the call moved to another function", MOVED, [(f"{SAMPLE_PATH}::fetch", LISTED_SIGNATURE)]),
            ("the call's message changed", REWORDED, [(LISTED_KEY, 'warning: f"Loaded the dependency {alias}"')]),
        ],
    )
    def test_a_listed_call_no_call_matches_any_more_is_stale_until_its_entry_is_removed(
        self, topic: str, source: str, expected_unlisted: list[tuple[str, str]]
    ) -> None:
        """The symmetric staleness: the listed signature fails the check, and whatever replaced the call is held as new code."""
        comparison = compare_with_baseline(offending=_offending(source), baseline={LISTED_KEY: [LISTED_SIGNATURE]})
        assert comparison.stale == [StaleEntry(key=LISTED_KEY, signature=LISTED_SIGNATURE)], topic
        assert [(call.key, call.signature) for call in comparison.unlisted] == expected_unlisted, topic

    def test_a_signature_is_listed_once_per_call_that_carries_it(self) -> None:
        """A second identical call beside a listed one is new, and a signature listed twice for one call is stale once."""
        assert len(compare_with_baseline(offending=_offending(TWICE), baseline={LISTED_KEY: [LISTED_SIGNATURE]}).unlisted) == 1
        doubled = compare_with_baseline(offending=_offending(INTERPOLATED), baseline={LISTED_KEY: [LISTED_SIGNATURE, LISTED_SIGNATURE]})
        assert doubled.stale == [StaleEntry(key=LISTED_KEY, signature=LISTED_SIGNATURE)]
        assert doubled.unlisted == []

    def test_pruning_removes_stale_signatures_and_never_adds_one(self) -> None:
        offending = _offending(MOVED)
        pruned = prune_baseline(baseline={LISTED_KEY: [LISTED_SIGNATURE]}, offending=offending)
        assert pruned == {}
        assert [call.key for call in compare_with_baseline(offending=offending, baseline=pruned).unlisted] == [f"{SAMPLE_PATH}::fetch"]

    def test_pruning_keeps_what_still_matches(self) -> None:
        baseline = {LISTED_KEY: [LISTED_SIGNATURE, LISTED_SIGNATURE]}
        assert prune_baseline(baseline=baseline, offending=_offending(INTERPOLATED)) == {LISTED_KEY: [LISTED_SIGNATURE]}

    def test_the_rendered_baseline_loads_back_as_written(self, tmp_path: Path) -> None:
        baseline = {
            LISTED_KEY: [LISTED_SIGNATURE, 'error: "a \\\\ backslash", title="tab\\there"'],
            "api/pipelex_api/sample.py::<module>": ['info: f"Quoted \\"{value}\\" and é"'],
        }
        write_baseline(baseline=baseline, repo_root=tmp_path)
        assert load_baseline(repo_root=tmp_path) == {key: sorted(calls) for key, calls in baseline.items()}
        rendered = render_baseline(baseline=baseline)
        assert rendered.index("api/pipelex_api/sample.py") < rendered.index(SAMPLE_PATH), "keys are written sorted"

    @pytest.mark.parametrize(
        ("topic", "content", "expected_message"),
        [
            ("a wrong version", 'version = 2\n["pipelex/a.py::f"]\ncalls = ["info: x"]\n', "must declare `version = 1`"),
            ("a key without a qualified name", 'version = 1\n["pipelex/a.py"]\ncalls = ["info: x"]\n', "is not of the form"),
            ("an entry with no calls", 'version = 1\n["pipelex/a.py::f"]\ncalls = []\n', "non-empty `calls` array"),
            ("an unknown key", 'version = 1\n["pipelex/a.py::f"]\ncalls = ["info: x"]\nreason = "later"\n', "unknown key(s)"),
            ("a blank call", 'version = 1\n["pipelex/a.py::f"]\ncalls = [" "]\n', "not a non-empty string"),
            ("invalid TOML", "version = \n", "is not valid TOML"),
        ],
    )
    def test_a_malformed_baseline_is_an_error_never_an_empty_one(self, tmp_path: Path, topic: str, content: str, expected_message: str) -> None:
        (tmp_path / BASELINE_FILE).write_text(content, encoding="utf-8")
        with pytest.raises(LogCallGuardError) as error_info:
            load_baseline(repo_root=tmp_path)
        assert expected_message in str(error_info.value), topic

    def test_a_missing_baseline_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(LogCallGuardError, match="was not found"):
            load_baseline(repo_root=tmp_path)

    def test_the_scan_reads_both_trees_and_leaves_the_facade_package_out(self, tmp_path: Path) -> None:
        _write_tree(
            root=tmp_path,
            files={
                "pipelex/core/sample_module.py": INTERPOLATED,
                "pipelex/tools/log/log_dispatch.py": INTERPOLATED,
                "api/pipelex_api/routes.py": INTERPOLATED,
            },
        )
        offending = collect_offending_calls(repo_root=tmp_path)
        assert [call.key for call in offending] == ["api/pipelex_api/routes.py::load", "pipelex/core/sample_module.py::load"]
        assert build_baseline(offending=offending) == {
            "api/pipelex_api/routes.py::load": [LISTED_SIGNATURE],
            "pipelex/core/sample_module.py::load": [LISTED_SIGNATURE],
        }

    def test_a_missing_scan_root_is_an_error_rather_than_a_pass(self, tmp_path: Path) -> None:
        _write_tree(root=tmp_path, files={"pipelex/core/sample_module.py": CONVERTED})
        with pytest.raises(LogCallGuardError, match="does not exist"):
            collect_offending_calls(repo_root=tmp_path)

    def test_the_committed_baseline_matches_the_tree(self) -> None:
        """What `make check-log-calls` gates, read here too so `make agent-test` catches a drift between the two."""
        comparison = compare_with_baseline(offending=collect_offending_calls(repo_root=_REPO_ROOT), baseline=load_baseline(repo_root=_REPO_ROOT))
        assert comparison.unlisted == []
        assert comparison.stale == []

    def test_the_pilot_module_has_no_baseline_entry(self) -> None:
        """The pilot follows the conventions throughout, so the baseline holds nothing for it."""
        baseline = load_baseline(repo_root=_REPO_ROOT)
        assert [key for key in baseline if key.startswith(f"{PILOT_MODULE}::")] == []
