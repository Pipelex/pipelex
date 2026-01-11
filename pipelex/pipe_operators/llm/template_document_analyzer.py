"""Service for analyzing templates to find document references.

This module provides the TemplateDocumentAnalyzer class which examines Jinja2 templates
to determine which variables reference documents (directly or as lists) and how they
should be extracted at runtime.
"""

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_native_concept, get_required_concept
from pipelex.pipe_operators.llm.document_reference import DocumentReference, DocumentReferenceKind
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_variable_references
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class TemplateDocumentAnalyzer:
    """Analyzes templates to find document references and validate their usage.

    This class:
    1. Parses templates to find variable references with their filters
    2. Resolves each variable's type from declared inputs
    3. Determines which variables reference documents (directly or as lists)
    4. Returns a list of DocumentReference objects describing how to extract documents
    """

    @classmethod
    def analyze_template_for_documents(
        cls,
        template_source: str,
        input_specs: dict[str, str],
        domain_code: str,
    ) -> list[DocumentReference]:
        """Analyze a template to find document references.

        Args:
            template_source: The Jinja2 template source
            input_specs: Mapping of variable names to concept codes (e.g., {"doc": "Document"})
            domain_code: The domain code for resolving concepts

        Returns:
            List of DocumentReference objects describing how to extract documents
        """
        # Preprocess template (convert @variable, $variable syntax)
        preprocessed = preprocess_template(template_source)

        # Parse template to get variable references with filters
        variable_refs = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=preprocessed,
        )

        document_references: list[DocumentReference] = []

        for var_ref in variable_refs:
            # Get the root variable name (for dotted paths like "submission.pdf")
            root_var = get_root_from_dotted_path(var_ref.path)

            # Skip if the root variable is not in declared inputs
            if root_var not in input_specs:
                continue

            # Parse the input spec to get multiplicity info (e.g., "Document[]" -> concept="Document", multiplicity=True)
            input_spec = input_specs[root_var]
            parsed_input = parse_concept_with_multiplicity(input_spec)
            has_multiplicity = parsed_input.multiplicity is not None and parsed_input.multiplicity is not False

            # Resolve the concept for this variable
            concept = cls._resolve_concept(input_spec, domain_code)

            # Determine what type the variable path resolves to
            resolved_type_info = cls._resolve_variable_type(var_ref.path, root_var, concept)
            if resolved_type_info is None:
                continue

            is_document_content, is_list_of_documents = resolved_type_info

            # If the input has multiplicity brackets (e.g., Document[]), treat single documents as lists
            if has_multiplicity and is_document_content:
                is_document_content = False
                is_list_of_documents = True

            if is_document_content:
                # Direct DocumentContent reference
                document_references.append(
                    DocumentReference(
                        variable_path=var_ref.path,
                        kind=DocumentReferenceKind.DIRECT,
                    )
                )
            elif is_list_of_documents:
                # Direct list[DocumentContent] reference
                document_references.append(
                    DocumentReference(
                        variable_path=var_ref.path,
                        kind=DocumentReferenceKind.DIRECT_LIST,
                    )
                )

        return document_references

    @classmethod
    def _resolve_concept(cls, concept_ref_or_code: str, domain_code: str) -> Concept:
        """Resolve a concept reference to a Concept object.

        Handles multiplicity brackets like Document[] or Document[3] by stripping them.
        """
        # Strip multiplicity brackets (e.g., "Document[]" -> "Document")
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
    ) -> tuple[bool, bool] | None:
        """Resolve what type a variable path points to.

        Args:
            var_path: Full variable path (e.g., "doc", "submission.pdf")
            root_var: Root variable name (e.g., "doc", "submission")
            root_concept: The concept for the root variable

        Returns:
            Tuple of (is_document_content, is_list_of_documents)
            or None if type cannot be resolved
        """
        native_document_concept = get_native_concept(NativeConceptCode.DOCUMENT)

        # For simple variable references (no dots after root)
        if var_path == root_var:
            # Check if it's directly a DocumentContent
            is_document = Concept.are_concept_compatible(
                concept_1=root_concept,
                concept_2=native_document_concept,
                strict=True,
            )
            if is_document:
                return (True, False)

            # Document doesn't have nested documents concept, so no nested checking needed
            return None

        # For dotted paths, documents are terminal so we don't support nested paths
        return None
