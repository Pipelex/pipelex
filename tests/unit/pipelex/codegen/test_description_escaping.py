from collections.abc import Callable
from inspect import getdoc
from pathlib import Path

import pytest

from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.emitters.target import EmittedFile
from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import ResolvedLibrary, resolve_concepts_from_crate
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.tools.misc.python_literals import normalized_docstring_text
from tests.unit.pipelex.codegen.conftest import load_generated_module
from tests.unit.pipelex.codegen.test_data import DescriptionEscapingCases


class TestDescriptionEscaping:
    @pytest.mark.parametrize(
        ("emitter", "module_name"),
        [
            pytest.param(emit_python_pydantic, "generated_pydantic", id="python-pydantic"),
            pytest.param(emit_python_structures, "generated_structures", id="python-structures"),
        ],
    )
    @pytest.mark.parametrize(
        "description",
        [
            pytest.param(DescriptionEscapingCases.TRIPLE_QUOTE_DESCRIPTION, id="verbatim-docstring"),
            pytest.param(DescriptionEscapingCases.ESCAPED_DOCSTRING_DESCRIPTION, id="escaped-docstring"),
        ],
    )
    def test_python_descriptions_cannot_escape_docstrings(
        self,
        emitter: Callable[[ResolvedLibrary], list[EmittedFile]],
        module_name: str,
        description: str,
        tmp_path: Path,
    ):
        library = resolve_concepts_from_crate(self._make_crate(description=description))

        content = emitter(library)[0].content
        module = load_generated_module(content, tmp_path=tmp_path, name=module_name)

        # The docstring is rendered the way a human writes one, so `__doc__` carries the class-body
        # indentation — the shape that survives `ruff format` and the pydocstyle rules, and therefore the
        # only shape that keeps the stamp valid. `inspect.getdoc` takes that indentation straight back
        # off, which is what `normalized_docstring_text` describes and what consumers actually read.
        assert getdoc(module.Described) == normalized_docstring_text(description)
        # A statement the description spelled would sit in the class body, which pydantic refuses or reads as a field: the
        # class loads, and its one field is the declared one.
        assert set(module.Described.model_fields) == {"value"}
        # The field description is a plain single-line literal, so it stays byte-identical — exact bytes
        # survive wherever they are consumed programmatically rather than read as documentation.
        assert module.Described.model_fields["value"].description == description

    def test_typescript_descriptions_cannot_escape_jsdoc(self):
        description = DescriptionEscapingCases.TRIPLE_QUOTE_DESCRIPTION
        library = resolve_concepts_from_crate(self._make_crate(description=description))

        content = emit_ts_zod(library)[0].content

        assert ' * Safe opening"""' in content
        assert " *     injected = True" in content
        assert ' *     """ignored * /' in content
        assert " * export const injected = true;" in content
        assert " * /**" in content
        assert " * backslash \\ path" in content
        assert " * Unicode café" in content
        assert "\nexport const injected = true;\n" not in content
        assert "\r" not in content

    @staticmethod
    def _make_crate(*, description: str) -> LibraryCrate:
        return LibraryCrate(
            mthds_version="1.0.0-test",
            concepts={
                "escaping.Described": ConceptBlueprint(
                    description=description,
                    structure={
                        "value": ConceptStructureBlueprint(
                            description=description,
                            type=ConceptStructureBlueprintFieldType.TEXT,
                            required=True,
                        )
                    },
                )
            },
        )
