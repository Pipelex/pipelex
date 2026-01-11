import types
from typing import Any, Union, cast, get_args, get_origin

from kajson import kajson
from pydantic import ValidationError

from pipelex import log
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_content_generator
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint, ConstructFieldBlueprint, ConstructFieldMethod
from pipelex.pipe_operators.compose.exceptions import (
    StructuredContentComposerTypeError,
    StructuredContentComposerValidationError,
    StructuredContentComposerValueError,
)
from pipelex.tools.typing.class_utils import are_classes_equivalent
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


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
        content_generator: The content generator to use for template rendering (supports dry run mode)
    """

    def __init__(
        self,
        construct_blueprint: ConstructBlueprint,
        working_memory: WorkingMemory,
        output_class: type[StuffContent],
        runtime_params: dict[str, Any] | None = None,
        extra_context: dict[str, Any] | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ):
        self.construct_blueprint = construct_blueprint
        self.working_memory = working_memory
        self.output_class = output_class
        self.runtime_params = runtime_params or {}
        self.extra_context = extra_context or {}
        self.content_generator = content_generator or get_content_generator()

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
            msg = f"Cannot validate {self.output_class.__name__}: {formatted_error}"
            msg += f"\nField values: {kajson.dumps(field_values, indent=4)}"
            raise StructuredContentComposerValidationError(msg) from exc

    async def _resolve_all_fields(self) -> dict[str, Any]:
        """Resolve all fields in the blueprint to their values.

        Returns:
            Dictionary mapping field names to resolved values
        """
        field_values: dict[str, Any] = {}

        for field_name, field_blueprint in self.construct_blueprint.fields.items():
            field_values[field_name] = await self._resolve_field(field_blueprint=field_blueprint, field_name=field_name)

        return field_values

    async def _resolve_field(self, field_blueprint: ConstructFieldBlueprint, field_name: str) -> Any:
        """Resolve a single field according to its composition method.

        Args:
            field_blueprint: The blueprint for this field
            field_name: The name of the field (for error messages and nested class lookup)

        Returns:
            The resolved value for the field
        """
        match field_blueprint.method:
            case ConstructFieldMethod.FIXED:
                return field_blueprint.fixed_value

            case ConstructFieldMethod.FROM_VAR:
                return self._resolve_from_var(field_blueprint=field_blueprint, field_name=field_name)

            case ConstructFieldMethod.TEMPLATE:
                return await self._resolve_template(field_blueprint=field_blueprint)

            case ConstructFieldMethod.NESTED:
                return await self._resolve_nested(field_blueprint=field_blueprint, field_name=field_name)

    def _resolve_from_var(self, field_blueprint: ConstructFieldBlueprint, field_name: str) -> Any:
        """Resolve a FROM_VAR field by getting value from working memory.

        The resolution is type-aware: it checks what the target field expects
        and converts content accordingly:
        - TextContent -> str: extract .text
        - TextContent -> TextContent/subclass: keep object
        - ListContent -> list[X]: extract items as dicts
        - ListContent -> ListContent: keep object

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
            return self._resolve_dotted_path(path=path, expected_type=expected_type)
        else:
            return self._resolve_from_stuff_name(name=path, expected_type=expected_type)

    def _resolve_dotted_path(self, path: str, expected_type: type[Any] | None) -> Any:
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

    def _resolve_from_stuff_name(self, name: str, expected_type: type[Any] | None) -> StuffContent | list[dict[str, Any]] | str:
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

    def _convert_for_target_type(self, stuff_content: StuffContent, expected_type: type[Any] | None) -> StuffContent | list[dict[str, Any]] | str:
        """Convert content based on the expected target field type.

        Central dispatcher for type-aware conversion. Routes to specific
        conversion methods based on content type.

        Args:
            stuff_content: The content to convert
            expected_type: The expected type annotation for the target field

        Returns:
            The content, converted as appropriate for the target field type
        """
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

    def _convert_text_content(self, text_content: TextContent, expected_type: Any) -> TextContent | str:
        """Convert TextContent based on expected type (str, TextContent, or subclass).

        Args:
            text_content: The TextContent to convert
            expected_type: The expected type annotation for the target field

        Returns:
            Either the text string, or the TextContent object (potentially converted)
        """
        if self._expects_type(expected_type=expected_type, target_type=str):
            # Target field expects str, extract the text
            log.verbose("  -> Target expects str, returning TextContent.text")
            return text_content.text
        elif self._expects_type(expected_type=expected_type, target_type=TextContent):
            # Target field expects TextContent or subclass
            converted_text_content = self._convert_content_for_field(stuff_content=text_content, expected_type=expected_type)
            assert isinstance(converted_text_content, TextContent)
            return converted_text_content
        else:
            # Default: return the object as-is
            log.verbose(f"  -> Unknown target type, returning {type(text_content).__name__} object")
            return text_content

    def _convert_list_content(
        self, list_content: ListContent[StuffContent], expected_type: type[Any] | None
    ) -> ListContent[StuffContent] | list[dict[str, Any]]:
        """Convert ListContent based on expected type (list[X] or ListContent[X]).

        Args:
            list_content: The ListContent to convert
            expected_type: The expected type annotation for the target field

        Returns:
            Either a list of dicts, or a ListContent object with converted items
        """
        expected_item_type: type[Any] | None
        if expected_type and self._expects_list_content_type(expected_type=expected_type):
            # Target field expects ListContent[X], check item compatibility and return as ListContent
            expected_item_type = self._get_list_item_type(expected_type=expected_type)
            log.verbose(f"  -> Target expects ListContent[{expected_item_type}]")
            converted_items = self._convert_list_items_as_objects(items=list_content.items, expected_item_type=expected_item_type)
            return ListContent(items=converted_items)
        elif expected_type and self._expects_list_type(expected_type=expected_type):
            # Target expects list[X], extract items as dicts for Pydantic reconstruction
            expected_item_type = self._get_list_item_type(expected_type=expected_type)
            log.verbose(f"  -> Target expects list[{expected_item_type}], extracting items from ListContent")
            return self._convert_list_items_as_dicts(items=list_content.items, expected_item_type=expected_item_type)
        else:
            # Default: return the object as-is
            log.verbose(f"  -> Unknown target type, returning ListContent object with {list_content.nb_items} items")
            return list_content

    def _get_field_expected_type(self, field_name: str) -> type[Any] | None:
        """Get the expected type annotation for a field from the output class.

        Args:
            field_name: The name of the field

        Returns:
            The type annotation for the field
        """
        field_info = self.output_class.model_fields.get(field_name)
        if field_info and field_info.annotation:
            return field_info.annotation
        else:
            return None

    def _expects_type(self, expected_type: type[Any], target_type: type) -> bool:
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

    def _convert_content_for_field(self, stuff_content: StuffContent, expected_type: type[StuffContent]) -> StuffContent:
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

        Args:
            expected_type: The type annotation (e.g., list[Address] or ListContent[TeamMember])

        Returns:
            The item type X, or None if not determinable
        """
        args = get_args(expected_type)
        if args:
            return args[0]  # type: ignore[return-value, no-any-return]
        else:
            return None

    def _convert_list_items_as_dicts(self, items: list[StuffContent], expected_item_type: type[Any] | None) -> list[dict[str, Any]]:
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

    def _convert_list_items_as_objects(self, items: list[StuffContent], expected_item_type: type[Any] | None) -> list[StuffContent]:
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
            converted_item = self._convert_single_item_as_object(item, expected_item_type, idx)
            converted_items.append(converted_item)

        log.verbose(f"     Returning {len(converted_items)} items as objects")
        return converted_items

    def _validate_item_compatibility(self, item: StuffContent, expected_type: type[Any], idx: int) -> None:
        """Validate that an item can be converted to the expected type.

        Args:
            item: The item to validate
            expected_type: The expected type for the item
            idx: The item index (for error messages)

        Raises:
            ValueError: If the item cannot be converted to the expected type
        """
        actual_type = type(item)

        # Case 1: Exact match or subclass - OK
        if isinstance(item, expected_type):
            log.verbose(f"     Item[{idx}]: {actual_type.__name__} is compatible with {expected_type.__name__}")
            return

        # Case 2: Check structural equivalence - OK
        if hasattr(actual_type, "model_fields") and hasattr(expected_type, "model_fields"):
            if are_classes_equivalent(class_1=actual_type, class_2=expected_type):
                log.verbose(f"     Item[{idx}]: {actual_type.__name__} is structurally equivalent to {expected_type.__name__}")
                return

        # Case 3: Try to validate via dict
        log.verbose(f"     Item[{idx}]: Validating conversion {actual_type.__name__} -> {expected_type.__name__}")
        item_dict = item.model_dump(exclude_none=False, serialize_as_any=True)

        if hasattr(expected_type, "model_validate"):
            try:
                expected_type.model_validate(item_dict)
            except ValidationError as exc:
                formatted_error = format_pydantic_validation_error(exc)
                msg = f"Cannot convert item[{idx}] from {actual_type.__name__} to {expected_type.__name__}: {formatted_error}"
                raise StructuredContentComposerTypeError(msg) from exc

    def _convert_single_item_as_object(self, item: StuffContent, expected_type: type[Any], idx: int) -> StuffContent:
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
            return self._convert_content_for_field(item, expected_type)
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

        # Build context consistently with _run_template_mode in PipeCompose:
        # 1. Working memory context (stuffs as variables)
        context: dict[str, Any] = self.working_memory.generate_context()
        # 2. Runtime params (from PipeRunParams.params)
        if self.runtime_params:
            context.update(**self.runtime_params)
        # 3. Extra context (from PipeCompose.extra_context)
        if self.extra_context:
            context.update(**self.extra_context)

        # Preprocess the template (handles $ -> {{ }} conversion)
        preprocessed = preprocess_template(field_blueprint.template)

        # Render the template using the provided content generator (supports dry run mode)
        return await self.content_generator.make_templated_text(
            context=context,
            template=preprocessed,
            template_category=TemplateCategory.BASIC,
        )

    async def _resolve_nested(self, field_blueprint: ConstructFieldBlueprint, field_name: str) -> StuffContent:
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

        # Create a new composer for the nested structure, passing through runtime params, extra context, and content generator
        nested_composer = StructuredContentComposer(
            construct_blueprint=field_blueprint.nested,
            working_memory=self.working_memory,
            output_class=nested_class,
            runtime_params=self.runtime_params,
            extra_context=self.extra_context,
            content_generator=self.content_generator,
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
            annotation = field_info.annotation
            # Handle Optional types (both `Optional[X]` and Python 3.10+ `X | None` syntax)
            # We need to specifically detect Optional types, not all generic types.
            # - Optional[X] has origin Union and type(None) in args
            # - X | None (Python 3.10+) has origin types.UnionType and type(None) in args
            # Other generic types like list[X] should NOT be unwrapped.
            origin = get_origin(annotation)
            if origin is Union or origin is types.UnionType:
                args = get_args(annotation)
                if type(None) in args:
                    # It's an Optional type, get the non-None type
                    non_none_args = [arg for arg in args if arg is not type(None)]
                    if non_none_args:
                        annotation = non_none_args[0]
            return annotation  # type: ignore[return-value]
        else:
            msg = f"Cannot determine class for nested field '{field_name}' in {self.output_class.__name__}"
            raise StructuredContentComposerTypeError(msg)
