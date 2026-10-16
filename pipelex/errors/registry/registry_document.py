"""The typed model of an MTHDS error registry document, and the loader of Pipelex's own.

An error registry, in the format the MTHDS standard defines (`spec/error-registry.md` on mthds.ai),
declares one entry per error code: its title, the domain whose actor must act, its retry verdict,
the step for that actor and for any other reader, its typed parameters, its templates and its HTTP
status. The model below reads that format, the core registry's as well as an extension owner's, and
refuses what the format's JSON Schema refuses: a member missing, a member it does not know, a value
outside its closed lists, a member present where the format forbids it, and a member written as `null`.

Pipelex's own registry, under the `pipelex` extension prefix, is authored in
`pipelex-error-registry.yaml` beside this module and ships as its JSON snapshot,
`pipelex-error-registry.json`, which :func:`load_pipelex_error_registry` reads.
"""

from __future__ import annotations

import functools
import importlib.resources
import re
from enum import StrEnum
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

PIPELEX_ERROR_REGISTRY_PACKAGE = "pipelex.errors.registry"
PIPELEX_ERROR_REGISTRY_SNAPSHOT_NAME = "pipelex-error-registry.json"

_SEGMENT_PATTERN = r"[a-z][a-z0-9_]*"
_SEGMENT_REGEX = re.compile(rf"^{_SEGMENT_PATTERN}$")
# An https URL with a lowercase host, an optional port and a path of non-empty segments, with no trailing slash, query or fragment.
_BASE_URL_PATTERN = (
    r"^https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~%!$&'()*+,;=:@-]+)*$"
)


class RegistryDomain(StrEnum):
    """Who must act on a code: the closed list of `ProblemDomain` in the MTHDS protocol."""

    INPUT = "input"
    METHOD = "method"
    ACCOUNT = "account"
    OPERATOR = "operator"
    RUNTIME = "runtime"


class RegistryRetry(StrEnum):
    """Whether repeating the operation can succeed: the closed list of `RetryVerdict` in the MTHDS protocol."""

    NO = "no"
    YES = "yes"
    OUTCOME_UNKNOWN = "outcome_unknown"


class RegistryStepKind(StrEnum):
    """What the reader does next: the closed list of `StepKind` in the MTHDS protocol."""

    RETRY = "retry"
    WAIT = "wait"
    READ_RUN = "read_run"
    REFRESH = "refresh"
    CHANGE_INPUT = "change_input"
    CHANGE_METHOD = "change_method"
    CHANGE_MODEL = "change_model"
    CHECK_CREDENTIALS = "check_credentials"
    REQUEST_ACCESS = "request_access"
    CHECK_ACCOUNT = "check_account"
    FIX_CONFIGURATION = "fix_configuration"
    UPGRADE = "upgrade"
    CONTACT_OWNER = "contact_owner"
    REPORT = "report"


class RegistryRaisedAs(StrEnum):
    """How a code reaches a reader, which decides whether it has an HTTP status."""

    PROBLEM = "problem"
    WARNING = "warning"
    CLIENT = "client"

    @property
    def has_status(self) -> bool:
        """Whether a code raised this way carries an HTTP status: only a problem document does."""
        match self:
            case RegistryRaisedAs.PROBLEM:
                return True
            case RegistryRaisedAs.WARNING | RegistryRaisedAs.CLIENT:
                return False


class RegistryParamType(StrEnum):
    """The type of a parameter: a scalar type, or `list` for a list of items of a scalar type."""

    IDENTIFIER = "identifier"
    INTEGER = "integer"
    SECONDS = "seconds"
    BYTES = "bytes"
    SHA256 = "sha256"
    ENUM = "enum"
    CALLER_TEXT = "caller_text"
    LIST = "list"

    @property
    def is_enum(self) -> bool:
        """Whether a parameter of this type lists the values it may hold."""
        match self:
            case RegistryParamType.ENUM:
                return True
            case (
                RegistryParamType.IDENTIFIER
                | RegistryParamType.INTEGER
                | RegistryParamType.SECONDS
                | RegistryParamType.BYTES
                | RegistryParamType.SHA256
                | RegistryParamType.CALLER_TEXT
                | RegistryParamType.LIST
            ):
                return False

    @property
    def is_list(self) -> bool:
        """Whether a parameter of this type holds a list of items."""
        match self:
            case RegistryParamType.LIST:
                return True
            case (
                RegistryParamType.IDENTIFIER
                | RegistryParamType.INTEGER
                | RegistryParamType.SECONDS
                | RegistryParamType.BYTES
                | RegistryParamType.SHA256
                | RegistryParamType.ENUM
                | RegistryParamType.CALLER_TEXT
            ):
                return False


