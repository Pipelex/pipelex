"""Regression test for cross-package refines in structures_cmd.

Ensures that when a concept refines a cross-package reference like
``alias->other_domain.OtherConcept``, the generated structure file uses a
valid Python identifier as its base class. Previously, ``QualifiedRef.parse``
left the ``alias->`` prefix in ``domain_path``, which the
``make_qualified_structure_class_name`` helper does not sanitise — the
generated module then failed to import because the base class name was not a
legal identifier.
"""

import re
import sys
import tempfile
from pathlib import Path
from types import ModuleType

from pipelex.cli.commands.build.structures_cmd import generate_structures_from_blueprints
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.hub import get_class_registry

_FAKE_BASE_MODULE_PATH = "tests_pr898_other_pkg_stub.structures.other_domain__other_concept"


class TestStructuresCmdCrossPackageRefines:
    @classmethod
    def _register_cross_package_stub(cls) -> type:
        """Register a stub mimicking what another package's `pipelex build structures` would have
        produced: a class whose `__name__` equals the registry key and that lives at a stable
        importable module path, so the generator can recover the import path via `__module__`.
        """
        stub_module = ModuleType(_FAKE_BASE_MODULE_PATH)
        stub_class: type = type("other_domain__OtherConcept", (StructuredContent,), {"__module__": _FAKE_BASE_MODULE_PATH})
        stub_module.other_domain__OtherConcept = stub_class  # type: ignore[attr-defined]
        sys.modules[_FAKE_BASE_MODULE_PATH] = stub_module
        get_class_registry().register_class(
            stub_class,
            name="other_domain__OtherConcept",
            should_warn_if_already_registered=False,
        )
        return stub_class

    def test_cross_package_refine_produces_valid_identifier(self):
        """A cross-package refine must produce a clean qualified base class name.

        The generated code must contain the domain-qualified class name
        (e.g. ``other_domain__OtherConcept``) and must NOT leak the
        cross-package alias separator ``->`` into the Python source. The
        generated file must also import the base class so it is loadable
        outside the generator's validation harness.
        """
        self._register_cross_package_stub()

        bundle = PipelexBundleBlueprint(
            domain="local_domain",
            description="Bundle that refines a cross-package concept.",
            concept={
                "RefiningConcept": ConceptBlueprint(
                    description="Refines a concept defined in another package.",
                    refines="some_alias->other_domain.OtherConcept",
                ),
            },
        )

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_directory = Path(temp_dir)

                generated_files = generate_structures_from_blueprints(
                    blueprints=[bundle],
                    output_directory=output_directory,
                    skip_existing_check=True,
                    quiet=True,
                )

                assert generated_files == [("local_domain", "RefiningConcept")]

                generated_file = output_directory / "local_domain__refining_concept.py"
                assert generated_file.exists(), f"Generated file not found: {generated_file}"

                generated_code = generated_file.read_text()

                assert "->" not in generated_code, (
                    "Generated code leaked the cross-package alias separator '->' (produces an invalid Python identifier):\n" + generated_code
                )
                assert "some_alias" not in generated_code, (
                    "Generated code leaked the cross-package alias name into the class definition:\n" + generated_code
                )
                assert "class local_domain__RefiningConcept(other_domain__OtherConcept):" in generated_code, (
                    "Expected generated class to inherit from the qualified cross-package base class. Got:\n" + generated_code
                )
                import_pattern = re.compile(r"^from\s+\S+\s+import\s+other_domain__OtherConcept(\s|$)", re.MULTILINE)
                assert import_pattern.search(generated_code), (
                    "Generated code is missing an import for the cross-package base class "
                    "`other_domain__OtherConcept`. Without it, importing the generated module fails with "
                    "`NameError: name 'other_domain__OtherConcept' is not defined`. Got:\n" + generated_code
                )
        finally:
            sys.modules.pop(_FAKE_BASE_MODULE_PATH, None)
