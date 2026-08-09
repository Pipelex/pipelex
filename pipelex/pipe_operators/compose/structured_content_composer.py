import datetime
import inspect
from typing import Any, NamedTuple, TypeAlias, cast, get_args, get_origin

from pydantic import ValidationError

from pipelex import log
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.compose_ops import build_compose_context
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint, ConstructFieldBlueprint, ConstructFieldMethod
from pipelex.pipe_operators.compose.exceptions import (
    StructuredContentComposerTypeError,
    StructuredContentComposerValidationError,
    StructuredContentComposerValueError,
)
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.typing.annotation_utils import unwrap_optional
from pipelex.tools.typing.class_utils import are_classes_equivalent
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

NativeScalarValue: TypeAlias = str | float | int | bool | datetime.date
"""The native Python scalar types a content wrapper can be unwrapped into."""

# The exact native scalar target types (no subclass matching: datetime is a date subclass
# and bool is an int subclass, and neither cross-kind conversion is wanted).
NATIVE_SCALAR_TARGET_TYPES: tuple[type[Any], ...] = (str, float, int, bool, datetime.date)


class NativeScalarExtraction(NamedTuple):
    """Result of attempting to extract a native scalar from a content wrapper.

    The explicit `matched` flag distinguishes a genuine extraction from a no-match,
    because legitimately extracted values can be falsy (False, 0, empty string).
    """

    matched: bool
    value: NativeScalarValue | None


