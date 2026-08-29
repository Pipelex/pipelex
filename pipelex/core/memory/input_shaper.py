"""Signature-driven input shaping (Smart Inputs).

The ``InputShaper`` interprets each provided input *top-down against the pipe's declared
signature* instead of bottom-up from the value's shape alone. A bare string becomes the declared
concept (a ``legal.Question``, not ``native.Text``); a bare number satisfies a ``Number``-refining
input; a bare dict validates against a structured concept; a JSON list shapes element-wise into
``ListContent[declared]``; the ``{"concept", "content"}`` envelope stays as a compat-checked escape
hatch.

This module is the top-down *dispatch*: the actual content building reuses the existing primitives
(``StuffContentFactory`` / ``ConceptLibrary.is_compatible`` / the bottom-up ``StuffFactory``). The
new code decides which arm each value takes; it does not invent new content builders.

See ``wip/inputs/smart-inputs-design.md`` (D1-D11) for the full rationale.
"""

import datetime
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from mthds.protocol.pipeline_inputs import PipelineInputs, StuffContentOrData
from pydantic import ValidationError

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.exceptions import (
    ExplicitConceptIncompatibleError,
    ListWhereSingularError,
    MultiplicityCountMismatchError,
    NullInputError,
    StructureValidationError,
    UnknownInputNameError,
    WrongScalarKindError,
)
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, fixed_item_count, is_multiple_multiplicity
from pipelex.core.stuffs.exceptions import StuffContentFactoryError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import DictStuff, Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.tools.uri.uri_resolver import resolve_local_path_reference


class InputKind(StrEnum):
    """Which interpretation arm a declared input concept takes (D5).

    Resolved once per input from the *declared concept's* nature. ``DYNAMIC`` is the bottom-up
    fallback used for ``Dynamic`` / ``Anything`` and the out-of-matrix natives (Html, JSON, Page,
    TextAndImages, SearchResult, Composite) — the signature genuinely does not know how to shape
    them, so today's shape-driven ``StuffFactory`` path handles the whole value.
    """

    TEXT = "text"
    NUMBER = "number"
    YES_NO = "yes_no"
    DATE = "date"
    TIME = "time"
    IMAGE = "image"
    DOCUMENT = "document"
    STRUCTURED = "structured"
    DYNAMIC = "dynamic"

    @property
    def is_structured(self) -> bool:
        """Whether this kind dispatches values top-down against a structured (non-native) concept."""
        match self:
            case InputKind.STRUCTURED:
                return True
            case (
                InputKind.TEXT
                | InputKind.NUMBER
                | InputKind.YES_NO
                | InputKind.DATE
                | InputKind.TIME
                | InputKind.IMAGE
                | InputKind.DOCUMENT
                | InputKind.DYNAMIC
            ):
                return False


