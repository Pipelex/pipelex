"""This repo's own linter config, gated against the corpus's ``fails_at`` signal.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Tag vocabulary".

`pipelex` is the first consumer of its own signal, and `.pipelex/plxt.toml` is where it consumes
it. Every deliberately invalid corpus entry used to be excluded from `plxt lint` by one blanket
glob, because *some* of them carry a structural fault the schema rejects and the config had no way
to say which. `fails_at` is that way: the entries whose tag says `schema` stay excluded, and every
other invalid entry is linted like any ordinary `.mthds` file in the tree.

The config is gated rather than generated because `plxt` is a static binary reading a static file —
there is nothing to hook a generation step onto. What this test buys is the same guarantee in the
direction that matters: a fault mis-declared `runtime` leaves its entry linted, and `make plxt-lint`
goes red naming it, which is what keeps the signal measured instead of merely asserted.
"""

from pathlib import Path
from typing import Any

from pipelex.test_extras.mthds_corpus.loader import iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryValidity
from pipelex.test_extras.mthds_corpus.vocabulary import load_vocabulary
from pipelex.tools.misc.toml_utils import load_toml_from_path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLXT_CONFIG_PATH = _REPO_ROOT / ".pipelex" / "plxt.toml"

_CORPUS_GLOB_MARKER = "mthds_corpus"


def _corpus_exclusion_globs() -> set[str]:
    """The corpus-related entries of the config's top-level `exclude` list.

    Narrowed by the marker rather than compared whole: the rest of that list is ordinary build-output
    noise (`.venv/**`, `target/**`) that has nothing to do with the corpus and should not have to be
    restated here to keep this gate green.
    """
    config: dict[str, Any] = load_toml_from_path(_PLXT_CONFIG_PATH)
    excluded: list[str] = config["exclude"]
    return {glob for glob in excluded if _CORPUS_GLOB_MARKER in glob}


class TestMthdsCorpusPlxtExclusions:
    def test_the_excluded_entries_are_exactly_the_schema_fault_entries(self) -> None:
        schema_fault_tags = load_vocabulary().schema_fault_tags
        assert schema_fault_tags, "The vocabulary declares no schema fault, so this gate would pass vacuously"

        expected = {
            f"**/mthds_corpus/entries/{entry.name}/*.mthds"
            for entry in iter_entries(validity=EntryValidity.INVALID)
            if not schema_fault_tags.isdisjoint(entry.manifest.covers)
        }
        assert _corpus_exclusion_globs() == expected, (
            "`.pipelex/plxt.toml`'s corpus exclusions disagree with the vocabulary's `fails_at` signal. "
            "An entry whose tag says `schema` must be excluded — the schema rejects it as the very error "
            "it exists to trigger — and every other invalid entry must be linted like any other .mthds file."
        )
