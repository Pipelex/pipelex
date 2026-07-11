"""The two codegen axes (`kind` and `target`) and the emitted-file unit shared by every emitter.

Codegen has exactly two explicit axes (see `docs/specs/pipelex-codegen.md` → "Two axes"): `kind` is
*what* to project (`types` over the concept set, `inputs` per pipe, …), `target` is *for whom* (a
language / idiom flavor). An emitter returns one or more `EmittedFile`s — a filename relative to the
output root plus its content — so a single projection can span more than one file (the ts-zod purity
split: a pure types file plus a thin binder file). The `kind`/`target` pair is what a generated file's
stamp records as its projection.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CodegenKind(StrEnum):
    """A codegen projection `kind` — the *what* axis. Only the kinds that emit tracked artifacts today
    are listed: `types` (over the concept set) and `inputs` (per pipe). Recorded in a file's stamp.
    """

    TYPES = "types"
    INPUTS = "inputs"


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
