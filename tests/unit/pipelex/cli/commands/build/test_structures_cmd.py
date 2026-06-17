"""Unit tests for the structure-codegen logic in build/structures_cmd.py.

Drives generate_structures_from_blueprints and its helpers directly with real
blueprints and a tmp output dir — the same pattern as the cross-package refines
regression test next door.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.cli.commands.build.structures_cmd import (
    _build_concept_ref_to_class_info,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _compute_relative_path_from_output_dir,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    generate_structures_from_blueprints,
)
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture


class TestStructuresCmd:
    def test_relative_path_inside_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An output dir under the cwd yields its relative path."""
        monkeypatch.chdir(tmp_path)
        output_directory = tmp_path / "generated" / "structures"
        output_directory.mkdir(parents=True)

        assert _compute_relative_path_from_output_dir(output_directory) == Path("generated/structures")

    def test_relative_path_outside_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An output dir outside the cwd yields None."""
        inside_dir = tmp_path / "inside"
        inside_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        monkeypatch.chdir(inside_dir)

        assert _compute_relative_path_from_output_dir(outside_dir) is None

    def test_relative_path_equal_to_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An output dir equal to the cwd yields the empty relative path."""
        monkeypatch.chdir(tmp_path)

        assert _compute_relative_path_from_output_dir(tmp_path) == Path()

    def test_concept_ref_mapping_skips_native_and_qualifies_names(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The concept_ref map skips the native domain, qualifies bare names and builds module paths."""
        monkeypatch.chdir(tmp_path)
        output_directory = tmp_path / "structures"
        output_directory.mkdir()
        blueprints = [
            PipelexBundleBlueprint(domain="native", description="native stub", concept={"NativeStub": "native stub concept"}),
            PipelexBundleBlueprint(
                domain="billing",
                description="billing concepts",
                concept={
                    "Invoice": ConceptBlueprint(description="An invoice", structure={"total": "the total"}),
                    "CustomName": ConceptBlueprint(description="Custom structure ref", structure="MyCustomClass"),
                },
            ),
        ]

        mapping = _build_concept_ref_to_class_info(blueprints, output_directory=output_directory)

        assert set(mapping.keys()) == {"billing.Invoice", "billing.CustomName"}
        assert mapping["billing.Invoice"].class_name == "billing__Invoice"
        assert mapping["billing.Invoice"].module_path == "structures.billing__invoice"
        assert mapping["billing.CustomName"].class_name == "MyCustomClass"
        assert mapping["billing.CustomName"].module_path == "structures.billing__my_custom_class"

    def test_concept_ref_mapping_without_relative_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the output dir is outside the cwd, module paths are None."""
        inside_dir = tmp_path / "inside"
        inside_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        monkeypatch.chdir(inside_dir)
        blueprints = [
            PipelexBundleBlueprint(
                domain="billing",
                description="billing concepts",
                concept={"Invoice": ConceptBlueprint(description="An invoice")},
            ),
        ]

        mapping = _build_concept_ref_to_class_info(blueprints, output_directory=outside_dir)

        assert mapping["billing.Invoice"].module_path is None

    def test_generate_string_concept_defaults_to_text_content(self, tmp_path: Path) -> None:
        """A bare string concept generates a TextContent subclass file."""
        blueprints = [
            PipelexBundleBlueprint(domain="notes", description="notes", concept={"QuickNote": "A short note"}),
        ]

        generated = generate_structures_from_blueprints(blueprints, output_directory=tmp_path, skip_existing_check=True, quiet=True)

        assert generated == [("notes", "QuickNote")]
        generated_code = (tmp_path / "notes__quick_note.py").read_text(encoding="utf-8")
        assert "class notes__QuickNote(TextContent):" in generated_code
        assert (tmp_path / "__init__.py").exists()

    def test_generate_explicit_structure(self, tmp_path: Path) -> None:
        """An explicit structure dict generates a structured class with its fields."""
        blueprints = [
            PipelexBundleBlueprint(
                domain="billing",
                description="billing",
                concept={
                    "Invoice": ConceptBlueprint(
                        description="An invoice",
                        structure={"total": "the invoice total", "customer_name": "the customer"},
                    ),
                },
            ),
        ]

        generated = generate_structures_from_blueprints(blueprints, output_directory=tmp_path, skip_existing_check=True, quiet=True)

        assert generated == [("billing", "Invoice")]
        generated_code = (tmp_path / "billing__invoice.py").read_text(encoding="utf-8")
        assert "class billing__Invoice" in generated_code
        assert "total" in generated_code
        assert "customer_name" in generated_code

    def test_generate_refines_native_concept(self, tmp_path: Path) -> None:
        """A concept refining a native concept inherits from its Content class."""
        blueprints = [
            PipelexBundleBlueprint(
                domain="notes",
                description="notes",
                concept={"FancyText": ConceptBlueprint(description="Fancy text", refines="Text")},
            ),
        ]

        generated = generate_structures_from_blueprints(blueprints, output_directory=tmp_path, skip_existing_check=True, quiet=True)

        assert generated == [("notes", "FancyText")]
        generated_code = (tmp_path / "notes__fancy_text.py").read_text(encoding="utf-8")
        assert "class notes__FancyText(TextContent):" in generated_code

    def test_generate_default_concept_blueprint(self, tmp_path: Path) -> None:
        """A blueprint with neither structure nor refines defaults to TextContent."""
        blueprints = [
            PipelexBundleBlueprint(
                domain="notes",
                description="notes",
                concept={"PlainThing": ConceptBlueprint(description="Just a thing")},
            ),
        ]

        generated = generate_structures_from_blueprints(blueprints, output_directory=tmp_path, skip_existing_check=True, quiet=True)

        assert generated == [("notes", "PlainThing")]
        generated_code = (tmp_path / "notes__plain_thing.py").read_text(encoding="utf-8")
        assert "class notes__PlainThing(TextContent):" in generated_code

    def test_generate_skips_native_domain_and_writes_no_init(self, tmp_path: Path) -> None:
        """Native-domain blueprints generate nothing — not even an __init__.py."""
        blueprints = [
            PipelexBundleBlueprint(domain="native", description="native stub", concept={"NativeStub": "native stub concept"}),
        ]

        generated = generate_structures_from_blueprints(blueprints, output_directory=tmp_path, skip_existing_check=True, quiet=True)

        assert generated == []
        assert not (tmp_path / "__init__.py").exists()
        assert list(tmp_path.iterdir()) == []

    def test_generate_skips_manually_created_class(self, tmp_path: Path) -> None:
        """With existing-class checking on, a registered class suppresses generation."""
        manual_class: type = type("ManualDoctorTestConcept", (TextContent,), {})
        get_class_registry().register_class(manual_class, name="ManualDoctorTestConcept", should_warn_if_already_registered=False)
        try:
            blueprints = [
                PipelexBundleBlueprint(
                    domain="notes",
                    description="notes",
                    concept={"ManualDoctorTestConcept": ConceptBlueprint(description="Manually owned")},
                ),
            ]

            generated = generate_structures_from_blueprints(
                blueprints,
                output_directory=tmp_path,
                target_path=tmp_path,
                skip_existing_check=False,
                quiet=True,
            )

            assert generated == []
            assert not (tmp_path / "notes__manual_doctor_test_concept.py").exists()
        finally:
            # The class registry is process-global — leaving the class registered would make later tests order-dependent
            get_class_registry().unregister_class_by_name("ManualDoctorTestConcept")

    def test_generate_non_quiet_echoes_progress(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Without quiet, progress is echoed through typer."""
        echo_mock = mocker.patch("pipelex.cli.commands.build.structures_cmd.typer.echo")
        secho_mock = mocker.patch("pipelex.cli.commands.build.structures_cmd.typer.secho")
        blueprints = [
            PipelexBundleBlueprint(domain="notes", description="notes", concept={"LoudNote": "A loud note"}),
        ]

        generate_structures_from_blueprints(blueprints, output_directory=tmp_path, skip_existing_check=True, quiet=False)

        echo_mock.assert_called_once()
        secho_calls = [str(call.args[0]) for call in secho_mock.call_args_list]
        assert any("notes__loud_note.py" in message for message in secho_calls)
        assert any("__init__.py" in message for message in secho_calls)
