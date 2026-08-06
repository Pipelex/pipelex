"""A PipeFunc may return the structure class that `codegen types` emits for its output concept.

Two naming rules describe the same concept, and they legitimately differ:

- The runtime names the class it generates for an inline-structure concept domain-qualified —
  `make_qualified_structure_class_name` -> `bootstrap__Quote`.
- `codegen types --target python-structures` names the class it emits **bare** when the code is
  unique across the crate, and falls back to the *same* qualified spelling when it collides
  (`codegen/emitters/naming.py::python_class_name`).

So `validate_output_with_library` must accept both spellings. If it only accepted the qualified one,
`pipelex build structures` would emit classes that its own PipeFunc could never legally return —
which is exactly the wall you hit right after the generated `structures.py` finally exists.

The collision arm needs no test of its own here: codegen emits `make_qualified_structure_class_name`
verbatim in that case, which is the spelling the validator already accepted.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from pipelex.cli.commands.crate_loading import load_normalized_crate
from pipelex.interpreter_hub import get_library_manager

SCALAR_MTHDS = """\
domain = "bootstrap"
description = "A method whose PipeFunc returns a generated structure class"

[concept.Quote]
description = "A priced quote"
structure.total = { description = "the total price", type = "number" }

[pipe.price_it]
type = "PipeFunc"
description = "Price the quote"
inputs = {}
output = "Quote"
function_name = "price_the_quote"
"""

LIST_MTHDS = """\
domain = "bootstrap"
description = "A method whose PipeFunc returns a list of generated structure classes"

[concept.Quote]
description = "A priced quote"
structure.total = { description = "the total price", type = "number" }

[pipe.price_them]
type = "PipeFunc"
description = "Price several quotes"
inputs = {}
output = "Quote[]"
function_name = "price_the_quotes"
"""

# `class Quote` — spelled exactly as `codegen types --target python-structures` emits it for the
# concept `bootstrap.Quote`, i.e. the bare code, since it is unique in this crate.
GENERATED_STYLE_SCALAR_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.registries.func_registry import pipe_func


class Quote(StructuredContent):
    total: float


@pipe_func(name="price_the_quote")
async def price_the_quote(working_memory: WorkingMemory) -> Quote:
    return Quote(total=1.0)
"""

GENERATED_STYLE_LIST_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.registries.func_registry import pipe_func


class Quote(StructuredContent):
    total: float


@pipe_func(name="price_the_quotes")
async def price_the_quotes(working_memory: WorkingMemory) -> ListContent[Quote]:
    return ListContent(items=[Quote(total=1.0)])
"""

# PipeFunc names live in one flat, process-wide namespace, so the rejection case registers under its
# own name rather than colliding with the accepting cases above.
WRONG_NAME_MTHDS = SCALAR_MTHDS.replace("price_the_quote", "price_the_quote_wrongly")

# An unrelated class name: neither the qualified spelling nor the concept's code. Still rejected —
# widening the accepted set must not turn the check into "any class at all".
WRONG_NAME_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.registries.func_registry import pipe_func


class SomethingElse(StructuredContent):
    total: float


@pipe_func(name="price_the_quote_wrongly")
async def price_the_quote_wrongly(working_memory: WorkingMemory) -> SomethingElse:
    return SomethingElse(total=1.0)
"""


def _write_bundle(root: Path, *, mthds: str, implementation: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "method.mthds").write_text(mthds, encoding="utf-8")
    (root / "impl.py").write_text(implementation, encoding="utf-8")
    return root


@pytest.fixture
def teardown_libraries() -> Generator[None, None, None]:
    yield
    get_library_manager().teardown()


@pytest.mark.usefixtures("teardown_libraries")
class TestPipeFuncAcceptsGeneratedStructureClass:
    def test_scalar_output_accepts_the_bare_generated_class_name(self) -> None:
        """`-> Quote` validates against concept `bootstrap.Quote`, whose runtime class is `bootstrap__Quote`."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _write_bundle(Path(tmp_dir) / "scalar", mthds=SCALAR_MTHDS, implementation=GENERATED_STYLE_SCALAR_PY)

            crate = load_normalized_crate(library_dirs=[bundle_dir])

            assert "bootstrap.price_it" in crate.pipes

    def test_list_output_accepts_the_bare_generated_class_name(self) -> None:
        """Same for the multiplicity arm: `-> ListContent[Quote]` against `output = "Quote[]"`."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _write_bundle(Path(tmp_dir) / "list", mthds=LIST_MTHDS, implementation=GENERATED_STYLE_LIST_PY)

            crate = load_normalized_crate(library_dirs=[bundle_dir])

            assert "bootstrap.price_them" in crate.pipes

    def test_an_unrelated_class_name_is_still_rejected(self) -> None:
        """The accepted set is the two names for THIS concept, not 'any class'."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _write_bundle(Path(tmp_dir) / "wrong", mthds=WRONG_NAME_MTHDS, implementation=WRONG_NAME_PY)

            # Surfaces as the raw TypeError from validate_output_with_library — the library-level
            # loader does not wrap it, so the pin is on the type the user actually sees.
            with pytest.raises(TypeError, match="SomethingElse"):
                load_normalized_crate(library_dirs=[bundle_dir])
