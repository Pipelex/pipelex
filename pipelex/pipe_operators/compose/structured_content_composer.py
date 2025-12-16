"""Composer for creating StructuredContent from ConstructBlueprint.

The StructuredContentComposer takes a ConstructBlueprint and WorkingMemory,
resolves all fields according to their composition methods, and produces
a populated StructuredContent instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
        return self.output_class.model_validate(field_values)

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

        # Handle dotted paths (e.g., "deal.customer_name")
        if "." in path:
            parts = path.split(".", 1)
            base_name = parts[0]
            attr_path = parts[1]

            stuff = self.working_memory.get_stuff(base_name)
            content: Any = stuff.content

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
            return current  # pyright: ignore[reportUnknownVariableType]
        else:
            # Simple case: just get the stuff's content or text value
            stuff = self.working_memory.get_stuff(path)
            simple_content: Any = stuff.content

            # If it's a TextContent, return the text
            from pipelex.core.stuffs.text_content import TextContent  # noqa: PLC0415

            if isinstance(simple_content, TextContent):
                return simple_content.text
            return simple_content

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
