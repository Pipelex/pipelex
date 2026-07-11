"""The `codegen types` projection: a crate's concept set -> typed artifacts, selected by target.

`emit_types` is the single entry point the CLI (and route) call. It resolves the crate once into the
neutral `ResolvedLibrary` and dispatches to the target's emitter. The result is one or more
`EmittedFile`s; the caller decides where they land on disk.
"""

from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.emitters.target import CodegenTarget, EmittedFile
from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.libraries.library_crate import LibraryCrate


def emit_types(crate: LibraryCrate, *, target: CodegenTarget) -> list[EmittedFile]:
    """Project the concept set of a normalized `crate` into typed artifacts for `target`."""
    library = resolve_concepts_from_crate(crate)
    match target:
        case CodegenTarget.PYTHON_STRUCTURES:
            return emit_python_structures(library)
        case CodegenTarget.PYTHON_PYDANTIC:
            return emit_python_pydantic(library)
        case CodegenTarget.TS_ZOD:
            return emit_ts_zod(library)
