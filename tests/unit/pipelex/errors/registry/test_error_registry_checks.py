from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from pipelex.cli.dev_cli.commands.error_registry.exceptions import ErrorRegistryError
from pipelex.cli.dev_cli.commands.error_registry.registry_checks import (
    model_errors,
    registry_errors,
    schema_errors,
    semantic_errors,
)
from pipelex.cli.dev_cli.commands.error_registry.registry_source import DOCS_DIR, compose_registry_document, load_registry_source
from pipelex.errors.registry.registry_document import ErrorRegistryDocument

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

WHERE = "registry"

# The members the format requires of every entry.
REQUIRED_ENTRY_MEMBERS = ["code", "title", "domain", "retry", "raised_as", "detail", "steps", "params", "meaning", "what_to_do"]


def _entry(document: dict[str, Any], code: str) -> dict[str, Any]:
    for entry in document["codes"]:
        if entry["code"] == code:
            found: dict[str, Any] = entry
            return found
    msg = f"no entry {code}"
    raise KeyError(msg)


def _set_member(code: str, member: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def mutate(document: dict[str, Any]) -> None:
        _entry(document, code)[member] = value

    return mutate


def _add_param(code: str, name: str, param: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    def mutate(document: dict[str, Any]) -> None:
        _entry(document, code)["params"][name] = param

    return mutate


def _set_document_member(member: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def mutate(document: dict[str, Any]) -> None:
        document[member] = value

    return mutate


def _set_actor_detail(code: str, detail: str) -> Callable[[dict[str, Any]], None]:
    def mutate(document: dict[str, Any]) -> None:
        _entry(document, code)["steps"]["actor"]["detail"] = detail

    return mutate


def _duplicate_first_code(document: dict[str, Any]) -> None:
    document["codes"].append(copy.deepcopy(document["codes"][0]))


def _add_unused_family(document: dict[str, Any]) -> None:
    document["families"].append({"family": "pipelex.unused", "description": "A family no code uses."})


def _add_family_outside_prefix(document: dict[str, Any]) -> None:
    document["families"].append({"family": "other.billing", "description": "A family outside the prefix."})
    entry = copy.deepcopy(_entry(document, "pipelex.billing.credit_exhausted"))
    entry["code"] = "other.billing.credit_exhausted"
    document["codes"].append(entry)


def _move_code_to_undeclared_family(document: dict[str, Any]) -> None:
    _entry(document, "pipelex.billing.credit_exhausted")["code"] = "pipelex.nowhere.credit_exhausted"


def _remove_status_of_a_problem(document: dict[str, Any]) -> None:
    del _entry(document, "pipelex.billing.credit_exhausted")["status"]


class TestErrorRegistryChecks:
    def test_the_committed_registry_passes_every_check(
        self, composed_document: dict[str, Any], standard_schema: dict[str, Any], core_registry: ErrorRegistryDocument
    ) -> None:
        """The committed source, composed with Pipelex's version, has no fault in any pass."""
        errors = registry_errors(document=composed_document, schema=standard_schema, core=core_registry, docs_dir=DOCS_DIR, where=WHERE)
        assert errors == []
        registry = ErrorRegistryDocument.model_validate(composed_document)
        assert registry.prefix == "pipelex"
        assert registry.base_url == "https://docs.pipelex.com/errors"
        assert all(entry.code.startswith("pipelex.") for entry in registry.codes)

    @pytest.mark.parametrize("member", REQUIRED_ENTRY_MEMBERS)
    def test_an_entry_missing_a_member_is_refused_by_the_schema_and_the_typed_model(
        self, composed_document: dict[str, Any], standard_schema: dict[str, Any], member: str
    ) -> None:
        """Every entry declares every member its code needs: removing one is refused by both readers."""
        del _entry(composed_document, "pipelex.storage.unavailable")[member]
        found_by_schema = schema_errors(document=composed_document, schema=standard_schema, where=WHERE)
        assert any(f"'{member}' is a required property" in error for error in found_by_schema), found_by_schema
        registry, found_by_model = model_errors(document=composed_document, where=WHERE)
        assert registry is None
        assert found_by_model

    @pytest.mark.parametrize(
        ("topic", "mutate"),
        [
            ("a domain outside the closed list", _set_member("pipelex.storage.unavailable", "domain", "caller")),
            ("a retry verdict outside the closed list", _set_member("pipelex.storage.unavailable", "retry", "maybe")),
            ("an empty step detail", _set_actor_detail("pipelex.storage.unavailable", "")),
            ("a member the format does not know", _set_member("pipelex.storage.unavailable", "severity", "high")),
            ("a status on a warning", _set_member("pipelex.docgen.template_warning", "status", 422)),
            ("a status on a client code", _set_member("pipelex.catalog.link_conflict", "status", 409)),
            ("a problem without a status", _remove_status_of_a_problem),
            ("a status outside the HTTP error range", _set_member("pipelex.storage.unavailable", "status", 302)),
            ("an empty title", _set_member("pipelex.storage.unavailable", "title", "")),
            ("an enum without values", _add_param("pipelex.storage.unavailable", "kind", {"type": "enum", "description": "A kind."})),
            ("a list without items", _add_param("pipelex.storage.unavailable", "names", {"type": "list", "description": "Names."})),
            (
                "values on an identifier",
                _add_param("pipelex.storage.unavailable", "name", {"type": "identifier", "values": ["one"], "description": "A name."}),
            ),
            ("an unknown parameter type", _add_param("pipelex.storage.unavailable", "size", {"type": "float", "description": "A size."})),
            (
                "a parameter name that is not a segment",
                _add_param("pipelex.storage.unavailable", "Name", {"type": "identifier", "description": "A."}),
            ),
            (
                "a reference to a page with uppercase letters",
                _set_member("pipelex.storage.unavailable", "see", [{"title": "PipeDocGen", "href": "building-methods/PipeDocGen.md"}]),
            ),
            ("an empty list of references", _set_member("pipelex.storage.unavailable", "see", [])),
            ("a code with two segments only", _set_member("pipelex.storage.unavailable", "code", "pipelex.unavailable")),
            ("a null status on a warning", _set_member("pipelex.docgen.template_warning", "status", None)),
            ("a null status on a client code", _set_member("pipelex.catalog.link_conflict", "status", None)),
            ("a null status on a problem", _set_member("pipelex.storage.unavailable", "status", None)),
            ("a null list of references", _set_member("pipelex.storage.unavailable", "see", None)),
            (
                "null items on a parameter that is not a list",
                _add_param("pipelex.storage.unavailable", "name", {"type": "identifier", "items": None, "description": "A name."}),
            ),
            (
                "null values on a parameter that is not an enum",
                _add_param("pipelex.storage.unavailable", "name", {"type": "identifier", "values": None, "description": "A name."}),
            ),
            (
                "null values on a list item that is not an enum",
                _add_param(
                    "pipelex.storage.unavailable",
                    "names",
                    {"type": "list", "items": {"type": "identifier", "values": None}, "description": "Names."},
                ),
            ),
            (
                "a null optional mark",
                _add_param("pipelex.storage.unavailable", "name", {"type": "identifier", "optional": None, "description": "A name."}),
            ),
            ("a null list of extension prefixes", _set_document_member("extension_prefixes", None)),
            ("a null prefix", _set_document_member("prefix", None)),
        ],
    )
    def test_a_malformed_entry_is_refused_by_the_schema_and_the_typed_model(
        self,
        composed_document: dict[str, Any],
        standard_schema: dict[str, Any],
        topic: str,
        mutate: Callable[[dict[str, Any]], None],
    ) -> None:
        """What the format's schema refuses, the typed model refuses too, so the model never accepts a document the schema would not."""
        mutate(composed_document)
        assert schema_errors(document=composed_document, schema=standard_schema, where=WHERE), f"the schema accepted {topic}"
        registry, found_by_model = model_errors(document=composed_document, where=WHERE)
        assert registry is None, f"the typed model accepted {topic}"
        assert found_by_model

    def test_the_snapshot_reader_refuses_a_null_member(self, composed_document: dict[str, Any]) -> None:
        """The public loader reads JSON through the typed model alone, so the model refuses a null as the schema does, naming it."""
        _entry(composed_document, "pipelex.docgen.template_warning")["status"] = None
        with pytest.raises(PydanticValidationError, match="the member 'status' is null"):
            ErrorRegistryDocument.model_validate_json(json.dumps(composed_document))

    def test_a_step_kind_outside_the_closed_list_is_refused(self, composed_document: dict[str, Any], standard_schema: dict[str, Any]) -> None:
        """The step kinds are the protocol's closed list."""
        _entry(composed_document, "pipelex.storage.unavailable")["steps"]["actor"]["kind"] = "shout"
        assert schema_errors(document=composed_document, schema=standard_schema, where=WHERE)
        registry, _found = model_errors(document=composed_document, where=WHERE)
        assert registry is None

    @pytest.mark.parametrize(
        ("mutate", "expected"),
        [
            (_duplicate_first_code, "the code is declared twice"),
            (_move_code_to_undeclared_family, "its family pipelex.nowhere is not declared under families"),
            (_add_unused_family, "the family pipelex.unused is declared but no code belongs to it"),
            (_add_family_outside_prefix, "the family other.billing does not start with the prefix pipelex"),
            (
                _set_member("pipelex.storage.unavailable", "detail", "The storage failed on {nothing}."),
                "detail names {nothing}, which the code does not declare",
            ),
            (
                _set_member("pipelex.catalog.not_found", "detail", "No version {version} here."),
                "detail names {version}, which is optional and may be absent",
            ),
            (
                _set_member("pipelex.config.invalid", "detail", "The file '{file}' is invalid."),
                "detail names the operator-only {file}, which a caller may read",
            ),
            (
                _set_member("pipelex.config.invalid", "detail", "The runtime's configuration is {invalid!r}."),
                "detail: placeholder {invalid} carries a format specification",
            ),
            (
                _set_member("pipelex.storage.unavailable", "see", [{"title": "Nowhere", "href": "nowhere/page.md"}]),
                "see names nowhere/page.md, which the documentation does not hold",
            ),
            (
                _set_member("pipelex.storage.unavailable", "meaning", "Not `input.nonexistent`, but this."),
                "names `input.nonexistent`, which the core registry",
            ),
            (
                _set_member("pipelex.storage.unavailable", "what_to_do", "Read `pipelex.storage.vanished` first."),
                "names `pipelex.storage.vanished`, which this registry does not declare",
            ),
            (
                _add_param("pipelex.storage.unavailable", "class", {"type": "identifier", "description": "A class."}),
                "the parameter class is a Python keyword",
            ),
            (
                _add_param("pipelex.storage.unavailable", "model_dump", {"type": "identifier", "description": "A dump."}),
                "the parameter model_dump names an attribute of the generated parameters model",
            ),
            (
                _add_param("pipelex.storage.unavailable", "code", {"type": "identifier", "description": "A code."}),
                "the parameter code names an attribute of the generated parameters model",
            ),
        ],
    )
    def test_a_rule_beyond_the_schema_is_enforced(
        self,
        composed_document: dict[str, Any],
        standard_schema: dict[str, Any],
        core_registry: ErrorRegistryDocument,
        mutate: Callable[[dict[str, Any]], None],
        expected: str,
    ) -> None:
        """The rules a JSON Schema cannot state are refused, each with the code it found the fault in."""
        mutate(composed_document)
        assert schema_errors(document=composed_document, schema=standard_schema, where=WHERE) == []
        errors = registry_errors(document=composed_document, schema=standard_schema, core=core_registry, docs_dir=DOCS_DIR, where=WHERE)
        assert any(expected in error for error in errors), errors

    def test_an_operator_only_parameter_is_named_only_in_the_actor_step_of_an_operator_code(
        self, composed_document: dict[str, Any], standard_schema: dict[str, Any], core_registry: ErrorRegistryDocument
    ) -> None:
        """The actor of a runtime code is whoever made the call, who may not read an operator-only parameter."""
        entry = _entry(composed_document, "pipelex.storage.unavailable")
        entry["params"]["bucket"] = {"type": "identifier", "operator_only": True, "description": "The bucket."}
        entry["steps"]["actor"]["detail"] = "Check the bucket '{bucket}'."
        errors = registry_errors(document=composed_document, schema=standard_schema, core=core_registry, docs_dir=DOCS_DIR, where=WHERE)
        assert any("steps.actor.detail names the operator-only {bucket}" in error for error in errors), errors
        config_entry = _entry(composed_document, "pipelex.config.invalid")
        assert "{setting}" in config_entry["steps"]["actor"]["detail"]

    def test_the_prefix_must_be_registered_in_the_core_registry_under_the_same_base_url(
        self, composed_document: dict[str, Any], core_registry: ErrorRegistryDocument
    ) -> None:
        """The core registry registers the prefix, and the pages are published under the base URL it names."""
        registry = ErrorRegistryDocument.model_validate(composed_document)
        unregistered_core = core_registry.model_copy(update={"extension_prefixes": []})
        errors = semantic_errors(registry=registry, core=unregistered_core, docs_dir=DOCS_DIR, where=WHERE)
        assert any("does not register the prefix pipelex" in error for error in errors), errors
        elsewhere = registry.model_copy(update={"base_url": "https://errors.pipelex.com/codes"})
        errors = semantic_errors(registry=elsewhere, core=core_registry, docs_dir=DOCS_DIR, where=WHERE)
        assert any("is not the https://docs.pipelex.com/errors that the core registry" in error for error in errors), errors

    def test_a_duplicate_yaml_key_is_refused(self, tmp_path: Path) -> None:
        """A YAML loader would keep the second of two equal keys silently; the registry's loader refuses it."""
        source_path = tmp_path / "registry.yaml"
        source_path.write_text("prefix: pipelex\nprefix: acme\n", encoding="utf-8")
        with pytest.raises(ErrorRegistryError, match="duplicate key 'prefix'"):
            load_registry_source(path=source_path)

    def test_a_source_that_writes_its_own_version_is_refused(self) -> None:
        """The version is Pipelex's, from pyproject.toml, and written nowhere else."""
        with pytest.raises(ErrorRegistryError, match="writes a version"):
            compose_registry_document(source={"version": "1.0.0", "prefix": "pipelex"}, version="0.87.0")
        composed = compose_registry_document(source={"prefix": "pipelex"}, version="0.87.0")
        assert list(composed) == ["version", "prefix"]
