"""The MTHDS Test Corpus tag vocabulary — the closed set an entry's ``covers`` draws from.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Tag vocabulary".
``vocabulary.toml`` is generated in full by ``pipelex-dev generate-corpus-vocabulary`` and
committed, so a consumer reading it needs neither the generator nor a registry walk. This
module is the reader; the generator lives in the dev CLI, which the wheel excludes.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.test_extras.mthds_corpus.resources import corpus_root
from pipelex.tools.misc.toml_utils import load_toml_from_path

VOCABULARY_FILE_NAME = "vocabulary.toml"


class VocabularyTag(BaseModel):
    """One tag in the vocabulary.

    ``code`` is the registry code the tag was generated from. ``excluded`` carries the reason a
    tag is not required to have a focused entry, and is present only on excluded tags.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    excluded: str | None = None


class CorpusVocabulary(BaseModel):
    """The whole vocabulary, namespace by namespace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    namespaces: dict[str, dict[str, VocabularyTag]]

    @property
    def tags(self) -> frozenset[str]:
        """Every declared tag, in full ``<namespace>.<local_name>`` form."""
        declared: set[str] = set()
        for namespace, tags_in_namespace in self.namespaces.items():
            declared.update(f"{namespace}.{local_name}" for local_name in tags_in_namespace)
        return frozenset(declared)

    @property
    def required_tags(self) -> frozenset[str]:
        """The tags the exhaustivity gate requires a focused entry for — every tag that is not excluded."""
        required: set[str] = set()
        for namespace, tags_in_namespace in self.namespaces.items():
            for local_name, tag in tags_in_namespace.items():
                if tag.excluded is None:
                    required.add(f"{namespace}.{local_name}")
        return frozenset(required)


def vocabulary_path() -> Path:
    """Where the committed vocabulary file sits."""
    return corpus_root() / VOCABULARY_FILE_NAME


def load_vocabulary() -> CorpusVocabulary:
    """Read the committed ``vocabulary.toml`` that ships beside the corpus entries."""
    return CorpusVocabulary(namespaces=load_toml_from_path(vocabulary_path()))
