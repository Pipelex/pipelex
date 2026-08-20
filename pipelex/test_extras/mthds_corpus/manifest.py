"""The MTHDS Test Corpus entry manifest — the strict model behind every ``entry.toml``.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "The entry manifest".
The model is deliberately strict: an unknown key is an error rather than a
forward-compatibility affordance, so a new field is a change to the spec and to this
model in the same commit.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MANIFEST_FILE_NAME = "entry.toml"

ENTRY_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"


class EntryValidity(StrEnum):
    """Whether an entry's bundle is expected to validate."""

    VALID = "valid"
    INVALID = "invalid"


class EntryTier(StrEnum):
    """The cheapest conformance tier at which an entry is meaningful."""

    STATIC = "static"
    DRY = "dry"
    OFFLINE = "offline"
    INFERENCE = "inference"

    @property
    def rank(self) -> int:
        """Position in the cheapest-first tier order.

        A consumer running at tier ``T`` runs every entry whose rank is at most ``T``'s.
        """
        match self:
            case EntryTier.STATIC:
                return 0
            case EntryTier.DRY:
                return 1
            case EntryTier.OFFLINE:
                return 2
            case EntryTier.INFERENCE:
                return 3


class EntryGranularity(StrEnum):
    """Whether an entry is minimal or realistically multi-feature."""

    FOCUSED = "focused"
    COMPOSITE = "composite"


class CorpusEntryManifest(BaseModel):
    """One parsed ``entry.toml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=ENTRY_NAME_PATTERN)
    description: str = Field(min_length=1)
    validity: EntryValidity
    tier: EntryTier
    granularity: EntryGranularity
    covers: list[str] = Field(min_length=1)
    expected_error: str | None = None

    @model_validator(mode="after")
    def validate_covers_has_no_duplicates(self) -> Self:
        duplicates = sorted({tag for tag in self.covers if self.covers.count(tag) > 1})
        if duplicates:
            msg = f"Entry '{self.name}' repeats tags in `covers`: {', '.join(duplicates)}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_expected_error_matches_validity(self) -> Self:
        # `expected_error` is what makes an invalid entry surgical: it names the one error the
        # bundle must produce, so the gate is red both when it fails differently and when it
        # accidentally validates. A valid entry carrying one would be claiming both.
        match self.validity:
            case EntryValidity.INVALID:
                if not self.expected_error:
                    msg = f"Entry '{self.name}' is invalid, so it must declare the `expected_error` it produces"
                    raise ValueError(msg)
            case EntryValidity.VALID:
                if self.expected_error is not None:
                    msg = f"Entry '{self.name}' is valid, so it must not declare an `expected_error`"
                    raise ValueError(msg)
        return self
