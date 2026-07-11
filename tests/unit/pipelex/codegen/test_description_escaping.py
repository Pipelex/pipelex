from collections.abc import Callable
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
    def test_python_descriptions_cannot_escape_docstrings(
        self,
        emitter: Callable[[ResolvedLibrary], list[EmittedFile]],
        module_name: str,
        tmp_path: Path,
    ):
        description = DescriptionEscapingCases.MALICIOUS_DESCRIPTION
        library = resolve_concepts_from_crate(self._make_crate(description=description))

        content = emitter(library)[0].content
        module = load_generated_module(content, tmp_path=tmp_path, name=module_name)

        assert module.Payload.__doc__ == description
        assert not hasattr(module.Payload, "injected")
        assert module.Payload.model_fields["value"].description == description

    def test_typescript_descriptions_cannot_escape_jsdoc(self):
        description = DescriptionEscapingCases.MALICIOUS_DESCRIPTION
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
                "security.Payload": ConceptBlueprint(
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
