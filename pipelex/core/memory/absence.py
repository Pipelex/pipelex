from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AbsenceKind(StrEnum):
    """How a slot came to hold no value.

    - DECLARED_ABSENT: a producer with an optional (`?`) output declared it produced nothing
      (e.g. a PipeCondition `continue` outcome, or — phase 2 — an LLM maybe-wrapper), or a binding
      step's path reached a field holding nothing.
    - SKIPPED: the producing pipe was lifted (skipped) because one of its plain inputs was absent,
      or a binding step was, because its root was.
    - NOT_PROVIDED: the caller omitted an optional method input from the pipeline inputs.
    """

    DECLARED_ABSENT = "declared_absent"
    SKIPPED = "skipped"
    NOT_PROVIDED = "not_provided"

    @property
    def is_skipped(self) -> bool:
        match self:
            case AbsenceKind.SKIPPED:
                return True
            case AbsenceKind.DECLARED_ABSENT | AbsenceKind.NOT_PROVIDED:
                return False


class AbsenceRecord(BaseModel):
    """A recorded fact that a named slot holds no value, with provenance (D2).

    Absence stays what it mechanically is — no Stuff under the name — but becomes a recorded
    fact: who produced it, why, and which upstream absence it chains to. Provenance is captured
    at the moment absence is produced, not reconstructed at failure time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    variable_name: str
    kind: AbsenceKind = Field(strict=False)
    reason: str
    producing_pipe: str | None = None
    upstream: AbsenceRecord | None = None

    def provenance_chain(self) -> list[AbsenceRecord]:
        """This record followed by its upstream chain, ending at the origin absence."""
        chain: list[AbsenceRecord] = []
        node: AbsenceRecord | None = self
        while node is not None:
            chain.append(node)
            node = node.upstream
        return chain

    def origin(self) -> AbsenceRecord:
        """The first absence in the chain — where absence entered the flow."""
        return self.provenance_chain()[-1]
