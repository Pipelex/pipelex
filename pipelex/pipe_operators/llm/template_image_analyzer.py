"""Service for analyzing templates to find image references.

This module provides the TemplateImageAnalyzer class which examines Jinja2 templates
to determine which variables reference images (directly or nested) and how they
should be extracted at runtime.
"""

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_native_concept, get_required_concept
from pipelex.pipe_operators.llm.exceptions import PipeLLMFactoryError
from pipelex.pipe_operators.llm.image_reference import ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.jinja2_models import Jinja2FilterName
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_variable_references
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class WithImagesFilterError(PipeLLMFactoryError):
    """Raised when | with_images is used on a type without nested images."""


class UnusedInputError(PipeLLMFactoryError):
    """Raised when an input is declared but never referenced in the template."""


class TemplateImageAnalyzer:
    """Analyzes templates to find image references and validate their usage.

    This class:
    1. Parses templates to find variable references with their filters
    2. Resolves each variable's type from declared inputs
    3. Determines which variables reference images (directly or via | with_images)
    4. Validates that | with_images is only used on types with nested images
    5. Returns a list of ImageReference objects describing how to extract images
    """

    @classmethod
    def analyze_template_for_images(
        cls,
        template_source: str,
        input_specs: dict[str, str],
        domain_code: str,
    ) -> list[ImageReference]:
        """Analyze a template to find image references.

        Args:
            template_source: The Jinja2 template source
            input_specs: Mapping of variable names to concept codes (e.g., {"page": "Page"})
            domain_code: The domain code for resolving concepts

        Returns:
            List of ImageReference objects describing how to extract images

        Raises:
            WithImagesFilterError: If | with_images is used on a type without nested images
        """
        # Preprocess template (convert @variable, $variable syntax)
        preprocessed = preprocess_template(template_source)

        # Parse template to get variable references with filters
        variable_refs = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=preprocessed,
        )

        image_references: list[ImageReference] = []

        for var_ref in variable_refs:
            # Get the root variable name (for dotted paths like "doc.cover")
            root_var = get_root_from_dotted_path(var_ref.path)

            # Skip if the root variable is not in declared inputs
            if root_var not in input_specs:
                continue

            # Parse the input spec to get multiplicity info (e.g., "Image[]" -> concept="Image", multiplicity=True)
            input_spec = input_specs[root_var]
            parsed_input = parse_concept_with_multiplicity(input_spec)
            has_multiplicity = parsed_input.multiplicity is not None and parsed_input.multiplicity is not False

            # Resolve the concept for this variable
            concept = cls._resolve_concept(input_spec, domain_code)

            # Determine what type the variable path resolves to
            # For nested paths like "doc.cover", we need to traverse the structure
            resolved_type_info = cls._resolve_variable_type(var_ref.path, root_var, concept)
            if resolved_type_info is None:
                continue

            is_image_content, is_list_of_images, has_nested_images, nested_paths = resolved_type_info

            # If the input has multiplicity brackets (e.g., Image[]), treat single images as lists
            if has_multiplicity and is_image_content:
                is_image_content = False
                is_list_of_images = True

            # Check if | with_images filter is used
            has_with_images_filter = Jinja2FilterName.WITH_IMAGES in var_ref.filters

            if has_with_images_filter:
                # Validate: | with_images should only be used on types with nested images
                if not has_nested_images:
                    msg = (
                        f"Filter '| with_images' used on variable '{var_ref.path}' "
                        f"but the type has no nested images. Remove the filter or use a type with nested images."
                    )
                    raise WithImagesFilterError(msg)

                image_references.append(
                    ImageReference(
                        variable_path=var_ref.path,
                        kind=ImageReferenceKind.NESTED,
                        nested_image_paths=nested_paths,
                    )
                )
            elif is_image_content:
                # Direct ImageContent reference
                image_references.append(
                    ImageReference(
                        variable_path=var_ref.path,
                        kind=ImageReferenceKind.DIRECT,
                    )
                )
            elif is_list_of_images:
                # Direct list[ImageContent] reference
                image_references.append(
                    ImageReference(
                        variable_path=var_ref.path,
                        kind=ImageReferenceKind.DIRECT_LIST,
                    )
                )
            # If the variable has nested images but no | with_images filter,
            # we don't include them (text-only rendering)

        return image_references

    @classmethod
    def validate_unused_inputs(
        cls,
        template_sources: list[str],
        input_specs: dict[str, str],
    ) -> None:
        """Validate that all declared inputs are used in at least one template.

        Args:
            template_sources: List of template sources to check
            input_specs: Mapping of variable names to concept codes

        Raises:
            UnusedInputError: If any declared input is never referenced
        """
        referenced_roots: set[str] = set()

        for template_source in template_sources:
            preprocessed = preprocess_template(template_source)
            variable_refs = detect_jinja2_variable_references(
                template_category=TemplateCategory.LLM_PROMPT,
                template_source=preprocessed,
            )
            for var_ref in variable_refs:
                root_var = get_root_from_dotted_path(var_ref.path)
                referenced_roots.add(root_var)

        declared_inputs = set(input_specs.keys())
        unused_inputs = declared_inputs - referenced_roots

        if unused_inputs:
            msg = f"Inputs declared but never used in templates: {sorted(unused_inputs)}"
            raise UnusedInputError(msg)

    @classmethod
    def _resolve_concept(cls, concept_ref_or_code: str, domain_code: str) -> Concept:
        """Resolve a concept reference to a Concept object.

        Handles multiplicity brackets like Image[] or Text[3] by stripping them.
        """
        # Strip multiplicity brackets (e.g., "Image[]" -> "Image")
        parsed = parse_concept_with_multiplicity(concept_ref_or_code)
        clean_concept_ref = parsed.concept

        domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_ref_or_code(
            domain_code=domain_code,
            concept_ref_or_code=clean_concept_ref,
        )
        return get_required_concept(
            concept_ref=ConceptFactory.make_concept_ref_with_domain(
                domain_code=domain_and_code.domain_code,
                concept_code=domain_and_code.concept_code,
            ),
        )

    @classmethod
    def _resolve_variable_type(
        cls,
        var_path: str,
        root_var: str,
        root_concept: Concept,
    ) -> tuple[bool, bool, bool, list[str] | None] | None:
        """Resolve what type a variable path points to.

        Args:
            var_path: Full variable path (e.g., "doc.cover", "pages")
            root_var: Root variable name (e.g., "doc", "pages")
            root_concept: The concept for the root variable

        Returns:
            Tuple of (is_image_content, is_list_of_images, has_nested_images, nested_paths)
            or None if type cannot be resolved
        """
        native_image_concept = get_native_concept(NativeConceptCode.IMAGE)

        # For simple variable references (no dots after root)
        if var_path == root_var:
            # Check if it's directly an ImageContent
            is_image = Concept.are_concept_compatible(
                concept_1=root_concept,
                concept_2=native_image_concept,
                strict=True,
            )
            if is_image:
                return (True, False, False, None)

            # Check if it has nested images (loose compatibility)
            has_nested = Concept.are_concept_compatible(
                concept_1=root_concept,
                concept_2=native_image_concept,
                strict=False,
            )
            nested_paths: list[str] | None = None
            if has_nested:
                nested_paths = root_concept.search_for_nested_image_fields_in_structure_class()
                if not nested_paths:
                    has_nested = False

            return (False, False, has_nested, nested_paths)

        # For dotted paths (e.g., "doc.cover"), we need to traverse the structure
        # This is more complex - for now we'll check if the path ends with an image field
        # by examining the nested image paths of the root concept
        nested_paths = root_concept.search_for_nested_image_fields_in_structure_class()

        # Check if the relative path (after root) matches any nested image path
        relative_path = var_path[len(root_var) + 1 :] if var_path.startswith(f"{root_var}.") else None
        if relative_path and nested_paths:
            # Exact match means it's a direct image reference
            if relative_path in nested_paths:
                return (True, False, False, None)
            # Check if any nested path starts with this path (nested structure with images)
            matching_paths = [p for p in nested_paths if p.startswith(relative_path)]
            if matching_paths:
                # It's a structure with nested images
                sub_paths = [p[len(relative_path) + 1 :] for p in matching_paths if p != relative_path]
                return (False, False, bool(sub_paths), sub_paths or None)

        return None