class StructuredContentComposer:
    """Composes a StructuredContent instance from a ConstructBlueprint.

    The composer resolves each field in the blueprint according to its method:
    - FIXED: Use the literal value directly
    - FROM_VAR: Get value from working memory via path
    - TEMPLATE: Render Jinja2 template with working memory context and runtime params
    - NESTED: Recursively compose a nested StructuredContent

    Attributes:
        construct_blueprint: The blueprint defining how to compose each field
        working_memory: The working memory containing input variables
        output_class: The StructuredContent subclass to instantiate
        runtime_params: Additional runtime parameters for template context (from PipeRunParams.params)
        extra_context: Extra context values for template rendering (from PipeCompose.extra_context)
    """

    def __init__(
        self,
        construct_blueprint: ConstructBlueprint,
        working_memory: WorkingMemory,
        output_class: type[StuffContent],
        runtime_params: dict[str, Any] | None = None,
        extra_context: dict[str, Any] | None = None,
    ):
        self.construct_blueprint = construct_blueprint
        self.working_memory = working_memory
        self.output_class = output_class
        self.runtime_params = runtime_params or {}
        self.extra_context = extra_context or {}
        # Per-field record of how each field was built. Populated as fields resolve.
        # Shape per entry: {"method": ConstructFieldMethod, "rendered": str (templates only)}.
        # Nested fields record only their method; their sub-fields are not surfaced.
        self.field_resolutions: dict[str, dict[str, Any]] = {}

    async def compose(self) -> StuffContent:
        """Compose the StructuredContent asynchronously.

        Returns:
            Populated StructuredContent instance
        """
        field_values = await self._resolve_all_fields()
        try:
            return self.output_class.model_validate(field_values)
        except ValidationError as exc:
            formatted_error = format_pydantic_validation_error(exc)
            field_type_summary = self._build_field_type_summary(field_values)
            msg = f"Cannot validate {self.output_class.__name__}: {formatted_error}\n{field_type_summary}"
            raise StructuredContentComposerValidationError(msg) from exc

    def _build_field_type_summary(self, field_values: dict[str, Any]) -> str:
        """Build a diagnostic summary comparing actual vs expected types for each field.

        This is used in error messages to help users quickly identify type mismatches.
        The method is defensive: it never raises, returning a fallback message instead.

        Args:
            field_values: The resolved field values that failed validation

        Returns:
            A formatted string showing actual vs expected types per field
        """
        try:
            lines: list[str] = ["Field type summary:"]
            for field_name, value in field_values.items():
                actual_type_name = type(value).__name__
                field_info = self.output_class.model_fields.get(field_name)
                if field_info and field_info.annotation:
                    expected_type_name = getattr(field_info.annotation, "__name__", str(field_info.annotation))
                else:
                    expected_type_name = "unknown"
                mismatch_marker = "" if actual_type_name == expected_type_name else " <-- MISMATCH"
                lines.append(f"  {field_name}: {actual_type_name} (expected {expected_type_name}){mismatch_marker}")
            return "\n".join(lines)
        except Exception:  # noqa: BLE001
            # General exception catching tolerated here because the method is purely defensive diagnostic code that builds error messages
            return "Field type summary: unavailable (introspection failed)"

    async def _resolve_all_fields(self) -> dict[str, Any]:
        """Resolve all fields in the blueprint to their values.

        Returns:
            Dictionary mapping field names to resolved values
        """
        field_values: dict[str, Any] = {}

        for field_name, field_blueprint in self.construct_blueprint.fields.items():
            field_values[field_name] = await self._resolve_field(field_blueprint=field_blueprint, field_name=field_name)

        return field_values

    async def _resolve_field(self, field_blueprint: ConstructFieldBlueprint, *, field_name: str) -> Any:
        """Resolve a single field according to its composition method.

        Args:
            field_blueprint: The blueprint for this field
            field_name: The name of the field (for error messages and nested class lookup)

        Returns:
            The resolved value for the field
        """
        self.field_resolutions[field_name] = {"method": field_blueprint.method}
        match field_blueprint.method:
            case ConstructFieldMethod.FIXED:
                return field_blueprint.fixed_value

            case ConstructFieldMethod.FROM_VAR:
                return self._resolve_from_var(field_blueprint=field_blueprint, field_name=field_name)

            case ConstructFieldMethod.TEMPLATE:
                rendered_text = await self._resolve_template(field_blueprint=field_blueprint)
                self.field_resolutions[field_name]["rendered"] = rendered_text
                return rendered_text

            case ConstructFieldMethod.NESTED:
                return await self._resolve_nested(field_blueprint=field_blueprint, field_name=field_name)

    def _resolve_from_var(self, field_blueprint: ConstructFieldBlueprint, *, field_name: str) -> Any:
        """Resolve a FROM_VAR field by getting value from working memory.

        The resolution is type-aware: it checks what the target field expects
        (unwrapping Optional annotations) and converts content accordingly:
        - TextContent -> str: extract .text
        - NumberContent -> float/int: extract .number
        - YesNoContent -> bool: extract .yes_no
        - DateContent -> date: extract .date
        - any wrapper -> its own wrapper class/subclass: keep object
        - ListContent -> list[native scalar]: extract the scalar from each item
        - ListContent -> list[X]: extract items as dicts
        - ListContent -> ListContent: keep object

        If list_to_dict_keyed_by is set, converts the list to a dict using the specified
        attribute as the key.

        Args:
            field_blueprint: The field blueprint with from_path
            field_name: The name of the target field (for type lookup)

        Returns:
            The value from working memory, converted as appropriate for the target field
        """
        if not field_blueprint.from_path:
            msg = "from_path is required for FROM_VAR method"
            raise StructuredContentComposerValueError(msg)

        path = field_blueprint.from_path
        expected_type: type[Any] | None = self._get_field_expected_type(field_name=field_name)
        log.verbose(f"_resolve_from_var: resolving path '{path}' for field '{field_name}' (expected: {expected_type})")

        if "." in path:
            resolved_value = self._resolve_dotted_path(path=path, expected_type=expected_type)
        else:
            resolved_value = self._resolve_from_stuff_name(name=path, expected_type=expected_type)

        # If list_to_dict_keyed_by is set, convert list to dict
        if field_blueprint.list_to_dict_keyed_by:
            return self._convert_list_to_dict_keyed_by(
                value=resolved_value,
                key_attr=field_blueprint.list_to_dict_keyed_by,
            )

        return resolved_value

    def _convert_list_to_dict_keyed_by(self, value: Any, *, key_attr: str) -> dict[str, Any]:
        """Convert a ListContent or list to a dict keyed by a specified attribute.

        Items are converted to dicts to allow Pydantic's discriminated union validation
        to work properly when the target field uses union types with discriminators.

        Args:
            value: The value to convert (must be ListContent or list)
            key_attr: The attribute name to use as the dict key

        Returns:
            A dict mapping the key_attr values to the items (converted to dicts)

        Raises:
            StructuredContentComposerTypeError: If value is not a ListContent or list
            StructuredContentComposerValueError: If an item doesn't have the key_attr
        """
        # Extract items from ListContent if needed
        items: list[Any]
        if isinstance(value, ListContent):
            list_content = cast("ListContent[StuffContent]", value)
            items = list_content.items
        elif isinstance(value, list):
            items = cast("list[Any]", value)
        else:
            msg = f"list_to_dict_keyed_by requires ListContent or list, got {type(value).__name__}"
            raise StructuredContentComposerTypeError(msg)

        log.verbose(f"  Converting list of {len(items)} items to dict keyed by '{key_attr}'")

        result: dict[str, Any] = {}
        for idx, item in enumerate(items):
            # Try to get the key attribute
            if hasattr(item, key_attr):
                key = getattr(item, key_attr)
            elif isinstance(item, dict) and key_attr in item:
                key = item[key_attr]  # pyright: ignore[reportUnknownVariableType]
            else:
                msg = f"Item at index {idx} does not have attribute '{key_attr}'"
                raise StructuredContentComposerValueError(msg)

            if not isinstance(key, str):
                msg = f"Key attribute '{key_attr}' at index {idx} must be a string, got {type(key).__name__}"  # pyright: ignore[reportUnknownArgumentType]
                raise StructuredContentComposerTypeError(msg)

            # Convert StuffContent items to dicts for proper discriminated union validation
            if isinstance(item, StuffContent):
                result[key] = item.model_dump(exclude_none=False, serialize_as_any=True)
            elif isinstance(item, dict):
                result[key] = item
            else:
                result[key] = item  # pyright: ignore[reportUnknownVariableType]

        log.verbose(f"  Converted to dict with keys: {list(result.keys())}")
        return result

    def _resolve_dotted_path(self, path: str, *, expected_type: type[Any] | None) -> Any:
        """Resolve a dotted path by navigating through object attributes.

        Handles paths like "deal.customer_name" by getting the base object
        from working memory and then navigating through its attributes.
        Applies type conversion based on expected_type (same as non-dotted paths).

        Args:
            path: The dotted path (e.g., "deal.customer_name")
            expected_type: The expected type annotation for the target field

        Returns:
            The value at the end of the attribute path, converted as appropriate
        """
        parts = path.split(".", 1)
        base_name = parts[0]
        attr_path = parts[1]

        stuff = self.working_memory.get_stuff(base_name)
        stuff_content: StuffContent = stuff.content
        log.verbose(f"  Stuff '{base_name}' content type: {type(stuff_content).__name__}")

        # Navigate the attribute path - this is dynamic attribute access at runtime
        current_value: Any = stuff_content
        for attr in attr_path.split("."):
            if hasattr(current_value, attr):  # pyright: ignore[reportUnknownArgumentType]
                current_value = getattr(current_value, attr)  # pyright: ignore[reportUnknownArgumentType]
            elif isinstance(current_value, dict) and attr in current_value:  # pyright: ignore[reportUnknownVariableType]
                current_value = current_value[attr]  # pyright: ignore[reportUnknownVariableType]
            else:
                msg = f"Cannot resolve path '{path}': attribute '{attr}' not found"
                raise StructuredContentComposerValueError(msg)
        log.verbose(f"  Resolved value type: {type(current_value).__name__}")  # pyright: ignore[reportUnknownArgumentType]

        # Apply type conversion if the resolved value is a StuffContent
        if isinstance(current_value, StuffContent):
            return self._convert_for_target_type(stuff_content=current_value, expected_type=expected_type)
        else:
            return current_value  # pyright: ignore[reportUnknownVariableType]

    def _resolve_from_stuff_name(
        self, name: str, *, expected_type: type[Any] | None
    ) -> StuffContent | list[dict[str, Any]] | list[NativeScalarValue] | NativeScalarValue:
        """Resolve a simple (non-dotted) path and convert content based on expected type.

        Args:
            name: A non-dotted path, hence it's the stuff name in working memory
            expected_type: The expected type annotation for the target field

        Returns:
            The content, converted as appropriate for the target field type
        """
        stuff = self.working_memory.get_stuff(name=name)
        stuff_content: StuffContent = stuff.content
        log.verbose(f"  Stuff '{name}' content type: {type(stuff_content).__name__}")
        return self._convert_for_target_type(stuff_content=stuff_content, expected_type=expected_type)

    def _convert_for_target_type(
        self, stuff_content: StuffContent, *, expected_type: type[Any] | None
    ) -> StuffContent | list[dict[str, Any]] | list[NativeScalarValue] | NativeScalarValue:
        """Convert content based on the expected target field type.

        Central dispatcher for type-aware conversion. Native scalar wrappers are unwrapped
        first (TextContent -> str, NumberContent -> float/int, YesNoContent -> bool,
        DateContent -> date) when the target expects the native type; otherwise routes to
        specific conversion methods based on content type.

        Args:
            stuff_content: The content to convert
            expected_type: The expected type annotation for the target field

        Returns:
            The content, converted as appropriate for the target field type
        """
        if expected_type is not None:
            extraction = self._extract_native_scalar(stuff_content=stuff_content, expected_type=expected_type)
            if extraction.matched and extraction.value is not None:
                log.verbose(f"  -> Target expects a native scalar, extracted {type(extraction.value).__name__} from {type(stuff_content).__name__}")
                return extraction.value
        if isinstance(stuff_content, TextContent):
            return self._convert_text_content(text_content=stuff_content, expected_type=expected_type)
        elif isinstance(stuff_content, ListContent):
            list_content = cast("ListContent[StuffContent]", stuff_content)
            return self._convert_list_content(list_content=list_content, expected_type=expected_type)
        elif expected_type is not None and self._expects_type(expected_type=expected_type, target_type=StuffContent):
            log.verbose(f"  -> Target expects {expected_type.__name__}, converting content")
            return self._convert_content_for_field(stuff_content=stuff_content, expected_type=expected_type)
        else:
            # Fallback: return as-is
            log.verbose(f"  -> Unknown target type, returning {type(stuff_content).__name__} object")
            return stuff_content

    def _convert_text_content(self, text_content: TextContent, *, expected_type: Any) -> TextContent:
        """Convert TextContent based on expected type (TextContent or subclass).

        The str target case is handled upstream by the native scalar extraction
        in _convert_for_target_type.

        Args:
            text_content: The TextContent to convert
            expected_type: The expected type annotation for the target field

        Returns:
            The TextContent object (potentially converted to the expected subclass)
        """
        if self._expects_type(expected_type=expected_type, target_type=TextContent):
            # Target field expects TextContent or subclass
            converted_text_content = self._convert_content_for_field(stuff_content=text_content, expected_type=expected_type)
            assert isinstance(converted_text_content, TextContent)
            return converted_text_content
        else:
            # Default: return the object as-is
            log.verbose(f"  -> Unknown target type, returning {type(text_content).__name__} object")
            return text_content

    def _extract_native_scalar(self, *, stuff_content: StuffContent, expected_type: type[Any]) -> NativeScalarExtraction:
        """Extract the native scalar value from a scalar content wrapper when the target expects it.

        Conversion matrix (wrapper -> native target):
        - TextContent -> str (or str subclass): extract .text
        - NumberContent -> float or int (never bool, an int subclass): extract .number
        - YesNoContent -> bool: extract .yes_no
        - DateContent -> date (exactly, never datetime, a date subclass): extract .date,
          but only when the Date carries no time of day — truncating a timestamped Date
          to a bare date would silently drop the time and its UTC offset, so it raises

        A wrapper-typed target (e.g. a NumberContent field) deliberately does not match here:
        it is handled by the generic StuffContent conversion path so the object is kept.

        Args:
            stuff_content: The content wrapper to extract from
            expected_type: The expected type annotation for the target field or list item

        Returns:
            A NativeScalarExtraction with matched=True and the scalar value when the
            wrapper/target pair is in the matrix, matched=False otherwise

        Raises:
            StructuredContentComposerTypeError: If a Date carrying a time of day targets a bare `date`
        """
        if isinstance(stuff_content, TextContent):
            if self._expects_type(expected_type=expected_type, target_type=str):
                return NativeScalarExtraction(matched=True, value=stuff_content.text)
        elif isinstance(stuff_content, NumberContent):
            if expected_type is not bool and (
                self._expects_type(expected_type=expected_type, target_type=float) or self._expects_type(expected_type=expected_type, target_type=int)
            ):
                return NativeScalarExtraction(matched=True, value=stuff_content.number)
        elif isinstance(stuff_content, YesNoContent):
            if self._expects_type(expected_type=expected_type, target_type=bool):
                return NativeScalarExtraction(matched=True, value=stuff_content.yes_no)
        elif isinstance(stuff_content, DateContent):
            if expected_type is datetime.date:
                if stuff_content.time is not None:
                    msg = (
                        f"Cannot copy a Date carrying a time of day ({stuff_content.rendered_plain()}) into a bare `date` field: "
                        "it would silently drop the time and its UTC offset. Target a Date-typed field to keep the time."
                    )
                    raise StructuredContentComposerTypeError(msg)
                return NativeScalarExtraction(matched=True, value=stuff_content.date)
        return NativeScalarExtraction(matched=False, value=None)

    def _convert_list_content(
        self, list_content: ListContent[StuffContent], *, expected_type: type[Any] | None
    ) -> ListContent[StuffContent] | list[dict[str, Any]] | list[NativeScalarValue]:
        """Convert ListContent based on expected type (list[X] or ListContent[X]).

        Args:
            list_content: The ListContent to convert
            expected_type: The expected type annotation for the target field

        Returns:
            Either a list of dicts, a list of native scalars, or a ListContent object with converted items
        """
        expected_item_type: type[Any] | None
        if expected_type and self._expects_list_content_type(expected_type=expected_type):
            # Target field expects ListContent[X], check item compatibility and return as ListContent
            expected_item_type = self._get_list_item_type(expected_type=expected_type)
            log.verbose(f"  -> Target expects ListContent[{expected_item_type}]")
            converted_items = self._convert_list_items_as_objects(items=list_content.items, expected_item_type=expected_item_type)
            return ListContent(items=converted_items)
        elif expected_type and self._expects_list_type(expected_type=expected_type):
            expected_item_type = self._get_list_item_type(expected_type=expected_type)
            if expected_item_type is not None and expected_item_type in NATIVE_SCALAR_TARGET_TYPES:
                # Target expects list of native scalars, extract the scalar from each item wrapper
                log.verbose(f"  -> Target expects list[{expected_item_type}], extracting native scalars from ListContent items")
                return self._convert_list_items_as_scalars(items=list_content.items, expected_item_type=expected_item_type)
            # Target expects list[X] with structured items, extract items as dicts for Pydantic reconstruction
            log.verbose(f"  -> Target expects list[{expected_item_type}], extracting items from ListContent")
            return self._convert_list_items_as_dicts(items=list_content.items, expected_item_type=expected_item_type)
        else:
            # Default: return the object as-is
            log.verbose(f"  -> Unknown target type, returning ListContent object with {list_content.nb_items} items")
            return list_content

    def _get_field_expected_type(self, field_name: str) -> type[Any] | None:
        """Get the expected type annotation for a field from the output class.

        Optional annotations (`Optional[X]` / `X | None`) are unwrapped to their non-None
        arm, so an optional field converts exactly like its required counterpart. Genuine
        multi-arm unions are returned unchanged.

        Args:
            field_name: The name of the field

        Returns:
            The type annotation for the field
        """
        field_info = self.output_class.model_fields.get(field_name)
        if field_info and field_info.annotation:
            return cast("type[Any]", unwrap_optional(field_info.annotation))
        else:
            return None

    def _expects_type(self, *, expected_type: type[Any], target_type: type) -> bool:
        """Check if the expected type matches or is a subclass of target_type.

        Args:
            expected_type: The type annotation to check
            target_type: The type to match against (e.g., str, TextContent, StuffContent)

        Returns:
            True if expected_type is target_type or a subclass of it
        """
        if expected_type is target_type:
            return True
        try:
            return issubclass(expected_type, target_type)
        except TypeError:
            # expected_type is not a class (e.g., it's a generic like list[X])
            return False

    def _convert_content_for_field(self, stuff_content: StuffContent, *, expected_type: type[StuffContent]) -> StuffContent:
        """Convert any StuffContent to the expected type if needed.

        This is a generic conversion method that handles class compatibility for
        any StuffContent subclass (TextContent, StructuredContent, etc.):
        1. If actual class is the expected class or a subclass -> return as-is
        2. If classes are structurally equivalent -> rebuild using expected class
        3. Otherwise -> attempt rebuild, error on failure

        Args:
            stuff_content: The StuffContent object to convert
            expected_type: The expected StuffContent class/subclass

        Returns:
            The content object, potentially rebuilt as the expected class

        Raises:
            ValueError: If the content cannot be converted to the expected type
        """
        actual_type = type(stuff_content)

        if isinstance(stuff_content, expected_type):
            # Exact match or subclass - return as-is
            log.verbose(f"  -> {actual_type.__name__} is compatible with {expected_type.__name__}, returning as-is")
            return stuff_content
        elif are_classes_equivalent(class_1=actual_type, class_2=expected_type):
            # Check structural equivalence and rebuild if compatible
            log.verbose(f"  -> {actual_type.__name__} is structurally equivalent to {expected_type.__name__}, rebuilding")
            content_dict = stuff_content.model_dump(exclude_none=False, serialize_as_any=True)
            return expected_type.model_validate(content_dict)
        else:
            # Try to rebuild anyway if expected_type accepts the content's fields
            try:
                log.verbose(f"  -> Attempting to rebuild {actual_type.__name__} as {expected_type.__name__}")
                content_dict = stuff_content.model_dump(exclude_none=False, serialize_as_any=True)
                return expected_type.model_validate(content_dict)
            except ValidationError as exc:
                formatted_error = format_pydantic_validation_error(exc)
                msg = f"Cannot convert {actual_type.__name__} to {expected_type.__name__}: classes are not compatible. {formatted_error}"
                raise StructuredContentComposerTypeError(msg) from exc

    def _expects_list_content_type(self, expected_type: type[Any]) -> bool:
        """Check if the expected type is ListContent (not list[X]).

        Args:
            expected_type: The type annotation to check

        Returns:
            True if the expected type is ListContent or a subclass
        """
        # Check if it's a generic ListContent[X]
        origin = get_origin(expected_type)
        if origin is not None:
            try:
                return isinstance(origin, type) and issubclass(origin, ListContent)
            except TypeError:
                return False

        # Check if it's the ListContent class itself
        try:
            return issubclass(expected_type, ListContent)
        except TypeError:
            return False

    def _expects_list_type(self, expected_type: type[Any]) -> bool:
        """Check if the expected type is list[X] (not ListContent).

        Args:
            expected_type: The type annotation to check

        Returns:
            True if the expected type is list[X]
        """
        origin = get_origin(expected_type)
        return origin is list

    def _get_list_item_type(self, expected_type: type[Any]) -> type[Any] | None:
        """Extract the item type from list[X] or ListContent[X].

        A nullable item annotation (`list[X | None]`) is normalized to its non-None arm,
        so nullable items convert exactly like their non-nullable counterparts.

        Args:
            expected_type: The type annotation (e.g., list[Address] or ListContent[TeamMember])

        Returns:
            The item type X, or None if not determinable
        """
        args = get_args(expected_type)
        if args:
            return cast("type[Any]", unwrap_optional(args[0]))
        else:
            return None

    def _convert_list_items_as_dicts(self, items: list[StuffContent], *, expected_item_type: type[Any] | None) -> list[dict[str, Any]]:
        """Convert list items to dicts for Pydantic model_validate reconstruction.

        Used when target is list[X] - items are returned as dicts so Pydantic
        can reconstruct them during model_validate().

        Args:
            items: The list of items to convert
            expected_item_type: The expected type for each item

        Returns:
            List of item dicts
        """
        log.verbose(f"     Converting {len(items)} items to dicts, expected item type: {expected_item_type}")

        if expected_item_type is None:
            log.verbose("     No expected item type, converting all items to dicts")
            return [item.model_dump(exclude_none=False, serialize_as_any=True) for item in items]

        converted_items: list[dict[str, Any]] = []
        for idx, item in enumerate(items):
            self._validate_item_compatibility(item=item, expected_type=expected_item_type, idx=idx)
            converted_items.append(item.model_dump(exclude_none=False, serialize_as_any=True))

        log.verbose(f"     Returning {len(converted_items)} items as dicts")
        return converted_items

    def _convert_list_items_as_scalars(self, *, items: list[StuffContent], expected_item_type: type[Any]) -> list[NativeScalarValue]:
        """Extract native scalar values from list item wrappers.

        Used when target is list[X] with X a native scalar type (str/float/int/bool/date):
        each item wrapper is unwrapped to its scalar value (e.g. TextContent -> str).

        Args:
            items: The list of item wrappers to convert
            expected_item_type: The native scalar type expected for each item

        Returns:
            List of native scalar values

        Raises:
            StructuredContentComposerTypeError: If an item is not a wrapper of the expected scalar type
        """
        log.verbose(f"     Extracting {len(items)} items as native scalars, expected item type: {expected_item_type}")

        converted_items: list[NativeScalarValue] = []
        for idx, item in enumerate(items):
            extraction = self._extract_native_scalar(stuff_content=item, expected_type=expected_item_type)
            if not extraction.matched or extraction.value is None:
                expected_type_name = getattr(expected_item_type, "__name__", str(expected_item_type))
                msg = f"Cannot convert item[{idx}] from {type(item).__name__} to {expected_type_name}: no native scalar extraction applies"
                raise StructuredContentComposerTypeError(msg)
            converted_items.append(extraction.value)

        log.verbose(f"     Returning {len(converted_items)} items as native scalars")
        return converted_items

    def _convert_list_items_as_objects(self, items: list[StuffContent], *, expected_item_type: type[Any] | None) -> list[StuffContent]:
        """Convert list items while keeping them as objects (for ListContent target).

        Used when target is ListContent[X] - items are validated and potentially
        rebuilt as the expected type, but returned as actual objects.

        Args:
            items: The list of items to convert
            expected_item_type: The expected type for each item

        Returns:
            List of StuffContent objects
        """
        log.verbose(f"     Converting {len(items)} items as objects, expected item type: {expected_item_type}")

        if expected_item_type is None:
            log.verbose("     No expected item type, returning items as-is")
            return items

        converted_items: list[StuffContent] = []
        for idx, item in enumerate(items):
            converted_item = self._convert_single_item_as_object(item, expected_type=expected_item_type, idx=idx)
            converted_items.append(converted_item)

        log.verbose(f"     Returning {len(converted_items)} items as objects")
        return converted_items

    def _validate_item_compatibility(self, item: StuffContent, *, expected_type: type[Any], idx: int) -> None:
        """Validate that an item can be converted to the expected type.

        Args:
            item: The item to validate
            expected_type: The expected type for the item
            idx: The item index (for error messages)

        Raises:
            ValueError: If the item cannot be converted to the expected type
        """
        actual_type = type(item)
        expected_type_name = getattr(expected_type, "__name__", str(expected_type))

        # Case 1: Exact match or subclass - OK
        # Note: isinstance() only works with actual classes, not ForwardRef, GenericAlias, or strings
        # We use inspect.isclass() to check if expected_type is a valid class for isinstance()
        if inspect.isclass(expected_type):
            try:
                if isinstance(item, expected_type):
                    log.verbose(f"     Item[{idx}]: {actual_type.__name__} is compatible with {expected_type_name}")
                    return
            except TypeError:
                # isinstance() failed - expected_type is not a valid type for this check
                pass

        # Case 2: Check structural equivalence - OK
        if hasattr(actual_type, "model_fields") and hasattr(expected_type, "model_fields"):
            if are_classes_equivalent(class_1=actual_type, class_2=expected_type):
                log.verbose(f"     Item[{idx}]: {actual_type.__name__} is structurally equivalent to {expected_type_name}")
                return

        # Case 3: native scalar item type - a wrapper dump can never validate into a bare scalar,
        # so fail loudly here instead of letting Pydantic produce a cryptic downstream error.
        # (The list[native-scalar] path normally extracts scalars before reaching this method.)
        if expected_type in NATIVE_SCALAR_TARGET_TYPES:
            msg = (
                f"Cannot convert item[{idx}] from {actual_type.__name__} to {expected_type_name}: "
                f"a native scalar item cannot be built from a {actual_type.__name__} dump"
            )
            raise StructuredContentComposerTypeError(msg)

        # Case 4: Try to validate via dict
        log.verbose(f"     Item[{idx}]: Validating conversion {actual_type.__name__} -> {expected_type_name}")
        item_dict = item.model_dump(exclude_none=False, serialize_as_any=True)

        if hasattr(expected_type, "model_validate"):
            try:
                expected_type.model_validate(item_dict)
            except ValidationError as exc:
                formatted_error = format_pydantic_validation_error(exc)
                msg = f"Cannot convert item[{idx}] from {actual_type.__name__} to {expected_type_name}: {formatted_error}"
                raise StructuredContentComposerTypeError(msg) from exc

    def _convert_single_item_as_object(self, item: StuffContent, *, expected_type: type[Any], idx: int) -> StuffContent:
        """Convert a single list item while keeping it as an object.

        Delegates to the generic _convert_content_for_field method,
        adding item index information to error messages.

        Args:
            item: The item to convert
            expected_type: The expected type for the item
            idx: The item index (for error messages)

        Returns:
            The item, potentially rebuilt as the expected type

        Raises:
            ValueError: If the item cannot be converted to the expected type
        """
        try:
            log.verbose(f"     Item[{idx}]: Converting {type(item).__name__} to {expected_type.__name__}")
            return self._convert_content_for_field(item, expected_type=expected_type)
        except StructuredContentComposerTypeError as exc:
            # Re-raise with item index in message
            msg = f"Item[{idx}]: {exc}"
            raise StructuredContentComposerTypeError(msg) from exc

    async def _resolve_template(self, field_blueprint: ConstructFieldBlueprint) -> str:
        """Resolve a TEMPLATE field by rendering the Jinja2 template.

        The context is built consistently with _run_template_mode in PipeCompose:
        1. Working memory context (stuffs as variables)
        2. Runtime params from PipeRunParams.params (keys prefixed with _)
        3. Extra context from PipeCompose.extra_context

        This ensures templates in construct fields can access the same variables
        as templates in template mode.

        Args:
            field_blueprint: The field blueprint with template

        Returns:
            The rendered template string
        """
        if not field_blueprint.template:
            msg = "template is required for TEMPLATE method"
            raise StructuredContentComposerValueError(msg)

        # The same three-layer context PipeCompose's template mode renders against, built by the same
        # kernel function so the layering order cannot fork between the two paths.
        # TODO: dry-run templating is being removed — this direct render_template call is intentional
        return await render_template(
            template=field_blueprint.template,
            category=TemplateCategory.BASIC,
            context=build_compose_context(
                memory=self.working_memory,
                runtime_params=self.runtime_params,
                extra_context=self.extra_context,
            ),
        )

    async def _resolve_nested(self, field_blueprint: ConstructFieldBlueprint, *, field_name: str) -> StuffContent:
        """Resolve a NESTED field by recursively composing a nested StructuredContent.

        Args:
            field_blueprint: The field blueprint with nested ConstructBlueprint
            field_name: The field name (used to look up the expected class from output_class)

        Returns:
            The composed nested StructuredContent
        """
        if not field_blueprint.nested:
            msg = "nested is required for NESTED method"
            raise StructuredContentComposerValueError(msg)

        # Get the field type from the output class to determine nested class
        nested_class: type[StuffContent] = self._get_nested_field_class(field_name=field_name)

        # Create a new composer for the nested structure, passing through all context
        nested_composer = StructuredContentComposer(
            construct_blueprint=field_blueprint.nested,
            working_memory=self.working_memory,
            output_class=nested_class,
            runtime_params=self.runtime_params,
            extra_context=self.extra_context,
        )

        return await nested_composer.compose()

    def _get_nested_field_class(self, field_name: str) -> type[StuffContent]:
        """Get the class for a nested field from the output class's field annotations.

        Args:
            field_name: The name of the nested field

        Returns:
            The class expected for the nested field
        """
        # Get the field info from the Pydantic model
        field_info = self.output_class.model_fields.get(field_name)
        if field_info and field_info.annotation:
            return cast("type[StuffContent]", unwrap_optional(field_info.annotation))
        else:
            msg = f"Cannot determine class for nested field '{field_name}' in {self.output_class.__name__}"
            raise StructuredContentComposerTypeError(msg)