class _RegistryModel(BaseModel):
    """The base of every part of a registry document: closed, so a member the format does not know is refused.

    No member of the format may be null: a member the format makes optional is left out, never written as
    `null`, and one it forbids in a case is absent in that case. The fields that model such a member are
    `None` when it is absent, so an explicit `null` is refused before validation, as the format's schema
    refuses it, rather than read as the member being absent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _refuse_null_members(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        members = cast("dict[Any, Any]", data)
        for member, value in members.items():
            if value is None:
                msg = f"the member '{member}' is null, which the format never allows: leave it out instead"
                raise ValueError(msg)
        return members


def _check_enum_values(*, param_type: RegistryParamType, values: list[str] | None) -> None:
    """Refuse values on a type that is not an enum, and an enum without values, as the format's schema does."""
    if param_type.is_enum:
        if not values:
            msg = "an enum lists its values"
            raise ValueError(msg)
        if len(set(values)) != len(values):
            msg = "an enum lists each of its values once"
            raise ValueError(msg)
        for value in values:
            if not _SEGMENT_REGEX.match(value):
                msg = f"the enum value '{value}' is not a lowercase segment"
                raise ValueError(msg)
    elif values is not None:
        msg = f"a parameter of type '{param_type}' lists no values"
        raise ValueError(msg)


class RegistryItemType(_RegistryModel):
    """The type of each item of a list parameter."""

    item_type: RegistryParamType = Field(alias="type", strict=False)
    values: list[str] | None = None

    @model_validator(mode="after")
    def _validate_item_type(self) -> Self:
        if self.item_type.is_list:
            msg = "the item of a list is a scalar type, never a list"
            raise ValueError(msg)
        _check_enum_values(param_type=self.item_type, values=self.values)
        return self


class RegistryParam(_RegistryModel):
    """One parameter of a code: a typed fact its sentences are written from."""

    param_type: RegistryParamType = Field(alias="type", strict=False)
    values: list[str] | None = None
    items: RegistryItemType | None = None
    description: str = Field(min_length=1, pattern=r"\S")
    optional: bool = False
    operator_only: bool = False

    @model_validator(mode="after")
    def _validate_param_type(self) -> Self:
        _check_enum_values(param_type=self.param_type, values=self.values)
        if self.param_type.is_list:
            if self.items is None:
                msg = "a list parameter declares the type of its items"
                raise ValueError(msg)
        elif self.items is not None:
            msg = f"a parameter of type '{self.param_type}' declares no items"
            raise ValueError(msg)
        return self


class RegistryStep(_RegistryModel):
    """One next step: its closed kind and the template of its detail sentence."""

    kind: RegistryStepKind = Field(strict=False)
    detail: str = Field(min_length=1, pattern=r"\S")


class RegistrySteps(_RegistryModel):
    """The step for the domain's actor and the step for any other reader."""

    actor: RegistryStep
    other: RegistryStep


class RegistryReference(_RegistryModel):
    """A documentation page that defines the situation a code names, and the text to link it with."""

    title: str = Field(min_length=1, pattern=r"\S")
    href: str = Field(pattern=r"^[a-z0-9_\-]+(/[a-z0-9_\-.]+)*\.md(#[a-z0-9_\-]+)?$")


class RegistryFamily(_RegistryModel):
    """A family of codes and what its codes are about."""

    family: str
    description: str = Field(min_length=1, pattern=r"\S")


class RegistryExtensionPrefix(_RegistryModel):
    """A registered extension prefix, as the core registry lists it."""

    prefix: str = Field(pattern=rf"^{_SEGMENT_PATTERN}$")
    owner: str = Field(min_length=1, pattern=r"\S")
    base_url: str = Field(pattern=_BASE_URL_PATTERN)


