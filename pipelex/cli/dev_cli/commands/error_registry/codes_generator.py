"""The generator of ``pipelex/errors/registry/pipelex_codes.py``: the Pipelex codes and their typed parameters.

For each code of the registry the module holds a member of ``PipelexErrorCode`` and a frozen,
closed and strict pydantic model of its parameters, so that whoever raises a code builds its parameters
with the types the registry declares and none it does not, a value of another type being refused
rather than coerced:

- ``identifier`` and ``caller_text`` are ``str``, ``integer`` is ``int``;
- ``seconds`` is a ``float`` and ``bytes`` an ``int``, neither ever negative;
- ``sha256`` is a ``str`` of lowercase hexadecimal;
- ``enum`` is the ``Literal`` of its values, and ``list`` a ``list`` of its items' type, each item
  constrained as a parameter of that type is;
- an optional parameter is its type or ``None``, ``None`` by default.

Each model also names its code and its operator-only parameters, which an implementation leaves out of
every problem it answers to a caller. The text is written so that ``ruff format`` leaves it as it is,
which the test suite checks by regenerating it.
"""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING

from pipelex.cli.dev_cli.commands.error_registry.exceptions import ErrorRegistryError
from pipelex.errors.registry.registry_document import RegistryItemType, RegistryParam, RegistryParamType

if TYPE_CHECKING:
    from pipelex.errors.registry.registry_document import ErrorRegistryDocument, RegistryEntry

_LINE_LENGTH = 150
_DOCSTRING_WIDTH = 110
_SHA256_PATTERN = "^[0-9a-f]{64}$"


def _local_code(*, registry: ErrorRegistryDocument, code: str) -> str:
    """A code without the registry's prefix, which the generated names leave out."""
    if registry.prefix is not None and code.startswith(f"{registry.prefix}."):
        return code[len(registry.prefix) + 1 :]
    return code


def code_member_name(*, registry: ErrorRegistryDocument, code: str) -> str:
    """The ``PipelexErrorCode`` member of a code: its family and name, upper-cased, such as ``BILLING_PLAN_LIMIT``."""
    return _local_code(registry=registry, code=code).replace(".", "_").upper()


def params_class_name(*, registry: ErrorRegistryDocument, code: str) -> str:
    """The parameters model of a code: its family and name in PascalCase, then ``Params``, such as ``BillingPlanLimitParams``."""
    words = _local_code(registry=registry, code=code).replace(".", "_").split("_")
    return "".join(word.capitalize() for word in words) + "Params"


class _Imports:
    """Which names the generated module uses, so that it imports exactly those."""

    def __init__(self) -> None:
        self.uses_annotated = False
        self.uses_literal = False
        self.uses_field = False


def _literal(*, values: list[str]) -> str:
    return "Literal[" + ", ".join(json.dumps(value) for value in values) + "]"


def _scalar_annotation(*, scalar_type: RegistryParamType, values: list[str] | None, imports: _Imports) -> str:
    match scalar_type:
        case RegistryParamType.IDENTIFIER | RegistryParamType.CALLER_TEXT | RegistryParamType.SHA256:
            return "str"
        case RegistryParamType.INTEGER | RegistryParamType.BYTES:
            return "int"
        case RegistryParamType.SECONDS:
            return "float"
        case RegistryParamType.ENUM:
            imports.uses_literal = True
            return _literal(values=values or [])
        case RegistryParamType.LIST:
            msg = "a list's items are of a scalar type"
            raise ErrorRegistryError(msg)


def _scalar_constraints(*, scalar_type: RegistryParamType) -> list[str]:
    """The field constraints a scalar type adds to its Python type: none for a list, whose items carry their own."""
    match scalar_type:
        case RegistryParamType.SECONDS | RegistryParamType.BYTES:
            return ["ge=0"]
        case RegistryParamType.SHA256:
            return [f"pattern={json.dumps(_SHA256_PATTERN)}"]
        case (
            RegistryParamType.IDENTIFIER | RegistryParamType.INTEGER | RegistryParamType.ENUM | RegistryParamType.CALLER_TEXT | RegistryParamType.LIST
        ):
            return []


def _item_annotation(*, item_type: RegistryItemType, imports: _Imports) -> str:
    """The annotation of a list's item: its scalar's Python type, constrained as a parameter of that type is."""
    annotation = _scalar_annotation(scalar_type=item_type.item_type, values=item_type.values, imports=imports)
    constraints = _scalar_constraints(scalar_type=item_type.item_type)
    if not constraints:
        return annotation
    imports.uses_annotated = True
    imports.uses_field = True
    return f"Annotated[{annotation}, Field({', '.join(constraints)})]"


def _field_line(*, param_name: str, param: RegistryParam, imports: _Imports) -> str:
    """The line declaring one parameter's field."""
    annotation: str
    if param.param_type.is_list:
        if param.items is None:
            msg = f"the list parameter {param_name} declares no items"
            raise ErrorRegistryError(msg)
        annotation = f"list[{_item_annotation(item_type=param.items, imports=imports)}]"
    else:
        annotation = _scalar_annotation(scalar_type=param.param_type, values=param.values, imports=imports)
    constraints = _scalar_constraints(scalar_type=param.param_type)
    if param.optional:
        annotation = f"{annotation} | None"
        if constraints:
            imports.uses_field = True
            return f"    {param_name}: {annotation} = Field(default=None, {', '.join(constraints)})"
        return f"    {param_name}: {annotation} = None"
    if constraints:
        imports.uses_field = True
        return f"    {param_name}: {annotation} = Field({', '.join(constraints)})"
    return f"    {param_name}: {annotation}"


