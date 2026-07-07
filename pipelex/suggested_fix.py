"""Suggested-fix wire models — structured, deterministic fixes attached to validation diagnostics.

Each fixable ``ValidationErrorItem`` carries a ``SuggestedFix``: semantic patch ops addressed
by TOML path, translated by the fix planner from enriched typed errors (never from message
strings). The ops are the machine contract; any rendered diff is presentation.

This module is deliberately low-level (stdlib + pydantic only) so that
``pipelex.base_exceptions`` — where ``ValidationErrorItem`` lives — can import it without
creating an import cycle. Naming is brand-neutral: fixes are a language-level concept.
"""

from enum import StrEnum
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

# A TOML-representable scalar value for a set_key op. Wave-1 fixes only ever write scalars
# (output refs, input refs); container values would come with rules that need them.
TomlScalar: TypeAlias = str | int | float | bool


class FixOpKind(StrEnum):
    """The semantic patch operations a suggested fix is composed of."""

    SET_KEY = "set_key"
    DELETE_KEY = "delete_key"
    DELETE_TABLE = "delete_table"
    RENAME_TABLE_KEY = "rename_table_key"


class FixSafety(StrEnum):
    """Whether a fix is safe to auto-apply (SAFE) or requires explicit opt-in (UNSAFE)."""

    SAFE = "safe"
    UNSAFE = "unsafe"

    @property
    def is_safe(self) -> bool:
        match self:
            case FixSafety.SAFE:
                return True
            case FixSafety.UNSAFE:
                return False


class FixOp(BaseModel):
    """One semantic patch op addressed by TOML path.

    ``table_path`` addresses the containing table (e.g. ``["pipe", "my_seq"]``), aligned with
    the ``field_path`` conventions of validation errors. ``key`` / ``value`` are used by
    ``set_key`` / ``delete_key``; ``new_key`` only by ``rename_table_key``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FixOpKind = Field(strict=False)
    table_path: list[str]
    key: str | None = None
    value: TomlScalar | None = None
    new_key: str | None = None


class SuggestedFix(BaseModel):
    """A deterministic fix for one validation error, ready for a style-preserving applier.

    ``fix_code`` is the kebab-case rule id (e.g. ``"match-sequence-output"``). ``source`` is
    the file the ops target, when known (multi-file libraries) — an applier must only apply
    ops to the file they target.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fix_code: str
    description: str
    safety: FixSafety = Field(strict=False)
    source: str | None = None
    ops: list[FixOp]
