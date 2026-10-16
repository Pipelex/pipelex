"""The checks of Pipelex's error registry, after the MTHDS standard's own checks of the core registry.

A registry document is checked in three passes, each run only on a document the previous one accepts:

1. the format's JSON Schema, vendored from the standard, which refuses a member missing, unknown or
   forbidden in its case and a value outside its closed lists;
2. the typed model Pipelex reads the registry with (:mod:`pipelex.errors.registry.registry_document`),
   which refuses what the schema refuses, so that the model can never accept a document the schema
   would not;
3. the rules a schema cannot state, which the standard's repository applies to the core registry and
   which apply to an extension registry alike: a family or a code given twice, a code whose family is
   undeclared, a family no code uses, a code or a family outside the prefix, a template naming a
   parameter its reader may not see, and a reference to a documentation page that does not exist.
   To these, Pipelex adds the rules its own use of the registry needs: the prefix is registered in the
   core registry under the same base URL, every code a sentence names in backticks exists, and every
   parameter name can be a field of the typed Python generated from the registry.
"""

from __future__ import annotations

import keyword
import re
import string
from typing import TYPE_CHECKING, Any, Protocol, cast

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from pipelex.errors.registry.registry_document import ErrorRegistryDocument, RegistryDomain, RegistryEntry

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# A code a sentence names in backticks: segments joined by dots.
_BACKTICKED_CODE_REGEX = re.compile(r"`([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)`")
_PARAM_NAME_REGEX = re.compile(r"[a-z][a-z0-9_]*")

# The class attributes of a code's generated parameters model, which no parameter may be named after.
RESERVED_PARAM_NAMES = frozenset({"code", "operator_only_params"})


class _SchemaValidator(Protocol):
    """The typed view of a jsonschema validator this module uses.

    The `types-jsonschema` stubs type `iter_errors` as an overload whose deprecated second arm carries an unknown
    type, which strict pyright refuses; this view gives the call a clean type.
    """

    def iter_errors(self, *, instance: object) -> Iterator[ValidationError]: ...


def _code_at(*, document: dict[str, Any], index: str) -> str | None:
    """The code of the entry at an index of the document's codes, when it has one."""
    codes: Any = document.get("codes")
    if not isinstance(codes, list) or not index.isdigit():
        return None
    code_list = cast("list[Any]", codes)
    position = int(index)
    if position >= len(code_list):
        return None
    entry: Any = code_list[position]
    if not isinstance(entry, dict):
        return None
    code: Any = cast("dict[str, Any]", entry).get("code")
    return code if isinstance(code, str) else None


def schema_errors(*, document: dict[str, Any], schema: dict[str, Any], where: str) -> list[str]:
    """The faults the format's JSON Schema finds, each named by its path in the document, a code's index by the code."""
    validator = cast("_SchemaValidator", Draft202012Validator(schema, format_checker=FormatChecker()))
    found_errors: list[ValidationError] = sorted(
        validator.iter_errors(instance=document), key=lambda found: [str(part) for part in found.absolute_path]
    )
    errors: list[str] = []
    for error in found_errors:
        parts = [str(part) for part in error.absolute_path]
        if len(parts) >= 2 and parts[0] == "codes":
            code = _code_at(document=document, index=parts[1])
            if code is not None:
                parts[1] = code
        path = "/".join(parts) or "(root)"
        errors.append(f"{where}: {path}: {error.message}")
    return errors


def model_errors(*, document: dict[str, Any], where: str) -> tuple[ErrorRegistryDocument | None, list[str]]:
    """The typed registry the document validates into, or the faults the typed model finds."""
    try:
        return ErrorRegistryDocument.model_validate(document), []
    except PydanticValidationError as exc:
        errors: list[str] = []
        for error in exc.errors():
            location = "/".join(str(part) for part in error["loc"]) or "(root)"
            errors.append(f"{where}: {location}: {error['msg']}")
        return None, errors


def placeholders(*, template: str) -> list[str]:
    """The parameter names a template names.

    Raises:
        ValueError: When the template is malformed, or a placeholder is not a bare parameter name.
    """
    names: list[str] = []
    for _literal, field_name, format_spec, conversion in string.Formatter().parse(template):
        if field_name is None:
            continue
        if not _PARAM_NAME_REGEX.fullmatch(field_name):
            msg = f"placeholder {{{field_name}}} is not a parameter name"
            raise ValueError(msg)
        if format_spec or conversion:
            msg = f"placeholder {{{field_name}}} carries a format specification"
            raise ValueError(msg)
        names.append(field_name)
    return names


def template_errors(*, entry: RegistryEntry, here: str) -> list[str]:
    """Templates name declared parameters, and only those the reader of each may see.

    A parameter declared optional may be absent, so no template names it. An operator-only parameter
    never reaches a caller, so only the actor's step of an operator code, which whoever runs the
    runtime reads, may name one.
    """
    is_operator_code: bool
    match entry.domain:
        case RegistryDomain.OPERATOR:
            is_operator_code = True
        case RegistryDomain.INPUT | RegistryDomain.METHOD | RegistryDomain.ACCOUNT | RegistryDomain.RUNTIME:
            is_operator_code = False
    templates = [
        ("detail", entry.detail, False),
        ("steps.actor.detail", entry.steps.actor.detail, is_operator_code),
        ("steps.other.detail", entry.steps.other.detail, False),
    ]
    errors: list[str] = []
    for template_name, template, operator_reads in templates:
        try:
            names = placeholders(template=template)
        except ValueError as exc:
            errors.append(f"{here}: {template_name}: {exc}")
            continue
        for param_name in names:
            declared = entry.params.get(param_name)
            if declared is None:
                errors.append(f"{here}: {template_name} names {{{param_name}}}, which the code does not declare")
            elif declared.optional:
                errors.append(f"{here}: {template_name} names {{{param_name}}}, which is optional and may be absent")
            elif declared.operator_only and not operator_reads:
                errors.append(f"{here}: {template_name} names the operator-only {{{param_name}}}, which a caller may read")
    return errors


