"""The MTHDS Test Corpus offline runner: every offline-tier entry runs live with its `inputs.json`.

An offline entry is one whose run needs no inference: a sequence of bindings, a PipeCompose, a PipeDocGen.
Running it is the only way to check the values a binding step binds, since the dry run fills every input
with a mock. A corpus entry holds no expected outputs, so what each entry must leave in working memory is
kept in this suite's test data, keyed by entry name, and every offline entry must have expectations there.
"""

import json
from typing import Any, cast

import pytest

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.mthds_corpus.loader import CorpusEntry, iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryTier, EntryValidity
from tests.integration.pipelex.test_extras.test_data import Absent, Bound, OfflineRunExpectations

_OFFLINE_ENTRIES = [entry for entry in iter_entries(validity=EntryValidity.VALID) if entry.manifest.tier is EntryTier.OFFLINE]


def _entry_id(entry: CorpusEntry) -> str:
    return entry.name


def _assert_matches(*, actual: Any, expected: Any, where: str) -> None:
    """Match `actual` against `expected` as a subset: every expected key, every list item, compared recursively."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{where}: expected a table, got {actual!r}"
        actual_dict = cast("dict[str, Any]", actual)
        for key, expected_value in cast("dict[str, Any]", expected).items():
            assert key in actual_dict, f"{where}: missing '{key}' in {actual_dict!r}"
            _assert_matches(actual=actual_dict[key], expected=expected_value, where=f"{where}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{where}: expected a list, got {actual!r}"
        actual_list = cast("list[Any]", actual)
        expected_list = cast("list[Any]", expected)
        assert len(actual_list) == len(expected_list), f"{where}: expected {len(expected_list)} items, got {actual_list!r}"
        for index_item, (actual_item, expected_item) in enumerate(zip(actual_list, expected_list, strict=True)):
            _assert_matches(actual=actual_item, expected=expected_item, where=f"{where}[{index_item}]")
        return
    assert actual == expected, f"{where}: expected {expected!r}, got {actual!r}"


def _content_dump(content: StuffContent) -> dict[str, Any]:
    if isinstance(content, ListContent):
        items = cast("ListContent[StuffContent]", content).items
        return {"items": [item.model_dump(mode="json") for item in items]}
    return content.model_dump(mode="json")


class TestMthdsCorpusOfflineRuns:
    def test_every_offline_entry_has_expectations(self) -> None:
        offline_names = {entry.name for entry in _OFFLINE_ENTRIES}
        assert offline_names == set(OfflineRunExpectations.BY_ENTRY), (
            "Every offline-tier entry needs its expectations in OfflineRunExpectations.BY_ENTRY, and nothing else may be listed there"
        )

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize("entry", _OFFLINE_ENTRIES, ids=_entry_id)
    async def test_offline_entry_runs_and_leaves_the_expected_values(self, entry: CorpusEntry) -> None:
        assert entry.inputs_path is not None, f"Offline entry '{entry.name}' has no inputs.json to run with"
        inputs = json.loads(entry.inputs_path.read_text(encoding="utf-8"))
        main_pipe = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=entry.bundle_path).main_pipe
        assert main_pipe is not None, f"Offline entry '{entry.name}' declares no main_pipe"

        result = await PipelexMTHDSProtocol(library_dirs=[str(entry.directory)], pipe_run_mode=PipeRunMode.LIVE).execute(
            pipe_code=main_pipe,
            inputs=inputs,
        )

        working_memory = result.pipe_output.working_memory
        for variable_name, expectation in OfflineRunExpectations.BY_ENTRY[entry.name].items():
            where = f"{entry.name}: '{variable_name}'"
            match expectation:
                case Bound(concept_ref=concept_ref, content=expected_content):
                    stuff = working_memory.get_optional_stuff(variable_name)
                    assert stuff is not None, f"{where} holds no value; absence: {working_memory.get_optional_absence(variable_name)}"
                    assert stuff.concept.concept_ref == concept_ref, f"{where} is a '{stuff.concept.concept_ref}', expected '{concept_ref}'"
                    _assert_matches(actual=_content_dump(stuff.content), expected=expected_content, where=where)
                case Absent(kind=kind):
                    assert working_memory.get_optional_stuff(variable_name) is None, f"{where} holds a value, expected an absence"
                    absence = working_memory.get_optional_absence(variable_name)
                    assert absence is not None, f"{where} has no recorded absence"
                    assert absence.kind == kind, f"{where} is recorded '{absence.kind}', expected '{kind}': {absence.reason}"
