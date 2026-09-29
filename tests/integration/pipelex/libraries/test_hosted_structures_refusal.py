"""A sandbox-hosted library load imports no customer Python, and refuses one that declares structure classes.

Importing a file runs its module-level code, so on a sandbox-hosted deployment the loader captures every
`.py` as source for the sandbox and imports none of it. A `StructuredContent` subclass would have to be
imported into the runner's own process to back a concept, so a load whose sources declare one is refused
with `MethodStructuresRefusedError`, the error a fetched package already gets. Each structure file here
carries a module-level sentinel that writes a marker file, so a test can tell whether the file executed.
"""

import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.codegen.emission import write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.codegen.stamp import apply_stamp
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.interpreter_hub import get_concept_library, get_library_manager, scoped_current_library
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.methods.exceptions import MethodStructuresRefusedError

SENTINEL_LINE = 'open(r"{marker}", "w").write("ran")\n'

STRUCTURE_FILE_PY = """\
from pipelex.core.stuffs.structured_content import StructuredContent


class {class_name}(StructuredContent):
    total: float


"""

ALIASED_STRUCTURE_FILE_PY = """\
from pipelex.core.stuffs.structured_content import StructuredContent as SC


class {class_name}(SC):
    total: float


"""

ATTRIBUTE_STRUCTURE_FILE_PY = """\
import pipelex.core.stuffs.structured_content as sc_module


class {class_name}(sc_module.StructuredContent):
    total: float


"""

PIPE_FUNC_WITH_OWN_CLASS_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.registries.func_registry import pipe_func


class {class_name}(StructuredContent):
    total: float


@pipe_func(name="make_hosted_refusal_total")
async def make_hosted_refusal_total(working_memory: WorkingMemory) -> {class_name}:
    return {class_name}(total=1.0)


"""

DYNAMIC_STRUCTURE_FILE_PY = """\
from pipelex.core.stuffs.structured_content import StructuredContent

{class_name} = type("{class_name}", (StructuredContent,), {{"__annotations__": {{"total": float}}}})


"""

INLINE_STRUCTURE_MTHDS = """\
domain = "hosted_generated"
description = "A concept with an inline structure"

[concept.Receipt]
description = "A receipt"

[concept.Receipt.structure]
total = { type = "number", description = "The total", required = true }
"""

CLASS_BACKED_MTHDS = """\
domain = "hosted_refusal"
description = "A concept backed by a Python class"

