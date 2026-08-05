"""`codegen types` must project a bundle whose PipeFunc implementation does not exist yet.

The bootstrap deadlock this closes: writing a `@pipe_func` requires the generated `structures.py`
(the validator enforces `return type == the output concept's structure class`), and generating
`structures.py` used to require that function already registered — so a new PipeFunc method could not
be started without hand-writing a throwaway stub.

`load_crate_for_concept_projection` breaks it by not instantiating the closure's pipes at all. Every
test here runs against ONE fixture pair — byte-identical `.mthds`, implementation present vs absent —
so the before/after is a controlled comparison, and the load-bearing assertion is that the projection
is IDENTICAL across the pair. If those ever diverge, the projection is not concept-only and the
weaker loader contract is unsafe.

The other half is the no-regression pins: `load_normalized_crate` must still reject the same bundle,
or the weaker contract has leaked into the one `resolve` / `codegen inputs` / `run` depend on.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from pipelex.cli.commands.crate_loading import load_crate_for_concept_projection, load_normalized_crate
from pipelex.codegen.emitters.target import CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.interpreter_hub import get_library, get_library_manager
from pipelex.libraries.exceptions import LibraryError
from pipelex.system.registries.func_registry import func_registry

# A bundle whose only pipe is a PipeFunc. Its concept carries a real structure, so the projection has
# something to emit and the comparison across the fixture pair is meaningful.
FUNC_BUNDLE_MTHDS = """\
domain = "bootstrap"
description = "A method being bootstrapped around a custom function"

[concept.Quote]
description = "A priced quote"
structure.total = { description = "the total price", type = "number" }
structure.currency = { description = "the currency", type = "text" }

[pipe.price_it]
type = "PipeFunc"
description = "Price the quote with customer code"
inputs = {}
output = "Quote"
function_name = "price_the_quote"
"""

# The implementation, as it exists only AFTER structures.py has been generated: it imports the
# generated module. That import is exactly why the file cannot be present during bootstrap.
IMPLEMENTATION_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.system.registries.func_registry import pipe_func


class Quote(StructuredContent):
    total: float
    currency: str


@pipe_func(name="price_the_quote")
async def price_the_quote(working_memory: WorkingMemory) -> Quote:
    return Quote(total=1.0, currency="EUR")
"""

# A half-written implementation: present on disk but unimportable, because it imports the
# structures.py this very projection exists to generate. The realistic bootstrap state.
UNIMPORTABLE_PY = """\
from structures import Quote  # noqa: F401  # does not exist yet — this is the bootstrap state

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.system.registries.func_registry import pipe_func


@pipe_func(name="price_the_quote")
async def price_the_quote(working_memory: WorkingMemory) -> Quote:
    return Quote(total=1.0, currency="EUR")
"""


def _make_bundle_dir(root: Path, *, implementation: str | None) -> Path:
    """One arm of the fixture pair: identical .mthds, implementation present / absent / unimportable."""
    bundle_dir = root
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "method.mthds").write_text(FUNC_BUNDLE_MTHDS, encoding="utf-8")
    if implementation is not None:
        (bundle_dir / "price_quote.py").write_text(implementation, encoding="utf-8")
    return bundle_dir


@pytest.fixture
def teardown_libraries() -> Generator[None, None, None]:
    """Each load here opens a fresh library and leaves it current; tear them all down afterwards."""
    yield
    get_library_manager().teardown()


@pytest.mark.usefixtures("teardown_libraries")
class TestConceptProjectionWithoutPipeFunc:
    def test_projection_is_identical_with_and_without_the_implementation(self) -> None:
        """THE load-bearing test: the presence of the customer's Python cannot change the projection.

        If the concept projection is genuinely concept-only, both arms of the pair emit the same
        bytes AND the same crate fingerprint. A divergence here means the projection reads something
        outside the crate's concept set, and the weaker loader contract would be unsound.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            present = _make_bundle_dir(Path(tmp_dir) / "impl_present", implementation=IMPLEMENTATION_PY)
            missing = _make_bundle_dir(Path(tmp_dir) / "impl_missing", implementation=None)

            crate_present = load_crate_for_concept_projection(library_dirs=[present])
            crate_missing = load_crate_for_concept_projection(library_dirs=[missing])

            assert crate_present.fingerprint == crate_missing.fingerprint
            emitted_present = emit_types(crate_present, target=CodegenTarget.PYTHON_STRUCTURES)
            emitted_missing = emit_types(crate_missing, target=CodegenTarget.PYTHON_STRUCTURES)
            assert [(f.filename, f.content) for f in emitted_present] == [(f.filename, f.content) for f in emitted_missing]
            # And it is a real projection, not two empty ones agreeing with each other.
            assert "class Quote" in emitted_missing[0].content

    def test_projection_loads_with_the_implementation_absent(self) -> None:
        """The deadlock itself: no implementation on disk, yet the concept set still projects."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _make_bundle_dir(Path(tmp_dir), implementation=None)

            crate = load_crate_for_concept_projection(library_dirs=[bundle_dir])

            assert "bootstrap.Quote" in crate.concepts
            # The pipe blueprint still rides the crate — the crate is derived from blueprints, and a
            # projection that silently dropped pipes would change the fingerprint and break the lock.
            assert "bootstrap.price_it" in crate.pipes

    def test_projection_loads_with_an_unimportable_implementation(self) -> None:
        """The real bootstrap state: the .py exists but imports the structures.py being generated.

        Stronger than the absent-file case — it proves the loader does not merely tolerate a missing
        registration, it never imports the customer module at all.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _make_bundle_dir(Path(tmp_dir), implementation=UNIMPORTABLE_PY)

            crate = load_crate_for_concept_projection(library_dirs=[bundle_dir])

            assert "bootstrap.Quote" in crate.concepts
            # Never imported, so it never registered — the direct assertion that the load skipped it,
            # rather than the weaker "it did not raise" (which a successful import would also satisfy).
            assert func_registry.get_function("price_the_quote") is None

    def test_no_live_pipe_is_built_by_the_projection_load(self) -> None:
        """The mechanism, pinned: the projection leaves the library's pipe library empty.

        Without this, a future change could make the projection pass by relaxing PipeFunc validation
        instead of by not building pipes — the same symptom, a much wider blast radius.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _make_bundle_dir(Path(tmp_dir), implementation=None)

            load_crate_for_concept_projection(library_dirs=[bundle_dir])

            library = get_library()
            assert library.pipe_library.root == {}
            # Concepts, by contrast, ARE loaded: the projection's input is not silently empty.
            assert any(ref.startswith("bootstrap.") for ref in library.concept_library.root)

    def test_normalized_crate_still_rejects_the_missing_implementation(self) -> None:
        """NO-REGRESSION PIN. `load_normalized_crate` is what `resolve`, `codegen inputs` and `run`
        call, and it documents "Load, validate, and normalize". The weaker contract must not leak
        into it: the same bundle that projects fine above must still be a negative verdict here.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _make_bundle_dir(Path(tmp_dir), implementation=None)

            with pytest.raises(LibraryError, match="price_the_quote"):
                load_normalized_crate(library_dirs=[bundle_dir])

    def test_normalized_crate_still_rejects_an_unimportable_implementation(self) -> None:
        """NO-REGRESSION PIN, unimportable arm: a broken .py is still a negative verdict for resolve."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = _make_bundle_dir(Path(tmp_dir), implementation=UNIMPORTABLE_PY)

            with pytest.raises(LibraryError, match="price_the_quote"):
                load_normalized_crate(library_dirs=[bundle_dir])
