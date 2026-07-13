"""The two codegen axes (`kind` and `target`) and the emitted-file unit shared by every emitter.

Codegen has exactly two explicit axes (see `docs/specs/pipelex-codegen.md` → "Two axes"): `kind` is
*what* to project (`types`, over the crate's concept set), `target` is *for whom* (a language / idiom
flavor). An emitter returns one or more `EmittedFile`s — a filename relative to the output root plus
its content — so a single projection can span more than one file (the ts-zod purity split: a pure
types file plus a thin binder file). The `kind`/`target` pair is what a generated file's stamp records
as its projection.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CodegenKind(StrEnum):
    """A codegen projection `kind` — the *what* axis, as recorded in a generated file's stamp.

    This is the **stamped-kind vocabulary**, deliberately narrower than the spec's `kind` axis: a kind
    is a member exactly when its artifacts ride the stamp/lock/offline-check trust chain. Input
    templates are the standing counter-example — they are user-editable scaffolds, not tracked
    generated code, so `pipelex codegen inputs` writes them unstamped and unlocked on purpose (see
    `pipelex/codegen/emission.py`). Nothing can ever stamp one, hence no `inputs` member. A future
    per-pipe kind (`docs`, `tools`, `tests`) joins this enum exactly when its artifacts are tracked.
    """

    TYPES = "types"


class CodegenTarget(StrEnum):
    """A codegen target flavor. All targets are Pipelex projections — the MTHDS standard specifies no
    type projection (see `docs/specs/pipelex-codegen.md` → "Ownership"). They differ in audience:
    `ts-zod` and `python-pydantic` emit idiom-neutral types any consumer can use; `python-structures`
    emits StructuredContent classes for a Pipelex runtime host.
    """

    PYTHON_STRUCTURES = "python-structures"
    PYTHON_PYDANTIC = "python-pydantic"
    TS_ZOD = "ts-zod"


class EmittedFile(BaseModel):
    """One generated file: a filename relative to the output root and its full content."""

    model_config = ConfigDict(frozen=True)

    filename: str
    content: str