[concept.Invoice]
description = "An invoice"
structure = "{class_name}"
"""


def _write_structure_file(*, path: Path, template: str, class_name: str, marker: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.format(class_name=class_name) + SENTINEL_LINE.format(marker=marker), encoding="utf-8")


def _is_imported(*, path: Path) -> bool:
    """Whether any module in this process was loaded from *path*."""
    resolved = path.resolve()
    for module in list(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return True
    return False


class TestHostedStructuresRefusal:
    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_structure_file_is_refused_and_never_executed(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        library_dir = tmp_path / "bundle"
        structure_file = library_dir / "structures" / "invoice.py"
        marker = tmp_path / "sentinel.ran"
        _write_structure_file(path=structure_file, template=STRUCTURE_FILE_PY, class_name="HostedRefusalInvoice", marker=marker)

        library_id = load_empty_library()
        with pytest.raises(MethodStructuresRefusedError) as exc_info:
            get_library_manager().load_libraries(library_id=library_id, library_dirs=[library_dir])

        message = str(exc_info.value)
        assert "structures/invoice.py defines HostedRefusalInvoice" in message
        assert "not in-process Python" in message
        assert "from structures import <domain>__<Concept>" in message
        assert not marker.exists(), "the structure file's module-level code ran in the loading process"
        assert not _is_imported(path=structure_file)
        # Refused before anything was kept: no crate carries the source.
        assert get_library_manager().get_crate(library_id=library_id) is None

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    @pytest.mark.parametrize(
        ("template", "class_name"),
        [
            (ALIASED_STRUCTURE_FILE_PY, "HostedRefusalAliasedInvoice"),
            (ATTRIBUTE_STRUCTURE_FILE_PY, "HostedRefusalAttributeInvoice"),
            (PIPE_FUNC_WITH_OWN_CLASS_PY, "HostedRefusalPipeFuncTotal"),
        ],
        ids=["aliased-import", "attribute-base", "pipe-func-declaring-its-class"],
    )
    def test_every_declared_form_is_refused(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
        template: str,
        class_name: str,
    ):
        library_dir = tmp_path / "bundle"
        py_file = library_dir / "customer.py"
        marker = tmp_path / "sentinel.ran"
        _write_structure_file(path=py_file, template=template, class_name=class_name, marker=marker)

        library_id = load_empty_library()
        with pytest.raises(MethodStructuresRefusedError, match=re.escape(f"customer.py defines {class_name}")):
            get_library_manager().load_libraries(library_id=library_id, library_dirs=[library_dir])

        assert not marker.exists()
        assert not _is_imported(path=py_file)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_dynamic_class_escapes_the_scan_but_never_executes(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """A class built by `type(...)` escapes the static scan, so the load is not refused. It is not imported either:
        the file travels as source, its module-level code never runs here, and a concept naming the class finds none.
        """
        class_name = "HostedRefusalDynamicInvoice"
        library_dir = tmp_path / "bundle"
        py_file = library_dir / "structures" / "invoice.py"
        marker = tmp_path / "sentinel.ran"
        _write_structure_file(path=py_file, template=DYNAMIC_STRUCTURE_FILE_PY, class_name=class_name, marker=marker)
        (library_dir / "invoice.mthds").write_text(CLASS_BACKED_MTHDS.format(class_name=class_name), encoding="utf-8")

        library_id = load_empty_library()
        with pytest.raises(ConceptFactoryError, match=f"Structure class '{class_name}'.*not a registered subclass of StuffContent"):
            get_library_manager().load_libraries(library_id=library_id, library_dirs=[library_dir])

        assert not marker.exists(), "the dynamically built class's module-level code ran in the loading process"
        assert not _is_imported(path=py_file)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_structure_file_under_an_excluded_dir_is_not_refused(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """A file under an excluded directory is neither shipped nor imported, so it is not refused."""
        library_dir = tmp_path / "bundle"
        py_file = library_dir / ".venv" / "lib" / "invoice.py"
        marker = tmp_path / "sentinel.ran"
        _write_structure_file(path=py_file, template=STRUCTURE_FILE_PY, class_name="HostedRefusalVenvInvoice", marker=marker)

        library_id = load_empty_library()
        get_library_manager().load_libraries(library_id=library_id, library_dirs=[library_dir])

        assert not marker.exists()
        assert not _is_imported(path=py_file)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_one_refusal_lists_every_directory(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        marker = tmp_path / "sentinel.ran"
        _write_structure_file(path=dir_a / "structures" / "invoice.py", template=STRUCTURE_FILE_PY, class_name="HostedRefusalA", marker=marker)
        _write_structure_file(path=dir_b / "models" / "receipt.py", template=STRUCTURE_FILE_PY, class_name="HostedRefusalB", marker=marker)

        library_id = load_empty_library()
        with pytest.raises(MethodStructuresRefusedError) as exc_info:
            get_library_manager().load_libraries(library_id=library_id, library_dirs=[dir_a, dir_b])

        message = str(exc_info.value)
        assert "structures/invoice.py defines HostedRefusalA" in message
        assert "models/receipt.py defines HostedRefusalB" in message
        assert not marker.exists()

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_refusal_names_relative_paths_only(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """On a host the library directory is a temporary one, which is not the caller's to read."""
        library_dir = tmp_path / "bundle"
        marker = tmp_path / "sentinel.ran"
        _write_structure_file(
            path=library_dir / "structures" / "invoice.py", template=STRUCTURE_FILE_PY, class_name="HostedRefusalPathInvoice", marker=marker
        )

        library_id = load_empty_library()
        with pytest.raises(MethodStructuresRefusedError) as exc_info:
            get_library_manager().load_libraries(library_id=library_id, library_dirs=[library_dir])

        message = str(exc_info.value)
        assert str(tmp_path) not in message
        assert str(tmp_path.resolve()) not in message
        assert tmp_path.name not in message

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_generated_structures_module_is_accepted_and_never_executed(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """The module `pipelex build structures` writes into a bundle copies the method's own MTHDS concepts, so a
        hosted load accepts it as generated: it travels to the sandbox as source and is never imported here.
        """
        library_dir = tmp_path / "bundle"
        library_dir.mkdir()
        (library_dir / "receipt.mthds").write_text(INLINE_STRUCTURE_MTHDS, encoding="utf-8")
        library_manager = get_library_manager()
        generation_library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=generation_library_id):
                library_manager.load_libraries(library_id=generation_library_id, library_dirs=[library_dir])
                crate = library_manager.get_crate(library_id=generation_library_id)
                assert crate is not None
                normalized = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
                write_stamped_projection(
                    emit_types(normalized, target=CodegenTarget.PYTHON_STRUCTURES),
                    output_dir=library_dir / "structures",
                    crate_fingerprint=normalized.fingerprint,
                    engine_version="0.0.0-test",
                    kind=CodegenKind.TYPES,
                    target=CodegenTarget.PYTHON_STRUCTURES,
                )
        finally:
            library_manager.teardown(library_id=generation_library_id)
        generated_file = library_dir / "structures" / "structures.py"
        generated_source = generated_file.read_text(encoding="utf-8")
        assert "(StructuredContent)" in generated_source

        library_id = load_empty_library()
        library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])

        hosted_crate = library_manager.get_crate(library_id=library_id)
        assert hosted_crate is not None
        assert hosted_crate.python_sources.get("structures/structures.py") == generated_source
        assert not _is_imported(path=generated_file)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_edited_generated_structures_module_is_refused(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """A generated module edited below its stamp may carry a hand-written class, so it is refused like one."""
        library_dir = tmp_path / "bundle"
        (library_dir / "structures").mkdir(parents=True)
        body = STRUCTURE_FILE_PY.format(class_name="HostedRefusalEditedInvoice")
        stamped = apply_stamp(
            body,
            crate_fingerprint="0" * 64,
            engine_version="0.0.0-test",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_STRUCTURES,
            pipe_ref=None,
            options={},
            comment_prefix="#",
        )
        (library_dir / "structures" / "structures.py").write_text(stamped + "    extra: str = ''\n", encoding="utf-8")

        library_id = load_empty_library()
        with pytest.raises(MethodStructuresRefusedError, match=re.escape("structures/structures.py defines HostedRefusalEditedInvoice")):
            get_library_manager().load_libraries(library_id=library_id, library_dirs=[library_dir])

    def test_direct_mode_imports_the_structure_class(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        """Structure classes stay an open-source and self-hosted feature: a direct-mode load imports the file and
        the concept resolves to its class.
        """
        class_name = "HostedRefusalDirectModeInvoice"
        library_dir = tmp_path / "bundle"
        (library_dir / "structures").mkdir(parents=True)
        (library_dir / "structures" / "invoice.py").write_text(STRUCTURE_FILE_PY.format(class_name=class_name), encoding="utf-8")
        (library_dir / "invoice.mthds").write_text(CLASS_BACKED_MTHDS.format(class_name=class_name), encoding="utf-8")

        library_id = load_empty_library()
        get_library_manager().load_libraries(library_id=library_id, library_dirs=[library_dir])

        concept_library = get_concept_library()
        invoice_class = concept_library.get_structure_class(concept=concept_library.get_required_concept("hosted_refusal.Invoice"))
        assert invoice_class.__name__ == class_name
        assert _is_imported(path=library_dir / "structures" / "invoice.py")