def _docstring_text(*, text: str, where: str) -> str:
    if "\\" in text or '"""' in text or text.endswith('"'):
        msg = f"{where} cannot be written into a docstring as it stands: it holds a backslash or a closing quote"
        raise ErrorRegistryError(msg)
    return text


def _params_class(*, registry: ErrorRegistryDocument, entry: RegistryEntry, imports: _Imports) -> list[str]:
    class_name = params_class_name(registry=registry, code=entry.code)
    member_name = code_member_name(registry=registry, code=entry.code)
    lines = [f"class {class_name}(PipelexErrorParams):"]
    title = _docstring_text(text=entry.title, where=f"{entry.code}: title")
    lines.append(f'    """The parameters of `{entry.code}`.')
    lines.append("")
    lines.extend(textwrap.wrap(f"{title}.", width=_DOCSTRING_WIDTH, initial_indent="    ", subsequent_indent="    ", break_long_words=False))
    if entry.params:
        lines.append("")
        lines.append("    Attributes:")
        for param_name, param in entry.params.items():
            description = _docstring_text(text=param.description, where=f"{entry.code}: params.{param_name}.description")
            wrapped = textwrap.wrap(
                f"{param_name}: {description}",
                width=_DOCSTRING_WIDTH,
                initial_indent="        ",
                subsequent_indent="            ",
                break_long_words=False,
                break_on_hyphens=False,
            )
            lines.extend(wrapped)
    lines.append('    """')
    lines.append("")
    lines.append(f"    code: ClassVar[PipelexErrorCode] = PipelexErrorCode.{member_name}")
    operator_only = [param_name for param_name, param in entry.params.items() if param.operator_only]
    if operator_only:
        names = ", ".join(json.dumps(param_name) for param_name in operator_only)
        lines.append(f"    operator_only_params: ClassVar[frozenset[str]] = frozenset({{{names}}})")
    if entry.params:
        lines.append("")
        for param_name, param in entry.params.items():
            line = _field_line(param_name=param_name, param=param, imports=imports)
            if len(line) > _LINE_LENGTH:
                msg = f"{entry.code}: the field of the parameter {param_name} runs past {_LINE_LENGTH} characters"
                raise ErrorRegistryError(msg)
            lines.append(line)
    return lines


def render_pipelex_codes(*, registry: ErrorRegistryDocument) -> str:
    """The text of ``pipelex_codes.py`` for a registry."""
    imports = _Imports()
    body: list[str] = [
        "",
        "class PipelexErrorCode(StrEnum):",
        '    """Every code of the Pipelex error registry."""',
        "",
    ]
    body.extend(f"    {code_member_name(registry=registry, code=entry.code)} = {json.dumps(entry.code)}" for entry in registry.codes)
    body.extend(
        [
            "",
            "",
            "class PipelexErrorParams(BaseModel):",
            '    """The parameters of a Pipelex code: the base of each code\'s own model, closed, frozen and strict.',
            "",
            '    Strict, so that a value of another type is refused rather than coerced: a line given as ``"3"`` or',
            "    ``True`` is refused rather than read as an integer. An integer is still accepted where a number of",
            "    seconds is declared.",
            "",
            "    Attributes:",
            "        code: The code whose parameters the model holds.",
            "        operator_only_params: The parameters that only whoever runs the runtime may read, which an",
            "            implementation leaves out of every problem it answers to a caller.",
            '    """',
            "",
            '    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)',
            "",
            "    code: ClassVar[PipelexErrorCode]",
            "    operator_only_params: ClassVar[frozenset[str]] = frozenset()",
        ]
    )
    for entry in registry.codes:
        body.extend(["", ""])
        body.extend(_params_class(registry=registry, entry=entry, imports=imports))
    body.extend(
        [
            "",
            "",
            "PIPELEX_ERROR_PARAMS: dict[PipelexErrorCode, type[PipelexErrorParams]] = {",
        ]
    )
    for entry in registry.codes:
        member_name = code_member_name(registry=registry, code=entry.code)
        body.append(f"    PipelexErrorCode.{member_name}: {params_class_name(registry=registry, code=entry.code)},")
    body.append("}")
    body.append('"""The parameters model of every Pipelex code."""')

    typing_names = ["ClassVar"]
    if imports.uses_annotated:
        typing_names.insert(0, "Annotated")
    if imports.uses_literal:
        typing_names.append("Literal")
    pydantic_names = ["BaseModel", "ConfigDict", "Field"] if imports.uses_field else ["BaseModel", "ConfigDict"]
    header = [
        '"""The Pipelex error codes and the typed parameters of each, generated from ``pipelex-error-registry.yaml``.',
        "",
        "Generated by ``pipelex-dev generate-error-registry`` (``make generate-error-registry``): never edit it by",
        "hand. The registry beside it is the single source, and the test suite fails when this module is not what",
        "the generator writes from it.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from enum import StrEnum",
        f"from typing import {', '.join(typing_names)}",
        "",
        f"from pydantic import {', '.join(pydantic_names)}",
        "",
    ]
    return "\n".join([*header, *body]) + "\n"
