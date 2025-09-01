from __future__ import annotations

import dataclasses
import enum
import inspect
import sys
import types
import typing
from typing import Any, Dict, List, Set, Tuple, Type, cast, get_args, get_origin, get_type_hints

from pydantic import BaseModel
from typing_extensions import Annotated as TE_Annotated
from typing_extensions import get_args as te_get_args
from typing_extensions import get_origin as te_get_origin


class StructurePrinter:
    """Render classes (Pydantic models, dataclasses, enums, domain types) into a readable string."""

    _UNION_ORIGINS: Tuple[type, ...] = tuple(t for t in (getattr(typing, "Union", None), getattr(types, "UnionType", None)) if t)

    # ---------- pretty printers ----------

    @classmethod
    def pretty_type(cls, tp: Any) -> str:
        # Prefer stdlib origin/args, fallback to typing_extensions
        origin = get_origin(tp) or te_get_origin(tp)
        args = get_args(tp) or te_get_args(tp) or ()

        # Handle cases where Annotated isn't recognized by get_origin
        if origin is None:
            s = str(tp)
            if "Annotated[" in s or s.startswith("Annotated[") or s.startswith("typing.Annotated"):
                try:
                    ann_args = te_get_args(tp) or get_args(tp) or ()
                    if ann_args:
                        return cls.pretty_type(ann_args[0])
                except Exception:
                    pass
            return getattr(tp, "__name__", s)

        # Union / Optional
        if origin in cls._UNION_ORIGINS:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1 and len(args) == 2:
                return f"Optional[{cls.pretty_type(non_none[0])}]"
            return "Union[" + ", ".join(cls.pretty_type(a) for a in non_none) + "]"

        # Literal (typing or typing_extensions)
        if str(origin).endswith("Literal"):
            lit = ", ".join(repr(getattr(a, "value", a)) for a in args)
            return f"Literal[{lit}]"

        # Annotated[T, ...] -> T
        if str(origin).endswith("Annotated") or (TE_Annotated and origin is TE_Annotated):
            if args:
                return cls.pretty_type(args[0])
            return str(tp)

        # Containers
        from typing import Dict as TDict
        from typing import List as TList
        from typing import Tuple as TTuple

        if origin in (list, TList):
            if args:
                return f"List[{cls.pretty_type(args[0])}]"
            return "List"
        if origin in (dict, TDict):
            if len(args) >= 2:
                return f"Dict[{cls.pretty_type(args[0])}, {cls.pretty_type(args[1])}]"
            return "Dict"
        if origin in (tuple, TTuple):
            return "Tuple[" + ", ".join(cls.pretty_type(a) for a in args) + "]"

        # Fallback for other generics
        name = getattr(origin, "__name__", str(origin))
        inner = ", ".join(cls.pretty_type(a) for a in args)
        return f"{name}[{inner}]" if inner else name

    @classmethod
    def extract_model_types(cls, tp: Any) -> Set[Type[Any]]:
        """Collect class types appearing inside a type annotation (recursively).
        Also collects Enum *types* when they appear as Literal values.
        """
        found: Set[Type[Any]] = set()
        origin = get_origin(tp) or te_get_origin(tp)
        if origin is None:
            if isinstance(tp, type):
                found.add(tp)
            return found

        args = get_args(tp) or te_get_args(tp) or ()

        # If Literal of enums, collect the enum's class
        if str(origin).endswith("Literal"):
            for a in args:
                if isinstance(a, enum.Enum):
                    found.add(type(a))

        for a in args:
            found |= cls.extract_model_types(a)
        return found

    # ---------- decisions ----------

    @classmethod
    def is_renderable_type(cls, _type: Any) -> bool:
        if not isinstance(_type, type):
            return False
        if _type in (object, type):
            return False
        # render Pydantic models, dataclasses, enums, and your own domain classes
        try:
            is_pydantic = issubclass(_type, BaseModel)
        except TypeError:
            is_pydantic = False

        try:
            is_dc = dataclasses.is_dataclass(_type)
        except Exception:
            is_dc = False

        try:
            is_enum = issubclass(_type, enum.Enum)
        except TypeError:
            is_enum = False

        module = getattr(_type, "__module__", None)
        is_pipelex = module.startswith("pipelex.") if isinstance(module, str) else False

        return is_pydantic or is_dc or is_enum or is_pipelex

    @classmethod
    def _is_content_base(cls, b: Type[Any], stop_at: Type[Any]) -> bool:
        if b is stop_at:
            return True
        name = getattr(b, "__name__", "")
        if name in {"StructuredContent", "TextContent", "ListContent"}:
            return True
        return b.__module__.startswith("pipelex.core.stuffs.stuff_content")

    # ---------- rendering ----------

    @classmethod
    def _normalize_base_name(cls, b: Any) -> str:
        """Return a non-generic display name for a base (strip T params)."""
        base_origin = get_origin(b) or te_get_origin(b)
        if base_origin is not None:
            b = base_origin

        # Try a clean __name__ first
        name = cast(str, getattr(b, "__name__", None))
        if name:
            if "[" in name:
                return name.split("[", 1)[0]
            return name

        # Fallback to str() patterns
        text = str(b)
        if "[" in text and "]" in text:
            return text.split("[", 1)[0].split(".")[-1].strip()
        if text.startswith("<class "):
            inside = text.split("'")[1]
            return inside.split(".")[-1]
        return text

    @classmethod
    def _display_base_name(cls, c: Type[Any], stop_at: Type[Any]) -> str:
        bases = list(c.__bases__)
        # special rule: if stop_at among bases, show the base immediately to its LEFT
        if stop_at in bases:
            idx = bases.index(stop_at)
            if idx > 0:
                return cls._normalize_base_name(bases[idx - 1])
            return cls._normalize_base_name(stop_at)
        # otherwise show first non-object base, if any
        for b in bases:
            if b is not object:
                return cls._normalize_base_name(b)
        return "object"

    @classmethod
    def _class_doc(cls, c: Type[Any]) -> str:
        """Own docstring only; suppress auto-docs for dataclasses."""
        import inspect as _inspect

        doc = (c.__dict__.get("__doc__") or "").strip()
        if not doc:
            return ""
        if dataclasses.is_dataclass(c):
            # Drop auto-generated signature-like docstrings (with or without quotes)
            if doc.startswith(f"{c.__name__}(") and doc.endswith(")"):
                return ""
            try:
                sig = str(_inspect.signature(c))
                if doc == f"{c.__name__}{sig}":
                    return ""
            except Exception:
                pass
        return doc

    @classmethod
    def _field_names_declared_on(cls, c: Type[Any]) -> List[str]:
        ann = c.__dict__.get("__annotations__", {})
        return list(ann.keys())

    @classmethod
    def _field_names_from_noncontent_bases(cls, c: Type[Any], stop_at: Type[Any]) -> List[Tuple[Type[Any], str]]:
        """
        Include base *fields* only when the class uses multiple inheritance with the content base.
        This matches the rule:
        - Employee(Person):           do NOT include Person fields
        - Mixed(BaseLeft, StructuredContent): include BaseLeft fields (left of stop_at)
        """
        pairs: List[Tuple[Type[Any], str]] = []
        if stop_at not in c.__bases__:  # only in the StructuredContent MI case
            return pairs
        for b in c.__bases__:
            if cls._is_content_base(b, stop_at):
                continue
            names = b.__dict__.get("__annotations__", {})
            for name in names.keys():
                pairs.append((b, name))
        return pairs

    @classmethod
    def _get_hints(cls, owner: Type[Any], localns: Dict[str, Any]) -> Dict[str, Any]:
        """Robust get_type_hints with module globals + caller locals; fall back to raw __annotations__ on failure."""
        try:
            owner_globals = sys.modules[owner.__module__].__dict__
        except KeyError:
            owner_globals = {}
        try:
            return get_type_hints(owner, globalns=owner_globals, localns=localns, include_extras=True)
        except TypeError:
            # Python version without include_extras support
            try:
                return get_type_hints(owner, globalns=owner_globals, localns=localns)
            except Exception:
                return dict(getattr(owner, "__annotations__", {}))
        except Exception:
            # Any evaluation error (e.g., unresolved forward refs) -> fallback
            return dict(getattr(owner, "__annotations__", {}))

    @classmethod
    def _add_class(
        cls,
        c: Type[Any],
        stop_at: Type[Any],
        lines: List[str],
        seen: Set[Type[Any]],
        localns: Dict[str, Any],
    ) -> None:
        if c in seen or c is stop_at or c is object:
            return
        seen.add(c)

        # --- Enum printing (with double-quoted strings) ---
        if issubclass(c, enum.Enum):
            base_name = cls._normalize_base_name(c.__bases__[0])
            lines.append(f"class {c.__name__}({base_name}):")
            doc = cls._class_doc(c)  # or for enum: c
            if doc:
                if "\n" in doc:
                    ds = doc.splitlines()
                    lines.append(f'    """{ds[0]}')
                    for ln in ds[1:]:
                        if ln.strip():
                            lines.append("    " + ln.strip())
                        else:
                            lines.append("")
                    lines.append('    """')
                else:
                    lines.append(f'    """{doc}"""')
            for name, member in c.__members__.items():
                val = member.value
                if isinstance(val, str):
                    val_out = '"' + val.replace('"', '\\"') + '"'
                else:
                    val_out = repr(val)
                lines.append(f"    {name} = {val_out}")
            lines.append("")
            return

        # header
        base_name = cls._display_base_name(c, stop_at)
        lines.append(f"class {c.__name__}({base_name}):")

        # docstring
        doc = cls._class_doc(c)  # or for enum: c
        if doc:
            if "\n" in doc:
                ds = doc.splitlines()
                lines.append(f'    """{ds[0]}')
                for ln in ds[1:]:
                    if ln.strip():
                        lines.append("    " + ln.strip())
                    else:
                        lines.append("")
                lines.append('    """')
            else:
                lines.append(f'    """{doc}"""')
        # fields declared directly on this class
        own_names: List[str] = cls._field_names_declared_on(c)
        # fields declared on bases that are NOT content bases
        base_field_pairs = cls._field_names_from_noncontent_bases(c, stop_at)

        # Build list of (owner, field_name)
        ordered_fields: List[Tuple[Type[Any], str]] = [(c, n) for n in own_names]
        ordered_fields.extend(base_field_pairs)

        referenced: Set[Type[Any]] = set()

        if not ordered_fields:
            lines.append("    # No fields")
        else:
            for owner, name in ordered_fields:
                owner_hints = cls._get_hints(owner, localns=localns)
                tp = owner_hints.get(name, Any)

                # description via owner's model_fields (Pydantic v2)
                desc = None
                mf = getattr(owner, "model_fields", None)
                if mf and name in mf:
                    desc = getattr(mf[name], "description", None)

                pretty = cls.pretty_type(tp)
                lines.append(f"    {name}: {pretty}" + (f"  # {desc}" if desc else ""))

                referenced |= cls.extract_model_types(tp)

        lines.append("")  # blank line after each class

        # recurse into referenced classes (deterministic order)
        for r in sorted(referenced, key=lambda t: t.__name__):
            if cls.is_renderable_type(r) and r is not stop_at and r not in seen:
                cls._add_class(r, stop_at, lines, seen, localns)

    @classmethod
    def render_model(cls, model_cls: Type[Any], stop_at: Type[Any]) -> str:
        """Return a printable string describing `model_cls` and its referenced types."""
        # Capture caller locals to resolve forward refs defined in test/local scopes
        localns: Dict[str, Any] = {}
        current_frame = inspect.currentframe()
        if current_frame is not None:
            caller_frame = current_frame.f_back
            if caller_frame is not None:
                localns = dict(caller_frame.f_locals)

        lines: List[str] = []
        seen: Set[Type[Any]] = set()
        cls._add_class(model_cls, stop_at, lines, seen, localns)
        return "\n".join(lines).rstrip()