def _entry_texts(*, entry: RegistryEntry) -> list[tuple[str, str]]:
    """Every sentence of an entry, with the member it is written in."""
    texts = [
        ("title", entry.title),
        ("detail", entry.detail),
        ("steps.actor.detail", entry.steps.actor.detail),
        ("steps.other.detail", entry.steps.other.detail),
        ("meaning", entry.meaning),
        ("what_to_do", entry.what_to_do),
    ]
    texts.extend((f"params.{param_name}.description", param.description) for param_name, param in entry.params.items())
    return texts


def code_reference_errors(*, text: str, here: str, registry: ErrorRegistryDocument, core: ErrorRegistryDocument) -> list[str]:
    """A code named in backticks exists: a core code in the core registry, a code of this registry's prefix in this one.

    Only a name shaped like a code of one of the two registries is checked: two segments whose first is
    a core family, or three whose first is this registry's prefix. A file name such as `codegen.lock`
    is neither, and is left alone.
    """
    core_families = {family.family for family in core.families}
    errors: list[str] = []
    for match in _BACKTICKED_CODE_REGEX.finditer(text):
        name = match.group(1)
        segments = name.split(".")
        if len(segments) == 2 and segments[0] in core_families:
            if core.entry(code=name) is None:
                errors.append(f"{here} names `{name}`, which the core registry {core.version} does not declare")
        elif len(segments) == 3 and segments[0] == registry.prefix:
            if registry.entry(code=name) is None:
                errors.append(f"{here} names `{name}`, which this registry does not declare")
    return errors


def param_name_errors(*, entry: RegistryEntry, here: str) -> list[str]:
    """Every parameter name can be a field of the typed Python generated from the registry."""
    errors: list[str] = []
    for param_name in entry.params:
        if keyword.iskeyword(param_name) or keyword.issoftkeyword(param_name):
            errors.append(f"{here}: the parameter {param_name} is a Python keyword, which the generated parameters model cannot hold")
        elif param_name in RESERVED_PARAM_NAMES or hasattr(BaseModel, param_name):
            errors.append(f"{here}: the parameter {param_name} names an attribute of the generated parameters model")
    return errors


def semantic_errors(*, registry: ErrorRegistryDocument, core: ErrorRegistryDocument, docs_dir: Path, where: str) -> list[str]:
    """The rules a JSON Schema cannot state. Run only on a document the schema and the typed model accept."""
    errors: list[str] = []
    prefix = registry.prefix
    families = [family.family for family in registry.families]
    used_families: set[str] = set()

    for family in sorted({name for name in families if families.count(name) > 1}):
        errors.append(f"{where}: the family {family} is declared twice")
    if prefix is None:
        errors.append(f"{where}: an extension registry names its prefix")
    else:
        for family in families:
            if not family.startswith(f"{prefix}."):
                errors.append(f"{where}: the family {family} does not start with the prefix {prefix}")
        errors.extend(_registration_errors(registry=registry, core=core, prefix=prefix, where=where))

    for registry_family in registry.families:
        errors.extend(
            code_reference_errors(
                text=registry_family.description, here=f"{where}: {registry_family.family}: description", registry=registry, core=core
            )
        )

    seen_codes: set[str] = set()
    for entry in registry.codes:
        code = entry.code
        here = f"{where}: {code}"
        if code in seen_codes:
            errors.append(f"{here}: the code is declared twice")
        seen_codes.add(code)
        if prefix is not None and not code.startswith(f"{prefix}."):
            errors.append(f"{here}: the code does not start with the registry's prefix {prefix}")
        used_families.add(entry.family)
        if entry.family not in families:
            errors.append(f"{here}: its family {entry.family} is not declared under families")
        errors.extend(template_errors(entry=entry, here=here))
        errors.extend(param_name_errors(entry=entry, here=here))
        for member, text in _entry_texts(entry=entry):
            errors.extend(code_reference_errors(text=text, here=f"{here}: {member}", registry=registry, core=core))
        for reference in entry.see or []:
            page = reference.href.split("#", 1)[0]
            if not (docs_dir / page).is_file():
                errors.append(f"{here}: see names {page}, which the documentation does not hold")

    for family in families:
        if family not in used_families:
            errors.append(f"{where}: the family {family} is declared but no code belongs to it")
    return errors


def _registration_errors(*, registry: ErrorRegistryDocument, core: ErrorRegistryDocument, prefix: str, where: str) -> list[str]:
    """The prefix is registered in the core registry, under the base URL this registry publishes its pages at."""
    for registered in core.extension_prefixes or []:
        if registered.prefix == prefix:
            if registered.base_url != registry.base_url:
                msg = (
                    f"{where}: the base URL {registry.base_url} is not the {registered.base_url} that the core registry "
                    f"{core.version} registers the prefix {prefix} with"
                )
                return [msg]
            return []
    return [f"{where}: the core registry {core.version} does not register the prefix {prefix}"]


def registry_errors(*, document: dict[str, Any], schema: dict[str, Any], core: ErrorRegistryDocument, docs_dir: Path, where: str) -> list[str]:
    """Every fault of a registry document: the schema's, then the typed model's, then the rules beyond them."""
    errors = schema_errors(document=document, schema=schema, where=where)
    if errors:
        return errors
    registry, errors = model_errors(document=document, where=where)
    if registry is None:
        return errors
    return semantic_errors(registry=registry, core=core, docs_dir=docs_dir, where=where)