class InputShaper:
    """Turn a caller's provided inputs into a ``WorkingMemory``, interpreted against the signature."""

    @classmethod
    def shape(
        cls,
        pipeline_inputs: PipelineInputs,
        *,
        concept_provider: ConceptProviderAbstract,
        input_specs: InputStuffSpecs,
        search_scope: str | None = None,
        inputs_base_dir: Path | None = None,
    ) -> WorkingMemory:
        """Shape every provided input against its declared ``StuffSpec`` and return a WorkingMemory.

        Args:
            pipeline_inputs: The caller-provided inputs (name -> value/envelope/object).
            concept_provider: Resolves concepts and answers compatibility questions. Injected rather
                than looked up so this module stays out of the method interpreter's import closure
                (see hub-layering); the caller holds the loaded method's library.
            input_specs: The entry pipe's declared inputs (name -> StuffSpec).
            search_scope: The entry pipe's own scope (its domain, `alias->domain` for a dependency
                entry pipe), preferred when resolving a bare envelope/object concept code.
            inputs_base_dir: Directory that bare *relative local* file paths resolve against (D3) —
                the inputs file's parent when the inputs were loaded from a file (threaded from the
                CLI). ``None`` (in-process / inline-JSON callers) leaves relative paths untouched
                (the CWD contract). Only bare strings in the file-ish and CSV arms are resolved; the
                ``{"url": ...}`` dict form is owned by the CLI's url-key walk.

        Raises:
            UnknownInputNameError: a provided name is not declared (D8).
            InputShapingError subclasses: a provided value cannot be shaped (D4).
        """
        cls._check_input_names(pipeline_inputs, input_specs=input_specs)
        working_memory = WorkingMemory(root={})
        for variable_name, value in pipeline_inputs.items():
            stuff_spec = input_specs.get_required_stuff_spec(variable_name=variable_name)
            stuff = cls._shape_one(
                value,
                concept_provider=concept_provider,
                stuff_spec=stuff_spec,
                variable_name=variable_name,
                search_scope=search_scope,
                inputs_base_dir=inputs_base_dir,
            )
            working_memory.add_new_stuff(name=variable_name, stuff=stuff)
        return working_memory

    @classmethod
    def _check_input_names(cls, pipeline_inputs: PipelineInputs, *, input_specs: InputStuffSpecs) -> None:
        """Reject any provided name absent from the signature, up front (D8)."""
        declared_names = input_specs.declared_names
        declared_set = set(declared_names)
        for variable_name in pipeline_inputs:
            if variable_name not in declared_set:
                raise UnknownInputNameError.make(variable_name=variable_name, declared_names=declared_names)

    @classmethod
    def _shape_one(
        cls,
        value: Any,
        *,
        concept_provider: ConceptProviderAbstract,
        stuff_spec: StuffSpec,
        variable_name: str,
        search_scope: str | None,
        inputs_base_dir: Path | None,
    ) -> Stuff:
        declared_concept = stuff_spec.concept

        # (D6) Explicit forms — a {"concept", "content"} envelope, a DictStuff, or a directly-provided
        # StuffContent/ListContent object — build bottom-up as today, then get compat-checked.
        if cls._is_explicit(value):
            return cls._shape_explicit(
                value,
                concept_provider=concept_provider,
                declared_concept=declared_concept,
                stuff_spec=stuff_spec,
                variable_name=variable_name,
                search_scope=search_scope,
            )

        # (D9) A top-level null is never a value — absence is expressed by omitting the key.
        if value is None:
            raise NullInputError.make(
                variable_name=variable_name,
                declared_concept_ref=declared_concept.concept_ref,
                expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
            )

        # (D5) Bare value: dispatch on the declared concept's nature.
        input_kind = cls.resolve_input_kind(declared_concept, concept_provider=concept_provider)
        match input_kind:
            case InputKind.DYNAMIC:
                # The signature genuinely does not know how to shape this — hand the whole raw value
                # to the bottom-up factory (today's behavior, including its own list handling).
                return StuffFactory.make_stuff_from_stuff_content_or_data(
                    stuff_content_or_data=value,
                    concept_provider=concept_provider,
                    name=variable_name,
                    search_scope=search_scope,
                )
            case (
                InputKind.TEXT
                | InputKind.NUMBER
                | InputKind.YES_NO
                | InputKind.DATE
                | InputKind.TIME
                | InputKind.IMAGE
                | InputKind.DOCUMENT
                | InputKind.STRUCTURED
            ):
                content = cls._shape_with_multiplicity(
                    value,
                    concept_provider=concept_provider,
                    stuff_spec=stuff_spec,
                    input_kind=input_kind,
                    variable_name=variable_name,
                    search_scope=search_scope,
                    inputs_base_dir=inputs_base_dir,
                )
                return StuffFactory.make_stuff(concept=declared_concept, content=content, name=variable_name)

    @classmethod
    def resolve_input_kind(cls, concept: Concept, *, concept_provider: ConceptProviderAbstract) -> InputKind:
        """Map a declared concept to its interpretation arm via ordered strict-compatibility checks (D5).

        ``strict=True`` means refinement / structural-equivalence only — a concept refining ``Number``
        matches ``NUMBER`` but an unrelated concept that merely shares a field does not.
        """
        if NativeConceptCode.is_dynamic_concept(concept_code=concept.code):
            return InputKind.DYNAMIC

        ordered_natives: list[tuple[NativeConceptCode, InputKind]] = [
            (NativeConceptCode.YES_NO, InputKind.YES_NO),
            (NativeConceptCode.DATE, InputKind.DATE),
            (NativeConceptCode.TIME, InputKind.TIME),
            (NativeConceptCode.NUMBER, InputKind.NUMBER),
            (NativeConceptCode.IMAGE, InputKind.IMAGE),
            (NativeConceptCode.DOCUMENT, InputKind.DOCUMENT),
            (NativeConceptCode.TEXT, InputKind.TEXT),
        ]
        for native_code, input_kind in ordered_natives:
            wanted_concept = concept_provider.get_native_concept(native_concept=native_code)
            if concept_provider.is_compatible(tested_concept=concept, wanted_concept=wanted_concept, strict=True):
                return input_kind

        # A user (non-native) concept whose structure is StructuredContent dispatches its dict
        # top-down. Everything else — the out-of-matrix natives (Html/JSON/Page/TextAndImages/
        # SearchResult/Composite/Anything) — falls back to bottom-up building.
        if not Concept.is_native_concept(concept=concept):
            if issubclass(concept_provider.get_structure_class(concept=concept), StructuredContent):
                return InputKind.STRUCTURED
        return InputKind.DYNAMIC

    @classmethod
    def _peel_multiplicity(cls, multiplicity: VariableMultiplicity | None) -> tuple[bool, int | None]:
        """Peel a declared multiplicity into ``(is_list, fixed_count)`` (D2).

        Both halves are the shared projection, not a local re-derivation: ``[]`` is a variable list,
        ``[N]`` for ``N >= 2`` a fixed-count list carrying its count, and ``None`` — like ``[1]``, which
        is the single form with its count written out — is singular. Deriving it here again is exactly
        how this function once came to frame a ``[1]`` slot as a one-item list while the contract, the
        schema and the descriptor beside it all ruled it single.
        """
        return is_multiple_multiplicity(multiplicity=multiplicity), fixed_item_count(multiplicity=multiplicity)

    @classmethod
    def _shape_with_multiplicity(
        cls,
        value: Any,
        *,
        concept_provider: ConceptProviderAbstract,
        stuff_spec: StuffSpec,
        input_kind: InputKind,
        variable_name: str,
        search_scope: str | None,
        inputs_base_dir: Path | None,
    ) -> StuffContent:
        """Peel the declared multiplicity (D2), then build the item content(s)."""
        is_list, fixed_count = cls._peel_multiplicity(stuff_spec.multiplicity)

        # (D11) A declared structured LIST input accepts a table reference — a bare tabular path
        # string or the exact {"url": <tabular path>} wrapper — read row-wise into the declared
        # concept, tried BEFORE element-wise shaping so the bare string is not misread as one item.
        if is_list and input_kind.is_structured:
            csv_list_content = cls._try_shape_csv(
                value, concept_provider=concept_provider, stuff_spec=stuff_spec, variable_name=variable_name, inputs_base_dir=inputs_base_dir
            )
            if csv_list_content is not None:
                if fixed_count is not None and len(csv_list_content.items) != fixed_count:
                    raise MultiplicityCountMismatchError.make(
                        variable_name=variable_name,
                        declared_concept_ref=stuff_spec.concept.concept_ref,
                        expected_count=fixed_count,
                        provided_count=len(csv_list_content.items),
                        expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
                    )
                return csv_list_content

        if is_list:
            return cls._shape_list(
                value,
                concept_provider=concept_provider,
                stuff_spec=stuff_spec,
                input_kind=input_kind,
                variable_name=variable_name,
                fixed_count=fixed_count,
                search_scope=search_scope,
                inputs_base_dir=inputs_base_dir,
            )

        # Singular (no multiplicity, or a count of one). A list here is ambiguous — hard error (D2).
        if isinstance(value, list):
            raise ListWhereSingularError.make(
                variable_name=variable_name,
                declared_concept_ref=stuff_spec.concept.concept_ref,
                provided_description=cls._describe_value(value),
                expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
            )
        return cls._build_item_content(
            value,
            concept_provider=concept_provider,
            input_kind=input_kind,
            stuff_spec=stuff_spec,
            variable_name=variable_name,
            search_scope=search_scope,
            inputs_base_dir=inputs_base_dir,
        )

    @classmethod
    def _try_shape_csv(
        cls,
        value: Any,
        *,
        concept_provider: ConceptProviderAbstract,
        stuff_spec: StuffSpec,
        variable_name: str,
        inputs_base_dir: Path | None,
    ) -> ListContent[StuffContent] | None:
        """Detect and read a table reference for a declared structured list input (D11).

        Only a bare string or the exact single-key ``{"url": <str>}`` wrapper is a candidate; the
        tabular-suffix / local-only gates live in ``StuffFactory.try_make_csv_list_content``, which
        returns ``None`` for a non-tabular reference so the caller falls through to normal
        element-wise shaping (a record dict with sibling keys stays a record). A bare relative
        path resolves against ``inputs_base_dir`` first, like the file-ish arm (D3).
        """
        url: str
        if isinstance(value, str):
            url = value
        elif isinstance(value, dict):
            value_dict = cast("dict[Any, Any]", value)
            url_candidate = value_dict.get("url")
            if set(value_dict.keys()) != {"url"} or not isinstance(url_candidate, str):
                return None
            url = url_candidate
        else:
            return None
        url = cls._resolve_local_path(url, inputs_base_dir=inputs_base_dir)
        return StuffFactory.try_make_csv_list_content(stuff_spec.concept, concept_provider=concept_provider, content={"url": url}, name=variable_name)

    @classmethod
    def _resolve_local_path(cls, url: str, *, inputs_base_dir: Path | None) -> str:
        """Resolve a bare local path against the inputs file's directory (D3).

        A leading ``~`` expands to the user's home first (so ``~/photo.jpg`` is an absolute home
        path, never joined onto ``inputs_base_dir``); a still-relative path then resolves against the
        base dir. Shared with the CLI's url-key walk via ``resolve_local_path_reference``.
        """
        return resolve_local_path_reference(url, base_dir=inputs_base_dir)

    @classmethod
    def _shape_list(
        cls,
        value: Any,
        *,
        concept_provider: ConceptProviderAbstract,
        stuff_spec: StuffSpec,
        input_kind: InputKind,
        variable_name: str,
        fixed_count: int | None,
        search_scope: str | None,
        inputs_base_dir: Path | None,
    ) -> ListContent[StuffContent]:
        """Shape a declared-multiple input element-wise into a ListContent (D2)."""
        # A single bare value auto-wraps into a one-item list; an empty list stays empty (legal).
        item_values: list[Any] = cast("list[Any]", value) if isinstance(value, list) else [value]
        if fixed_count is not None and len(item_values) != fixed_count:
            raise MultiplicityCountMismatchError.make(
                variable_name=variable_name,
                declared_concept_ref=stuff_spec.concept.concept_ref,
                expected_count=fixed_count,
                provided_count=len(item_values),
                expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
            )
        items = [
            cls._build_item_content(
                item_value,
                concept_provider=concept_provider,
                input_kind=input_kind,
                stuff_spec=stuff_spec,
                variable_name=variable_name,
                search_scope=search_scope,
                inputs_base_dir=inputs_base_dir,
            )
            for item_value in item_values
        ]
        return ListContent(items=items)

    @classmethod
    def _build_item_content(
        cls,
        value: Any,
        *,
        concept_provider: ConceptProviderAbstract,
        input_kind: InputKind,
        stuff_spec: StuffSpec,
        variable_name: str,
        search_scope: str | None,
        inputs_base_dir: Path | None,
    ) -> StuffContent:
        """Build one item's ``StuffContent`` from a value, dispatched on the declared kind (D5).

        A list item that is itself an already-built ``StuffContent`` keeps today's behavior — it is
        built bottom-up (its concept inferred from its class) and D6-compat-checked against the
        declared item concept — so a ``list[StuffContent]`` (e.g. ``[Question(...), Question(...)]``)
        shapes just like the wrapped ``ListContent`` object form. Every other item is a bare value:
        each arm converts it into the canonical shape the declared concept's structure class expects,
        then delegates to ``StuffContentFactory`` so a refining subclass is honored.
        """
        concept = stuff_spec.concept
        if isinstance(value, StuffContent):
            built = StuffFactory.make_stuff_from_stuff_content_or_data(
                stuff_content_or_data=value, concept_provider=concept_provider, name=variable_name, search_scope=search_scope
            )
            if not concept_provider.is_compatible(tested_concept=built.concept, wanted_concept=concept):
                raise ExplicitConceptIncompatibleError.make(
                    variable_name=variable_name,
                    declared_concept_ref=concept.concept_ref,
                    provided_concept_ref=built.concept.concept_ref,
                    expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
                )
            return built.content
        match input_kind:
            case InputKind.TEXT:
                if not isinstance(value, str):
                    raise cls._wrong_kind(
                        concept_provider=concept_provider,
                        stuff_spec=stuff_spec,
                        variable_name=variable_name,
                        expected_kind="a string (text)",
                        value=value,
                    )
                return cls._make_content(
                    concept, concept_provider=concept_provider, value={"text": value}, stuff_spec=stuff_spec, variable_name=variable_name
                )
            case InputKind.NUMBER:
                # bool is a subclass of int — exclude it explicitly so a boolean never becomes a number.
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise cls._wrong_kind(
                        concept_provider=concept_provider, stuff_spec=stuff_spec, variable_name=variable_name, expected_kind="a number", value=value
                    )
                return cls._make_content(
                    concept, concept_provider=concept_provider, value={"number": value}, stuff_spec=stuff_spec, variable_name=variable_name
                )
            case InputKind.YES_NO:
                if not isinstance(value, bool):
                    raise cls._wrong_kind(
                        concept_provider=concept_provider,
                        stuff_spec=stuff_spec,
                        variable_name=variable_name,
                        expected_kind="a boolean (true/false)",
                        value=value,
                    )
                return cls._make_content(concept, concept_provider=concept_provider, value=value, stuff_spec=stuff_spec, variable_name=variable_name)
            case InputKind.DATE:
                if not isinstance(value, (datetime.date, str)):
                    raise cls._wrong_kind(
                        concept_provider=concept_provider,
                        stuff_spec=stuff_spec,
                        variable_name=variable_name,
                        expected_kind="an ISO date/datetime string or a date object",
                        value=value,
                    )
                return cls._make_content(concept, concept_provider=concept_provider, value=value, stuff_spec=stuff_spec, variable_name=variable_name)
            case InputKind.TIME:
                if not isinstance(value, (datetime.time, str)):
                    raise cls._wrong_kind(
                        concept_provider=concept_provider,
                        stuff_spec=stuff_spec,
                        variable_name=variable_name,
                        expected_kind="an ISO time-of-day string or a time object",
                        value=value,
                    )
                return cls._make_content(concept, concept_provider=concept_provider, value=value, stuff_spec=stuff_spec, variable_name=variable_name)
            case InputKind.IMAGE | InputKind.DOCUMENT:
                canonical: dict[str, Any]
                if isinstance(value, str):
                    # (D3) A bare relative local path resolves against the inputs file's directory;
                    # the {"url": ...} dict form is left to the CLI's signature-blind url-key walk.
                    canonical = {"url": cls._resolve_local_path(value, inputs_base_dir=inputs_base_dir)}
                elif isinstance(value, dict):
                    canonical = cast("dict[str, Any]", value)
                else:
                    raise cls._wrong_kind(
                        concept_provider=concept_provider,
                        stuff_spec=stuff_spec,
                        variable_name=variable_name,
                        expected_kind='a URL/path string or a {"url": ...} object',
                        value=value,
                    )
                return cls._make_content(
                    concept, concept_provider=concept_provider, value=canonical, stuff_spec=stuff_spec, variable_name=variable_name
                )
            case InputKind.STRUCTURED:
                if not isinstance(value, dict):
                    raise cls._wrong_kind(
                        concept_provider=concept_provider,
                        stuff_spec=stuff_spec,
                        variable_name=variable_name,
                        expected_kind="an object (structured value)",
                        value=value,
                    )
                return cls._make_content(
                    concept,
                    concept_provider=concept_provider,
                    value=cast("dict[str, Any]", value),
                    stuff_spec=stuff_spec,
                    variable_name=variable_name,
                )
            case InputKind.DYNAMIC:
                # Unreachable: DYNAMIC short-circuits in `_shape_one` before multiplicity peeling.
                # Kept so the match over InputKind stays exhaustive.
                msg = f"Input '{variable_name}': DYNAMIC kind must be handled by the bottom-up fallback, not per-item shaping."
                raise PipelexUnexpectedError(msg)

    @classmethod
    def _make_content(
        cls,
        concept: Concept,
        *,
        concept_provider: ConceptProviderAbstract,
        value: dict[str, Any] | str | bool | datetime.date | datetime.time,
        stuff_spec: StuffSpec,
        variable_name: str,
    ) -> StuffContent:
        """Delegate to ``StuffContentFactory``, wrapping a build failure as a D4 structure error.

        The structure class is resolved through the **injected provider**, then handed down as a
        resolved type — the shape ``hub-layering.md`` prescribes for exactly this ("rendering takes
        the resolved class, not the name"), and the one ``StuffSpec.render_stuff_spec`` already
        follows. The registry-resolving overload
        (``make_stuff_content_from_concept_required``) stays for the bottom-up callers that hold no
        provider; a caller that *has* one must not reach past it into ambient state, which is what
        the provider parameter exists to avoid.

        Two things follow, and neither is incidental. A shaper that resolved names from the process
        registry could not run without a loaded library at all — the registry is empty outside a
        booted process, so `shape_inputs` was un-callable by any programmatic caller that built its
        own provider, despite taking one explicitly for that purpose. And a name that should have
        resolved and did not now raises ``ConceptStructureClassNotFoundError`` (uncaught here,
        deliberately) rather than arriving as a ``StructureValidationError``: an unresolvable
        declared class is not a malformed *value*, and reporting it as one pointed the author at
        their input instead of at the concept.
        """
        try:
            return StuffContentFactory.make_content_from_value(
                stuff_content_subclass=concept_provider.get_structure_class(concept=concept),
                value=value,
            )
        except (ValidationError, StuffContentFactoryError) as exc:
            raise StructureValidationError.make(
                variable_name=variable_name,
                declared_concept_ref=concept.concept_ref,
                reason=str(exc),
                expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
            ) from exc

    @classmethod
    def _shape_explicit(
        cls,
        value: Any,
        *,
        concept_provider: ConceptProviderAbstract,
        declared_concept: Concept,
        stuff_spec: StuffSpec,
        variable_name: str,
        search_scope: str | None,
    ) -> Stuff:
        """Build an explicit form bottom-up, then compat-check the built concept against declared (D6).

        The envelope ``{"concept": C, "content": ...}``, a ``DictStuff``, and a directly-provided
        ``StuffContent``/``ListContent`` all name (or infer) their own concept. ``StuffFactory`` builds
        them exactly as today — so the explicit, possibly more-specific concept is preserved — and the
        one new rule is: that concept must be compatible with the declared one, else a D4 error.
        """
        stuff = StuffFactory.make_stuff_from_stuff_content_or_data(
            stuff_content_or_data=cast("StuffContentOrData", value),
            concept_provider=concept_provider,
            name=variable_name,
            search_scope=search_scope,
        )
        if not concept_provider.is_compatible(tested_concept=stuff.concept, wanted_concept=declared_concept):
            raise ExplicitConceptIncompatibleError.make(
                variable_name=variable_name,
                declared_concept_ref=declared_concept.concept_ref,
                provided_concept_ref=stuff.concept.concept_ref,
                expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
            )
        if NativeConceptCode.is_dynamic_concept(concept_code=declared_concept.code):
            # Match the bare-value Dynamic path: the signature cannot guide list-vs-single shape here.
            return stuff
        cls._reconcile_explicit_multiplicity(stuff, concept_provider=concept_provider, stuff_spec=stuff_spec, variable_name=variable_name)
        return stuff

    @classmethod
    def _reconcile_explicit_multiplicity(
        cls, stuff: Stuff, *, concept_provider: ConceptProviderAbstract, stuff_spec: StuffSpec, variable_name: str
    ) -> None:
        """Enforce the unambiguous D2 shape rules on an explicit form (D6 governs only its concept).

        An explicit form whose built content is a ``ListContent`` must not fill a singular slot, and must
        match a declared fixed count — the same list-vs-singular and ``[N]``-count rules the bare-value
        path enforces in ``_shape_with_multiplicity``. Without this, a caller handing an explicit
        ``ListContent`` (or an envelope whose ``content`` is a list) to a singular-declared input would
        have it *silently* stored into the singular slot. The singular-under-``[]`` auto-wrap question is
        deliberately left to the caller's literal form (see ``wip/inputs/input-shaper-multiplicity-gaps.md``):
        an explicit singular is taken as given, not auto-wrapped.
        """
        content = stuff.content
        if not isinstance(content, ListContent):
            return
        list_content = cast("ListContent[StuffContent]", content)
        is_list, fixed_count = cls._peel_multiplicity(stuff_spec.multiplicity)
        if not is_list:
            raise ListWhereSingularError.make(
                variable_name=variable_name,
                declared_concept_ref=stuff_spec.concept.concept_ref,
                provided_description=f"a list of {len(list_content.items)} item(s)",
                expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
            )
        if fixed_count is not None and len(list_content.items) != fixed_count:
            raise MultiplicityCountMismatchError.make(
                variable_name=variable_name,
                declared_concept_ref=stuff_spec.concept.concept_ref,
                expected_count=fixed_count,
                provided_count=len(list_content.items),
                expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
            )

    @classmethod
    def _is_explicit(cls, value: Any) -> bool:
        """Whether a value is an explicit form: a ``{"concept", "content"}`` envelope, a ``DictStuff``,
        or an already-built ``StuffContent``/``ListContent`` object (D6).

        A dict whose keys are *exactly* ``{"concept", "content"}`` is always read as an envelope — even
        if a declared structured concept happens to have fields by those names (the deterministic
        collision rule; the escape hatch for that pathological structure is a nested envelope).
        """
        if isinstance(value, (DictStuff, StuffContent)):
            return True
        return isinstance(value, dict) and set(cast("dict[Any, Any]", value).keys()) == {"concept", "content"}

    @classmethod
    def _wrong_kind(
        cls, *, concept_provider: ConceptProviderAbstract, stuff_spec: StuffSpec, variable_name: str, expected_kind: str, value: Any
    ) -> WrongScalarKindError:
        return WrongScalarKindError.make(
            variable_name=variable_name,
            declared_concept_ref=stuff_spec.concept.concept_ref,
            expected_kind=expected_kind,
            provided_description=cls._describe_value(value),
            expected_shape=cls._render_expected_shape(concept_provider=concept_provider, stuff_spec=stuff_spec),
        )

    @classmethod
    def _render_expected_shape(cls, *, concept_provider: ConceptProviderAbstract, stuff_spec: StuffSpec) -> str:
        """Render the expected input shape from the signature, reused verbatim in D4 error hints."""
        rendered = stuff_spec.render_stuff_spec(concept_provider=concept_provider, output_format=ConceptRepresentationFormat.JSON)
        return json.dumps(rendered, ensure_ascii=False)

    @classmethod
    def _describe_value(cls, value: Any) -> str:
        """A short human description of a provided value, for error messages."""
        # bool before int: bool is a subclass of int.
        if value is None:
            return "null"
        if isinstance(value, bool):
            return f"a boolean ({str(value).lower()})"
        if isinstance(value, str):
            return f'a string ("{value[:40]}")'
        if isinstance(value, (int, float)):
            return f"a number ({value})"
        if isinstance(value, list):
            return f"a list of {len(cast('list[Any]', value))} item(s)"
        if isinstance(value, dict):
            keys = sorted(str(key) for key in cast("dict[Any, Any]", value))
            return f"an object with keys [{', '.join(keys)}]"
        return f"a value of type {type(value).__name__}"
