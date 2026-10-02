"""The template surface: what a type declares a template may do with its instances beyond reading public data.

Templates render under `PipelexTemplateEnvironment`, whose policy lets a template read public data
and call methods of plain values (strings, numbers, dates, containers) and nothing else. A type
whose instances templates need to call methods on, or read an underscore-prefixed name of, declares
exactly those names as its template surface, the way `StuffArtefact` declares its dict-like
accessors and its metadata fields.

The surface is read from the type, never from the instance: `StuffArtefact` answers attribute
lookups with content fields first, so an instance lookup would let a content field named like the
declaration replace it. The declaration's name is a dunder for the same reason, since no content
field can be spelled that way.

This module lives in `tools/` and imports nothing from `core/`, which is the layering the other
template protocols (`TagRenderable`, `ImageRenderable`) follow.
"""

from __future__ import annotations

from typing import Any

from pydantic.dataclasses import dataclass

TEMPLATE_SURFACE_ATTRIBUTE = "__template_surface__"


@dataclass(frozen=True)
class TemplateSurface:
    """What a template may do with an instance of the declaring type, beyond reading public data.

    Attributes:
        callable_names: The methods a template may call on an instance.
        private_names: The underscore-prefixed names a template may read, with a dot or with brackets.
    """

    callable_names: frozenset[str]
    private_names: frozenset[str]

    def __post_init__(self) -> None:
        # A dunder is never data: declaring one would reopen the path to Python internals.
        for name in self.private_names:
            if not name.startswith("_") or name.startswith("__"):
                msg = f"A template surface's private names start with a single underscore, and '{name}' does not."
                raise ValueError(msg)


def get_template_surface(obj: object) -> TemplateSurface | None:
    """Return the template surface the type of `obj` declares, or None when it declares none."""
    surface: Any = getattr(type(obj), TEMPLATE_SURFACE_ATTRIBUTE, None)
    if isinstance(surface, TemplateSurface):
        return surface
    return None