class RegistryEntry(_RegistryModel):
    """One code and everything a reader needs from it."""

    code: str
    title: str = Field(min_length=1, pattern=r"\S")
    domain: RegistryDomain = Field(strict=False)
    retry: RegistryRetry = Field(strict=False)
    raised_as: RegistryRaisedAs = Field(strict=False)
    status: int | None = Field(default=None, ge=400, le=599)
    detail: str = Field(min_length=1, pattern=r"\S")
    steps: RegistrySteps
    params: dict[str, RegistryParam]
    meaning: str = Field(min_length=1, pattern=r"\S")
    what_to_do: str = Field(min_length=1, pattern=r"\S")
    see: list[RegistryReference] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_entry(self) -> Self:
        if self.raised_as.has_status:
            if self.status is None:
                msg = f"the code '{self.code}', raised as a problem, has an HTTP status"
                raise ValueError(msg)
        elif self.status is not None:
            msg = f"the code '{self.code}', raised as '{self.raised_as}', has no HTTP status"
            raise ValueError(msg)
        for param_name in self.params:
            if not _SEGMENT_REGEX.match(param_name):
                msg = f"the parameter name '{param_name}' of the code '{self.code}' is not a lowercase segment"
                raise ValueError(msg)
        return self

    @property
    def family(self) -> str:
        """The code's family: the code without its last segment."""
        return self.code.rsplit(".", 1)[0]

    @property
    def page_path(self) -> str:
        """The code's documentation page, from the documentation's root: one directory per segment but the last."""
        return f"errors/{self.code.replace('.', '/')}.md"


class ErrorRegistryDocument(_RegistryModel):
    """An error registry: the core registry, or the registry of an extension prefix's owner."""

    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")
    prefix: str | None = Field(default=None, pattern=rf"^{_SEGMENT_PATTERN}$")
    base_url: str = Field(pattern=_BASE_URL_PATTERN)
    extension_prefixes: list[RegistryExtensionPrefix] | None = None
    families: list[RegistryFamily] = Field(min_length=1)
    codes: list[RegistryEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_document(self) -> Self:
        segment_count: int
        if self.prefix is None:
            if self.extension_prefixes is None:
                msg = "a core registry, which has no prefix, lists the registered extension prefixes"
                raise ValueError(msg)
            segment_count = 2
        else:
            if self.extension_prefixes is not None:
                msg = "an extension registry lists no extension prefixes"
                raise ValueError(msg)
            segment_count = 3
        code_pattern = re.compile(rf"^{_SEGMENT_PATTERN}(\.{_SEGMENT_PATTERN}){{{segment_count - 1}}}$")
        family_pattern = re.compile(rf"^{_SEGMENT_PATTERN}(\.{_SEGMENT_PATTERN}){{{segment_count - 2}}}$")
        for family in self.families:
            if not family_pattern.match(family.family):
                msg = f"the family '{family.family}' does not have {segment_count - 1} segment(s)"
                raise ValueError(msg)
        for entry in self.codes:
            if not code_pattern.match(entry.code):
                msg = f"the code '{entry.code}' does not have {segment_count} segments"
                raise ValueError(msg)
        return self

    def type_uri(self, *, code: str) -> str:
        """The type URI of a code: the registry's base URL, a slash, then the whole code."""
        return f"{self.base_url}/{code}"

    def entry(self, *, code: str) -> RegistryEntry | None:
        """The entry of a code, or `None` when this registry does not declare it."""
        for registry_entry in self.codes:
            if registry_entry.code == code:
                return registry_entry
        return None


def read_pipelex_error_registry_snapshot_text() -> str:
    """The text of Pipelex's error registry snapshot, as the package ships it."""
    resource = importlib.resources.files(PIPELEX_ERROR_REGISTRY_PACKAGE).joinpath(PIPELEX_ERROR_REGISTRY_SNAPSHOT_NAME)
    return resource.read_text(encoding="utf-8")


@functools.cache
def load_pipelex_error_registry() -> ErrorRegistryDocument:
    """Pipelex's error registry, read once from the snapshot the package ships."""
    return ErrorRegistryDocument.model_validate_json(read_pipelex_error_registry_snapshot_text())
