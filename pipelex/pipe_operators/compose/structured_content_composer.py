"""Composer for creating StructuredContent from ConstructBlueprint.

The StructuredContentComposer takes a ConstructBlueprint and WorkingMemory,
resolves all fields according to their composition methods, and produces
a populated StructuredContent instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, get_args, get_origin

from pipelex import log, pretty_print
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.hub import get_content_generator
from pipelex.pipe_operators.compose.construct_field_blueprint import ConstructFieldBlueprint, ConstructFieldMethod

if TYPE_CHECKING:
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.core.stuffs.stuff_content import StuffContent
    from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint


class StructuredContentComposer:
    """Composes a StructuredContent instance from a ConstructBlueprint.

    The composer resolves each field in the blueprint according to its method:
    - FIXED: Use the literal value directly
    - FROM_VAR: Get value from working memory via path
    - TEMPLATE: Render Jinja2 template with working memory context
    - NESTED: Recursively compose a nested StructuredContent

    Attributes:
        construct_blueprint: The blueprint defining how to compose each field
        working_memory: The working memory containing input variables
        output_class: The StructuredContent subclass to instantiate
    """

    def __init__(
        self,
        construct_blueprint: ConstructBlueprint,
        working_memory: WorkingMemory,
        output_class: type[StuffContent],
    ):
        self.construct_blueprint = construct_blueprint
        self.working_memory = working_memory
        self.output_class = output_class

    def compose(self) -> StuffContent:
        """Compose the StructuredContent synchronously.

        Note: If templates are used, this method will run async code synchronously
        which may not work in all contexts. Prefer compose_async() when templates
        are involved.

        Returns:
            Populated StructuredContent instance
        """
        import asyncio  # noqa: PLC0415

        # Check if we're already in an async context
        try:
            asyncio.get_running_loop()
            # We're in an async context, need to use a different approach
            # Create a new thread to run the async code
            import concurrent.futures  # noqa: PLC0415

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.compose_async())
                return future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.compose_async())

    async def compose_async(self) -> StuffContent:
        """Compose the StructuredContent asynchronously.

        Returns:
            Populated StructuredContent instance
        """
        field_values = await self._resolve_all_fields()

        # DEBUG: Show comprehensive comparison of expected vs actual
        self._debug_log_field_comparison(field_values)

        pretty_print(self.output_class, title="Output class")
        pretty_print(field_values, title="Field values")
        return self.output_class.model_validate(field_values)

    def _debug_log_field_comparison(self, field_values: dict[str, Any]) -> None:
        """Log detailed comparison between expected model fields and resolved values."""
        log.dev("=" * 80)
        log.dev(f"StructuredContentComposer DEBUG for {self.output_class.__name__}")
        log.dev("=" * 80)

        # Get expected fields from the output class
        expected_fields: dict[str, Any] = {}
        if hasattr(self.output_class, "model_fields"):
            for field_name, field_info in self.output_class.model_fields.items():
                expected_fields[field_name] = {
                    "annotation": field_info.annotation,
                    "required": field_info.is_required(),
                }

        log.dev(f"Expected fields from {self.output_class.__name__}:")
        for field_name, field_meta in expected_fields.items():
            log.dev(f"  - {field_name}: {field_meta['annotation']} (required={field_meta['required']})")

        # Blueprint fields
        blueprint_field_names = list(self.construct_blueprint.fields.keys())
        log.dev(f"Blueprint fields: {blueprint_field_names}")

        # Check for missing fields (in expected but not in blueprint)
        expected_names = set(expected_fields.keys())
        blueprint_names = set(blueprint_field_names)
        missing_in_blueprint = expected_names - blueprint_names
        extra_in_blueprint = blueprint_names - expected_names

        if missing_in_blueprint:
            log.warning(f"Fields MISSING in blueprint (expected by {self.output_class.__name__}): {missing_in_blueprint}")
        if extra_in_blueprint:
            log.warning(f"Fields EXTRA in blueprint (not in {self.output_class.__name__}): {extra_in_blueprint}")

        # Resolved values with types
        log.dev("Resolved field values:")
        for field_name, value in field_values.items():
            value_type = type(value).__name__
            expected_type = expected_fields.get(field_name, {}).get("annotation", "UNKNOWN")

            # Check if it's a list type and show item types
            if isinstance(value, list):
                if value:
                    item_types = [type(list_item).__name__ for list_item in value[:3]]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
                    log.dev(f"  - {field_name}: list[{item_types}...] (expected: {expected_type})")
                else:
                    log.dev(f"  - {field_name}: empty list (expected: {expected_type})")
            elif isinstance(value, dict):
                dict_keys = list(value.keys())[:5]  # type: ignore[misc]
                log.dev(f"  - {field_name}: dict with keys {dict_keys} (expected: {expected_type})")
                if "__class__" in value:
                    log.dev(f"    ^ This looks like a serialized object! __class__={value.get('__class__')}")  # pyright: ignore[reportUnknownMemberType]
            else:
                log.dev(f"  - {field_name}: {value_type} (expected: {expected_type})")

            # Type mismatch detection
            if expected_type != "UNKNOWN":
                self._debug_check_type_mismatch(field_name, value, expected_type)

        log.dev("=" * 80)

    def _debug_check_type_mismatch(self, field_name: str, value: Any, expected_type: Any) -> None:
        """Check and log type mismatches."""
        actual_type = type(value)  # type: ignore[misc]

        # Handle generic types like list[X]
        origin = get_origin(expected_type)
        if origin is list:
            args = get_args(expected_type)
            if not isinstance(value, list):
                log.warning(f"    TYPE MISMATCH for '{field_name}': expected list, got {actual_type.__name__}")
                if isinstance(value, dict) and "items" in value:
                    log.warning("    ^ Value is a dict with 'items' key - likely a serialized ListContent!")
            elif args and value:
                expected_item_type = args[0]
                for idx, list_item in enumerate(value[:3]):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
                    if not isinstance(list_item, expected_item_type):
                        log.warning(
                            f"    TYPE MISMATCH for '{field_name}[{idx}]': expected {expected_item_type.__name__}, got {type(list_item).__name__}"  # pyright: ignore[reportUnknownArgumentType]
                        )

    async def _resolve_all_fields(self) -> dict[str, Any]:
        """Resolve all fields in the blueprint to their values.

        Returns:
            Dictionary mapping field names to resolved values
        """
        field_values: dict[str, Any] = {}

        for field_name, field_blueprint in self.construct_blueprint.fields.items():
            field_values[field_name] = await self._resolve_field(field_blueprint, field_name)

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
                return self._resolve_from_var(field_blueprint)

            case ConstructFieldMethod.TEMPLATE:
                return await self._resolve_template(field_blueprint)

            case ConstructFieldMethod.NESTED:
                return await self._resolve_nested(field_blueprint, field_name)

    def _resolve_from_var(self, field_blueprint: ConstructFieldBlueprint) -> Any:
        """Resolve a FROM_VAR field by getting value from working memory.

        Args:
            field_blueprint: The field blueprint with from_path

        Returns:
            The value from working memory
        """
        if not field_blueprint.from_path:
            msg = "from_path is required for FROM_VAR method"
            raise ValueError(msg)

        path = field_blueprint.from_path
        log.dev(f"_resolve_from_var: resolving path '{path}'")

        # Handle dotted paths (e.g., "deal.customer_name")
        if "." in path:
            parts = path.split(".", 1)
            base_name = parts[0]
            attr_path = parts[1]

            stuff = self.working_memory.get_stuff(base_name)
            content: Any = stuff.content
            log.dev(f"  Stuff '{base_name}' content type: {type(content).__name__}")

            # Navigate the attribute path - this is dynamic attribute access at runtime
            current: Any = content
            for attr in attr_path.split("."):
                if hasattr(current, attr):  # pyright: ignore[reportUnknownArgumentType]
                    current = getattr(current, attr)  # pyright: ignore[reportUnknownArgumentType]
                elif isinstance(current, dict) and attr in current:  # pyright: ignore[reportUnknownVariableType]
                    current = current[attr]  # pyright: ignore[reportUnknownVariableType]
                else:
                    msg = f"Cannot resolve path '{path}': attribute '{attr}' not found"
                    raise ValueError(msg)
            log.dev(f"  Resolved value type: {type(current).__name__}")  # pyright: ignore[reportUnknownArgumentType]
            return current  # pyright: ignore[reportUnknownVariableType]
        else:
            # Simple case: just get the stuff's content or text value
            stuff = self.working_memory.get_stuff(path)
            simple_content: Any = stuff.content
            log.dev(f"  Stuff '{path}' content type: {type(simple_content).__name__}")

            # If it's a TextContent, return the text
            from pipelex.core.stuffs.text_content import TextContent  # noqa: PLC0415

            if isinstance(simple_content, TextContent):
                log.dev("  -> Returning TextContent.text (str)")
                return simple_content.text

            # Check if it's a ListContent - extract items for list fields
            from pipelex.core.stuffs.list_content import ListContent  # noqa: PLC0415

            if isinstance(simple_content, ListContent):  # type: ignore[misc]
                log.dev(f"  -> Content is ListContent with {simple_content.nb_items} items")  # type: ignore[misc]
                items_list = simple_content.items  # type: ignore[misc]
                log.dev(f"     Items types: {[type(list_item).__name__ for list_item in items_list[:3]]}")  # type: ignore[misc]
                pretty_print(simple_content, title=f"ListContent for '{path}'")  # type: ignore[misc]

                # WORKAROUND: Convert items to dicts to avoid class identity issues
                # During dry run, polyfactory creates mock objects with __module__="builtins"
                # which causes Pydantic validation to fail when the target field expects
                # a specific class. By converting to dicts, Pydantic can reconstruct
                # the objects using the correct class during model_validate().
                from pipelex.core.stuffs.stuff_content import StuffContent  # noqa: PLC0415

                items_as_dicts: list[Any] = []
                for list_item in items_list:  # type: ignore[misc]
                    if isinstance(list_item, StuffContent):
                        # Convert to dict, excluding internal fields like __class__ and __module__
                        item_dict = list_item.model_dump(exclude_none=False)
                        # Remove kajson metadata that would interfere with Pydantic validation
                        item_dict.pop("__class__", None)
                        item_dict.pop("__module__", None)
                        items_as_dicts.append(item_dict)
                        log.dev(f"     Converted item to dict: {list(item_dict.keys())}")
                    else:
                        items_as_dicts.append(list_item)  # type: ignore[misc]

                log.dev(f"     Returning {len(items_as_dicts)} items as dicts for Pydantic reconstruction")
                return items_as_dicts

            return simple_content  # type: ignore[misc]

    async def _resolve_template(self, field_blueprint: ConstructFieldBlueprint) -> str:
        """Resolve a TEMPLATE field by rendering the Jinja2 template.

        Args:
            field_blueprint: The field blueprint with template

        Returns:
            The rendered template string
        """
        if not field_blueprint.template:
            msg = "template is required for TEMPLATE method"
            raise ValueError(msg)

        # Get context from working memory
        context = self.working_memory.generate_context()

        # Preprocess the template (handles $ -> {{ }} conversion)
        preprocessed = preprocess_template(field_blueprint.template)

        # Render the template
        content_generator = get_content_generator()
        return await content_generator.make_templated_text(
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
            raise ValueError(msg)

        # Get the field type from the output class to determine nested class
        nested_class = self._get_nested_field_class(field_name)

        # Create a new composer for the nested structure
        nested_composer = StructuredContentComposer(
            construct_blueprint=field_blueprint.nested,
            working_memory=self.working_memory,
            output_class=nested_class,
        )

        return await nested_composer.compose_async()

    def _get_nested_field_class(self, field_name: str) -> type[StuffContent]:
        """Get the class for a nested field from the output class's field annotations.

        Args:
            field_name: The name of the nested field

        Returns:
            The class expected for the nested field
        """
        # Get the field info from the Pydantic model
        if hasattr(self.output_class, "model_fields"):
            field_info = self.output_class.model_fields.get(field_name)
            if field_info and field_info.annotation:
                annotation = field_info.annotation
                # Handle Optional types
                if hasattr(annotation, "__origin__"):
                    # It's a generic type like Optional[Address]
                    args = getattr(annotation, "__args__", ())
                    if args:
                        annotation = args[0]
                return annotation  # type: ignore[return-value]

        msg = f"Cannot determine class for nested field '{field_name}' in {self.output_class.__name__}"
        raise ValueError(msg)
