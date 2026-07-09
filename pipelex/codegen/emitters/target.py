"""The codegen `target` axis and the emitted-file unit shared by every emitter.

`target` is the *for-whom* axis of codegen (see `docs/specs/pipelex-codegen.md` → "Two axes"): a
language / idiom flavor. An emitter returns one or more `EmittedFile`s — a filename relative to the
output root plus its content — so a single projection can span more than one file (the ts-zod purity
split: a pure types file now, a thin binder file later).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CodegenTarget(StrEnum):
    """A codegen target flavor. `python-structures` is a Pipelex-runtime extension (StructuredContent
    classes); `python-pydantic` and `ts-zod` are protocol-capability type projections (neutral shapes).
    """

    PYTHON_STRUCTURES = "python-structures"
    PYTHON_PYDANTIC = "python-pydantic"
    TS_ZOD = "ts-zod"


class EmittedFile(BaseModel):
    """One generated file: a filename relative to the output root and its full content."""

    model_config = ConfigDict(frozen=True)

    filename: str
    content: str
