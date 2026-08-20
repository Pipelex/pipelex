"""The MTHDS Test Corpus tag vocabulary — the closed set an entry's ``covers`` draws from.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Tag vocabulary".
``vocabulary.toml`` is generated in full by ``pipelex-dev generate-corpus-vocabulary`` and
committed, so a consumer reading it needs neither the generator nor a registry walk. This
module is the reader; the generator lives in the dev CLI, which the wheel excludes.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.test_extras.mthds_corpus.resources import corpus_root
from pipelex.tools.misc.toml_utils import load_toml_from_path

VOCABULARY_FILE_NAME = "vocabulary.toml"

ERROR_NAMESPACE = "error"


class ValidationLayer(StrEnum):
    """The layer of checking a fault is caught at — the value of a tag's ``fails_at``.

    The two layers are ordered, and ``fails_at`` names the **earliest** one that rejects a bundle
    carrying the fault. ``SCHEMA`` is what a JSON-Schema check over the raw document already
    catches, because the fault is structural: a section that is missing a required key, or one
    whose value is outside a closed set. ``RUNTIME`` is everything a document has to be
    *interpreted* to notice — an unresolved reference, an input the flow never provides, an
    output whose concept does not fit.

    ``SCHEMA`` faults are rejected by the runtime too. The layers name where a fault is caught
    first, not who is allowed to catch it, which is why a schema-fault entry still declares the
    ``expected_error`` the runtime reports for it. The spelling matches plxt's own
    ``error[schema]`` diagnostic category, so a consumer branching on this field and a human
    reading a linter's output are using one word for one thing.
    """

    SCHEMA = "schema"
    RUNTIME = "runtime"

    @property
    def is_schema(self) -> bool:
        """True for the layer a check of the document's shape alone already rejects."""
        match self:
            case ValidationLayer.SCHEMA:
                return True
            case ValidationLayer.RUNTIME:
                return False


class VocabularyTag(BaseModel):
    """One tag in the vocabulary.

    A tag says where it came from, and the two kinds of namespace answer that differently.
    A **generated** tag carries ``code``, the registry code it was derived from. A
    **hand-maintained** tag has no registry to point at, so it carries ``description`` — a
    one-line statement of the language feature it names, which is the only place that meaning
    can live. ``excluded`` carries the reason a tag is not required to have a focused entry,
    and is present only on excluded tags.

    ``fails_at`` is the ``error.*`` namespace's own field, and it is the answer to a question
    every structural consumer was otherwise guessing at: does a check that only reads the
    document's *shape* reject this fault, or does it take the runtime to notice? A consumer
    sweeping the corpus with a schema validator expects a diagnostic on exactly the entries
    whose tag says :attr:`ValidationLayer.SCHEMA`, and expects silence on the rest — so the
    signal turns a sweep that had to hardcode a list of known-structural faults into one that
    reads the corpus it is sweeping.

    Every field is optional here, and no validator enforces which combinations are legal,
    deliberately. This model only *reads*: the generator is the single writer, and the drift
    gate regenerates the committed file in memory and compares it byte for byte, so a tag
    carrying a nonsensical combination cannot reach a reader through the channel this model
    serves. A validator would guard a state the pipeline cannot produce.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str | None = None
    description: str | None = None
    excluded: str | None = None
    fails_at: ValidationLayer | None = None


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
    def schema_fault_tags(self) -> frozenset[str]:
        """The tags whose fault a check of the document's shape alone already rejects.

        This is the consumer rule in one call: a structural sweep — a JSON-Schema pass, an editor
        diagnostic, a linter run over the corpus — expects a diagnostic on an entry covering a tag
        in this set, and expects none on any other entry. Reading it off the shipped vocabulary is
        what keeps a consumer from re-deriving the runtime's own knowledge downstream, whether by
        hardcoding a list of structural faults or by pattern-matching tag names.
        """
        return frozenset(
            f"{namespace}.{local_name}"
            for namespace, tags_in_namespace in self.namespaces.items()
            for local_name, tag in tags_in_namespace.items()
            if tag.fails_at is not None and tag.fails_at.is_schema
        )

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
