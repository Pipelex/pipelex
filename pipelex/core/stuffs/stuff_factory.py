import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import shortuuid
from mthds.protocol.pipeline_inputs import StuffContentOrData
from pydantic import BaseModel, ValidationError, field_validator

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptValueError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.validation import validate_concept_ref
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import DictStuff, Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry, get_concept_library, get_native_concept, get_required_concept
from pipelex.libraries.concept.concept_library import ConceptLibraryConceptNotFoundError
from pipelex.tools.tabular.csv_codec import is_tabular_path, list_content_from_csv
from pipelex.tools.tabular.exceptions import CsvError
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.tools.uri.resolved_uri import ResolvedLocalPath
from pipelex.tools.uri.uri_resolver import resolve_uri


class StuffBlueprint(BaseModel):
    stuff_name: str
    concept_ref: str
    content: dict[str, Any] | str

    @field_validator("concept_ref")
    @classmethod
    def validate_concept_ref_field(cls, concept_ref: str) -> str:
        validate_concept_ref(concept_ref)
        return concept_ref


class StuffFactory:
    @classmethod
    def make_stuff_code(cls) -> str:
        return shortuuid.uuid()[:5]

    @classmethod
    def make_stuff_name(cls, concept: Concept) -> str:
        return Stuff.make_stuff_name(concept=concept)

    @classmethod
    def make_from_str(cls, str_value: str, *, name: str) -> Stuff:
        return cls.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text=str_value),
            name=name,
        )

    @classmethod
    def make_from_concept_ref(cls, concept_ref: str, *, name: str, content: StuffContent) -> Stuff:
        validate_concept_ref(concept_ref)
        concept = get_required_concept(concept_ref=concept_ref)
        return cls.make_stuff(
            concept=concept,
            content=content,
            name=name,
        )

    @classmethod
    def make_stuff(
        cls,
        concept: Concept,
        *,
        content: StuffContent,
        name: str | None = None,
        code: str | None = None,
    ) -> Stuff:
        if not code:
            code = cls.make_stuff_code()

        if not name:
            name = cls.make_stuff_name(concept=concept)

        return Stuff(
            concept=concept,
            content=content,
            stuff_name=name,
            stuff_code=code,
        )

    @classmethod
    def make_from_blueprint(cls, blueprint: StuffBlueprint) -> "Stuff":
        concept_library = get_concept_library()
        if isinstance(blueprint.content, str) and concept_library.is_compatible(
            tested_concept=concept_library.get_required_concept(concept_ref=blueprint.concept_ref),
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
        ):
            the_stuff = cls.make_stuff(
                concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
                content=TextContent(text=blueprint.content),
                name=blueprint.stuff_name,
            )
        else:
            the_stuff_content = StuffContentFactory.make_stuff_content_from_concept_required(
                concept=concept_library.get_required_concept(concept_ref=blueprint.concept_ref),
                value=blueprint.content,
            )
            the_stuff = cls.make_stuff(
                concept=concept_library.get_required_concept(concept_ref=blueprint.concept_ref),
                content=the_stuff_content,
                name=blueprint.stuff_name,
            )
        return the_stuff

    @classmethod
    def combine_stuffs(
        cls,
        stuff_contents: dict[str, StuffContent],
        *,
        concept: Concept,
        name: str | None = None,
        code: str | None = None,
    ) -> Stuff:
        """Combine a dictionary of stuffs into a single stuff."""
        the_subclass = get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)
        try:
            the_stuff_content = the_subclass.model_validate(obj=stuff_contents)
        except ValidationError as exc:
            msg = f"Error combining stuffs for concept {concept.code}, stuff named `{name}`: {format_pydantic_validation_error(exc=exc)}"
            raise StuffFactoryError(msg) from exc
        return cls.make_stuff(
            concept=concept,
            content=the_stuff_content,
            name=name,
            code=code,
        )

    @classmethod
    def _try_make_csv_list_stuff(
        cls,
        concept: Concept,
        *,
        content: dict[str, Any],
        name: str | None,
        code: str | None,
    ) -> Stuff | None:
        """Wrap :meth:`try_make_csv_list_content` into a ``Stuff`` (Case 2.5 envelope path)."""
        list_content = cls.try_make_csv_list_content(concept, content=content, name=name)
        if list_content is None:
            return None
        return cls.make_stuff(concept=concept, content=list_content, name=name, code=code)

    @classmethod
    def try_make_csv_list_content(
        cls,
        concept: Concept,
        *,
        content: dict[str, Any],
        name: str | None,
    ) -> ListContent[StuffContent] | None:
        """Build a ``ListContent[row-concept]`` from a ``{"url": "...csv"}`` input reference.

        Detection is gated to the explicit wrapper shape — ``content`` must be *exactly*
        ``{"url": <tabular path>}`` — under a non-native structured concept. Each data row then
        becomes one instance of the concept's structure class, so one CSV yields one
        ``ListContent`` (the concept names the *row* type). Returns ``None`` for an ordinary
        record dict — no ``url`` key, sibling keys alongside ``url``, a non-tabular suffix, or a
        native concept — so the caller falls through to normal dict handling. The single-key gate
        keeps a real record that merely *has* a ``url`` field (e.g. ``{"label": "Home", "url":
        "report.csv"}``) from being silently reduced to a table with its sibling keys dropped.

        Shared by the bottom-up factory (Case 2.5 envelope) and the top-down ``InputShaper``
        (a bare tabular path / bare ``{"url": ...}`` under a declared structured list, Smart Inputs
        D11). The shaper resolves a relative path against the inputs-file dir before calling in, so
        this method's own gates operate on an already-resolved url.

        v1 reads LOCAL paths only: a tabular-suffixed remote ``url`` (``http(s)``/``s3``/``gs``/
        ``pipelex-storage``) is rejected with a clear ``CsvError`` rather than opened as a local path.
        (A base64 data URL carries no file suffix, so it is never detected as tabular and simply
        falls through to ordinary record handling.)
        """
        url = content.get("url")
        if not isinstance(url, str):
            return None
        if set(content) != {"url"}:
            # Only the bare {"url": ...} wrapper is a table reference; a record with other keys
            # alongside `url` stays a record (its siblings must not be dropped).
            return None
        if Concept.is_native_concept(concept=concept):
            # Native file concepts (Image, PDF, ...) own their own url handling; never hijack them.
            # Checked BEFORE url parsing so a native concept never raises a CSV-flavored error.
            return None
        # Parse the URL once, up front. A malformed url (e.g. a bad IPv6 bracket like ``https://[``)
        # makes ``urlsplit`` itself raise ``ValueError`` — convert that to a redacted CsvError rather
        # than let it escape into a traceback that would surface the raw (possibly token-bearing) url.
        try:
            url_parts = urlsplit(url)
        except ValueError as exc:
            msg = (
                f"CSV input supports local file paths only in v1, but stuff '{name}' for concept "
                f"'{concept.concept_ref}' has a url that could not be parsed. "
                "Download the file locally and reference it by path."
            )
            raise CsvError(msg) from exc
        # Detect the tabular suffix on the URL's PATH component only. A raw URL fed to ``Path`` keeps
        # any ``?query``/``#fragment`` inside ``.suffix`` (e.g. an S3 presigned ``...csv?X-Amz-...``),
        # which would hide the ``.csv`` and let a remote ref slip past the local-only guard below.
        if not is_tabular_path(Path(url_parts.path)):
            return None

        resolved = resolve_uri(url)
        # Accept only genuine local paths. `file://` resolves to a scheme-free local path; an http(s)/
        # base64/pipelex-storage url is a non-local ResolvedUri; an `s3://`/`gs://`-style scheme slips
        # through as a ResolvedLocalPath but keeps `://` in its path, so reject those too.
        if not isinstance(resolved, ResolvedLocalPath) or "://" in resolved.path:
            # Strip query/fragment/userinfo before echoing the url: CsvError is caller-facing and
            # survives STRICT disclosure, so a signed/token-bearing url (e.g. an S3 presigned link)
            # must not leak its credentials into the message. Keep scheme/host/path to identify it.
            safe_netloc = url_parts.hostname or ""
            try:
                safe_port = url_parts.port
            except ValueError:
                # A malformed/out-of-range port makes the `.port` property raise; don't let that
                # ValueError escape (it would bypass this redaction and surface the raw url in a
                # traceback). Drop the port from the sanitized display instead.
                safe_port = None
            if safe_port is not None:
                safe_netloc = f"{safe_netloc}:{safe_port}"
            safe_url = urlunsplit((url_parts.scheme, safe_netloc, url_parts.path, "", ""))
            msg = (
                f"CSV input supports local file paths only in v1, but stuff '{name}' for concept "
                f"'{concept.concept_ref}' points at a remote/non-local url: {safe_url!r}. "
                "Download the file locally and reference it by path."
            )
            raise CsvError(msg)

        try:
            row_model = concept.get_structure_class()
        except ConceptValueError as exc:
            # Keep the codec's typed-error boundary intact: an unregistered structure class is a
            # caller-fixable input problem, not a raw ValueError that escapes into core/runner.
            msg = f"CSV input for stuff '{name}': concept '{concept.concept_ref}' has no registered structure class to read CSV rows into."
            raise CsvError(msg) from exc
        return list_content_from_csv(Path(resolved.path), row_model=row_model)

    @classmethod
    def make_stuff_from_stuff_content_or_data(
        cls,
        stuff_content_or_data: StuffContentOrData,
        *,
        name: str | None = None,
        code: str | None = None,
        search_domain_codes: list[str] | None = None,
    ) -> Stuff:
        """Create a Stuff from StuffContentOrData covering all pipeline inputs cases.

        Case 1: Direct content (no 'concept' key)
            1.1: str → TextContent with Text concept
            1.2: list[str] → ListContent[TextContent] with Text concept
            1.3: StructuredContent → Use the StructuredContent, infer concept from class name
            1.4: list[StuffContent] → ListContent[StuffContent], infer concept from first item
            1.5: ListContent[StuffContent] → Use the ListContent, infer concept from first item

        Note: StructuredContent (1.3) and ListContent (1.5) are separate cases at the same level.
              Both inherit from StuffContent but handle different content types.

        Case 2: Dict with 'concept' AND 'content' keys (can be plain dict or DictStuff instance)
            2.1/2.1b: {"concept": "Text"/"native.Text", "content": str} → TextContent with Text concept
            2.1c: {"concept": "domain.Concept", "content": str} → TextContent with that concept (if compatible)
            2.1d: {"concept": "YesNo"/"domain.Concept", "content": bool} → YesNoContent (if YesNo-compatible)
            2.1e: {"concept": "Date"/"domain.Concept", "content": date/datetime obj} → DateContent (if Date-compatible)
            2.1f: {"concept": "Date"/"domain.Concept", "content": ISO str} → DateContent (if Date-compatible, checked after Text)
            2.2/2.2b: {"concept": "...", "content": list[str]} → ListContent[TextContent]
            2.3: {"concept": "...", "content": StuffContent} → Use the StuffContent
            2.4: {"concept": "...", "content": list[StuffContent]} → ListContent[StuffContent]
            2.5: {"concept": "...", "content": dict} → Create StuffContent from dict
            2.6: {"concept": "...", "content": list[dict]} → ListContent[StuffContent] from dicts
        """
        concept_library = get_concept_library()

        # ==================== CASE 1: Direct content (no concept key) ====================
        if not isinstance(stuff_content_or_data, dict):
            # Case 1.1: str → TextContent with Text concept
            if isinstance(stuff_content_or_data, str):
                return cls.make_stuff(
                    concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
                    content=TextContent(text=stuff_content_or_data),
                    name=name,
                    code=code,
                )

            # Case 1.5: ListContent[StuffContent] → Use the ListContent, infer concept from first item
            # Must check BEFORE Case 1.3 because ListContent is also a StuffContent
            if isinstance(stuff_content_or_data, ListContent):
                list_content = cast("ListContent[StuffContent]", stuff_content_or_data)

                if len(list_content.items) == 0:
                    msg = f"Cannot create Stuff '{name}' from empty ListContent"
                    raise StuffFactoryError(msg)

                first_item = list_content.items[0]

                # Check that items are StuffContent
                if not isinstance(first_item, StuffContent):  # pyright: ignore[reportUnnecessaryIsInstance]
                    msg = (
                        f"Trying to create a Stuff '{name}' from a ListContent but "
                        f"the items are not StuffContent. First item is of type {type(first_item).__name__}. "
                        "ListContent items must be subclasses of StuffContent."
                    )
                    raise StuffFactoryError(msg)

                # Check all items are of the same type
                for item in list_content.items:
                    if not isinstance(item, type(first_item)):
                        msg = (
                            f"Trying to create a Stuff '{name}' from a ListContent of '{type(first_item).__name__}' "
                            f"but the items are not of the same type. Especially, items {item} is of type {type(item).__name__}. "
                            "Every items of the list should be an identical type."
                        )
                        raise StuffFactoryError(msg)

                # Get concept from first item's class name
                content_class_name = type(first_item).__name__

                # Check if it's a native concept
                if "Content" in content_class_name and NativeConceptCode.is_native_concept_ref_or_code(
                    concept_ref_or_code=content_class_name.split("Content")[0]
                ):
                    concept = get_native_concept(native_concept=NativeConceptCode(content_class_name.split("Content")[0]))
                else:
                    try:
                        concept = concept_library.get_required_concept_from_concept_ref_or_code(
                            concept_ref_or_code=content_class_name, search_domain_codes=search_domain_codes
                        )
                    except ConceptLibraryConceptNotFoundError as exc:
                        msg = (
                            f"Trying to create a Stuff '{name}' from a ListContent but "
                            f"the concept of name '{content_class_name}' is not found in the library"
                        )
                        raise StuffFactoryError(msg) from exc

                return cls.make_stuff(
                    concept=concept,
                    content=list_content,
                    name=name,
                    code=code,
                )

            # Case 1.3: StuffContent object (includes both native and StructuredContent) → Infer concept from class name
            if isinstance(stuff_content_or_data, StuffContent):
                stuff_content = stuff_content_or_data
                content_class_name = stuff_content_or_data.__class__.__name__

                # Check if it's a native concept
                if "Content" in content_class_name and NativeConceptCode.is_native_concept_ref_or_code(
                    concept_ref_or_code=content_class_name.split("Content")[0]
                ):
                    # It's a native concept like TextContent, ImageContent, etc.
                    concept = get_native_concept(native_concept=NativeConceptCode(content_class_name.split("Content")[0]))
                else:
                    # It's a StructuredContent, try to find the concept
                    try:
                        concept = concept_library.get_required_concept_from_concept_ref_or_code(
                            concept_ref_or_code=content_class_name, search_domain_codes=search_domain_codes
                        )
                    except ConceptLibraryConceptNotFoundError as exc:
                        msg = (
                            f"Trying to create a Stuff '{name}' from a StuffContent '{content_class_name}' "
                            f"but the concept of name '{content_class_name}' is not found in the library"
                        )
                        raise StuffFactoryError(msg) from exc

                return cls.make_stuff(
                    concept=concept,
                    content=stuff_content,
                    name=name,
                    code=code,
                )

            # Case 1.2 or 1.4: list → ListContent
            if isinstance(stuff_content_or_data, list):
                if len(stuff_content_or_data) == 0:
                    msg = f"Cannot create Stuff '{name}' from empty list"
                    raise StuffFactoryError(msg)

                first_item = stuff_content_or_data[0]

                # Case 1.2: list[str] → ListContent[TextContent] with Text concept
                if isinstance(first_item, str):
                    for item in stuff_content_or_data:
                        if not isinstance(item, str):
                            msg = (
                                f"Trying to create a Stuff '{name}' from a list of strings but the item {item} is not a string. "
                                "Every items of the list should be a identical type. If its a string, everything should be a string."
                            )
                            raise StuffFactoryError(msg)

                    items = [TextContent(text=item) for item in cast("list[str]", stuff_content_or_data)]
                    return cls.make_stuff(
                        concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
                        content=ListContent(items=items),
                        name=name,
                        code=code,
                    )

                # Case 1.4: list[StuffContent] → ListContent[StuffContent]
                elif isinstance(first_item, StuffContent):  # pyright: ignore[reportUnnecessaryIsInstance]
                    # Get the concept from the first item's class name
                    content_class_name = type(first_item).__name__

                    # Check all items are of the same type
                    for item in stuff_content_or_data:
                        if not isinstance(item, type(first_item)):
                            msg = (
                                f"Trying to create a Stuff '{name}' from a list of '{type(first_item).__name__}' "
                                f"but the items are not of the same type. Especially, items {item} is of type {type(item).__name__}. "
                                "Every items of the list should be a identical type. If its a string, everything should be a string."
                            )
                            raise StuffFactoryError(msg)

                    # Check if it's a native concept
                    if "Content" in content_class_name and NativeConceptCode.is_native_concept_ref_or_code(
                        concept_ref_or_code=content_class_name.split("Content")[0]
                    ):
                        concept = get_native_concept(native_concept=NativeConceptCode(content_class_name.split("Content")[0]))
                    else:
                        try:
                            concept = concept_library.get_required_concept_from_concept_ref_or_code(
                                concept_ref_or_code=content_class_name, search_domain_codes=search_domain_codes
                            )
                        except ConceptLibraryConceptNotFoundError as exc:
                            msg = (
                                f"Trying to create a Stuff '{name}' from a list of StuffContent but "
                                f"the concept of name '{content_class_name}' is not found in the library"
                            )
                            raise StuffFactoryError(msg) from exc

                    return cls.make_stuff(
                        concept=concept,
                        content=ListContent(items=cast("list[StuffContent]", stuff_content_or_data)),
                        name=name,
                        code=code,
                    )
                else:
                    msg = f"Cannot create Stuff from list of {type(first_item)}. Type should be {StuffContentOrData}."
                    raise StuffFactoryError(msg)

        # ==================== CASE 2: Dict with 'concept' AND 'content' keys ====================
        # Convert DictStuff instance to plain dict if needed
        if isinstance(stuff_content_or_data, DictStuff):
            stuff_content_or_data = stuff_content_or_data.model_dump()

        if not isinstance(stuff_content_or_data, dict):
            msg = f"Unexpected type for stuff_content_or_data: {type(stuff_content_or_data)}.Type should be {StuffContentOrData}."
            raise StuffFactoryError(msg)

        # Check if it's a dict with concept and content keys
        if "concept" not in stuff_content_or_data:
            msg = f"Trying to create a Stuff '{name}' from a dict that should represent a StuffContentOrData but does not have a 'concept' key."
            raise StuffFactoryError(msg)

        if "content" not in stuff_content_or_data:
            msg = f"Trying to create a Stuff '{name}' from a dict that should represent a StuffContentOrData but does not have a 'content' key."
            raise StuffFactoryError(msg)

        # All Case 2 variants - dict with concept and content
        if len(stuff_content_or_data) != 2:
            msg = (
                f"Trying to create a Stuff '{name}' from a dict that should represent a StuffContentOrData but does not have "
                "exactly keys 'concept' and 'content'."
            )
            raise StuffFactoryError(msg)

        concept_ref = stuff_content_or_data["concept"]
        content = stuff_content_or_data["content"]

        # Get the concept from the library
        try:
            concept = concept_library.get_required_concept_from_concept_ref_or_code(
                concept_ref_or_code=concept_ref, search_domain_codes=search_domain_codes
            )
        except ConceptLibraryConceptNotFoundError as exc:
            msg = (
                f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                f"but the concept of name '{concept_ref}' is not found in the library"
            )
            raise StuffFactoryError(msg) from exc

        # Case 2.1d: content is a bool → YesNoContent for a YesNo-compatible concept.
        # Checked BEFORE the str/int-ish arms (bool is a subclass of int) so a boolean never falls through to
        # the final "unexpected type" error. No string coercion: "yes"/"no" strings take the str path and fail there.
        if isinstance(content, bool):
            yes_no_concept = get_native_concept(native_concept=NativeConceptCode.YES_NO)
            if concept_library.is_compatible(tested_concept=concept, wanted_concept=yes_no_concept, strict=True):
                return cls.make_stuff(
                    concept=concept,
                    content=StuffContentFactory.make_stuff_content_from_concept_required(concept=concept, value=content),
                    name=name,
                    code=code,
                )
            msg = (
                f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                f"but the concept of name '{concept_ref}' is not compatible with native concept 'native.YesNo' (the content is a boolean)"
            )
            raise StuffFactoryError(msg)

        # Case 2.1: content is a string
        if isinstance(content, str):
            # Check if concept is strictly compatible with Text (refinement = strict compatibility)
            text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
            if concept_library.is_compatible(tested_concept=concept, wanted_concept=text_concept, strict=True):
                return cls.make_stuff(
                    concept=concept,
                    content=TextContent(text=content),
                    name=name,
                    code=code,
                )
            # Case 2.1f: a strict-ISO date/datetime string under a Date-compatible concept builds a DateContent
            # (routed through the concept resolver so a refining subclass is honored, like the YesNo arm).
            date_concept = get_native_concept(native_concept=NativeConceptCode.DATE)
            if concept_library.is_compatible(tested_concept=concept, wanted_concept=date_concept, strict=True):
                return cls.make_stuff(
                    concept=concept,
                    content=StuffContentFactory.make_stuff_content_from_concept_required(concept=concept, value=content),
                    name=name,
                    code=code,
                )
            msg = (
                f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                f"but the concept of name '{concept_ref}' is not compatible with native concept 'native.Text' or 'native.Date'"
            )
            raise StuffFactoryError(msg)

        # Case 2.1e: content is a bare date/datetime object (a TOML temporal literal used as envelope content)
        # → DateContent for a Date-compatible concept. isinstance(date) covers datetime (its subclass); a bare
        # time never reaches here — the inputs loader rejects it, and a time is not a date anyway.
        if isinstance(content, datetime.date):
            date_concept = get_native_concept(native_concept=NativeConceptCode.DATE)
            if concept_library.is_compatible(tested_concept=concept, wanted_concept=date_concept, strict=True):
                return cls.make_stuff(
                    concept=concept,
                    content=StuffContentFactory.make_stuff_content_from_concept_required(concept=concept, value=content),
                    name=name,
                    code=code,
                )
            msg = (
                f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                f"but the concept of name '{concept_ref}' is not compatible with native concept 'native.Date' (the content is a date/datetime)"
            )
            raise StuffFactoryError(msg)

        # Case 2.3: content is a StuffContent object (includes both native and StructuredContent)
        if isinstance(content, StuffContent):
            if concept.structure_class_name != content.__class__.__name__:
                msg = (
                    f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                    f"but the concept of name '{concept_ref}' is not compatible with the content of type {content.__class__.__name__}"
                )
                raise StuffFactoryError(msg)

            return cls.make_stuff(
                concept=concept,
                content=content,
                name=name,
                code=code,
            )

        # Case 2.5: content is a dict
        if isinstance(content, dict):
            content_dict = cast("dict[str, Any]", content)
            # CSV input: a {"url": "...csv"} under a structured row concept loads as ListContent[row-concept].
            csv_stuff = cls._try_make_csv_list_stuff(concept=concept, content=content_dict, name=name, code=code)
            if csv_stuff is not None:
                return csv_stuff

            the_class = get_class_registry().get_class(name=concept.structure_class_name)
            if the_class is None:
                msg = (
                    f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a dict that should represent a StuffContentOrData "
                    f"but the concept of name '{concept_ref}' is not compatible with a dict content"
                )
                raise StuffFactoryError(msg)

            return cls.make_stuff(
                name=name,
                code=code,
                concept=concept,
                content=the_class.model_validate(obj=content),
            )

        # Case 2.2/2.2b/2.4/2.5/2.6: content is a list
        if isinstance(content, list):
            list_content_2 = cast("list[Any]", content)
            if len(list_content_2) == 0:
                msg = "Cannot create Stuff from empty list in content"
                raise StuffFactoryError(msg)

            first_item = list_content_2[0]

            # Case 2.2/2.2b: list[str]
            if isinstance(first_item, str):
                for item in list_content_2:
                    if not isinstance(item, str):
                        msg = (
                            f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a list of strings but the item {item} "
                            "is not a string. Every items of the list should be a identical type. If its a string, everything should be a string."
                        )
                        raise StuffFactoryError(msg)

                text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
                if concept_library.is_compatible(tested_concept=concept, wanted_concept=text_concept, strict=True):
                    items = [TextContent(text=item) for item in list_content_2]
                    return cls.make_stuff(
                        concept=concept,
                        content=ListContent(items=items),
                        name=name,
                        code=code,
                    )

                msg = f"Concept '{concept_ref}' is not compatible with list of text content"
                raise StuffFactoryError(msg)

            # Case 2.4: list[StuffContent] (includes both native and StructuredContent)
            if isinstance(first_item, StuffContent):
                for item in list_content_2:
                    if not isinstance(item, type(first_item)):
                        msg = (
                            f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a list of StuffContent "
                            "but the items are not of the same type. Every items of the list should be a identical type. "
                            f"If its a '{type(first_item).__name__}', everything should be a '{type(first_item).__name__}'."
                        )
                        raise StuffFactoryError(msg)

                return cls.make_stuff(
                    concept=concept,
                    content=ListContent(items=cast("list[StuffContent]", list_content_2)),
                    name=name,
                    code=code,
                )

            # Case 2.6: list[dict]
            if isinstance(first_item, dict):
                for item_dict in list_content_2:
                    if not isinstance(item_dict, dict):
                        msg = (
                            f"Trying to create a Stuff '{name}' in the inputs of your pipe, from a list of dicts but "
                            f"the item {item_dict} is not a dict. Every items of the list should be a identical type. "
                            "If its a dict, everything should be a dict."
                        )
                        raise StuffFactoryError(msg)

                # Create StuffContent objects from dicts
                stuff_items: list[StuffContent] = []
                for item_dict in list_content_2:
                    stuff_content = StuffContentFactory.make_stuff_content_from_concept_with_fallback(
                        concept=concept,
                        value=item_dict,
                    )
                    stuff_items.append(stuff_content)

                return cls.make_stuff(
                    concept=concept,
                    content=ListContent(items=stuff_items),
                    name=name,
                    code=code,
                )

            msg = f"Cannot create Stuff from list of {type(first_item)} in content"
            raise StuffFactoryError(msg)

        msg = f"Unexpected type for content value: {type(content)}"
        raise StuffFactoryError(msg)
