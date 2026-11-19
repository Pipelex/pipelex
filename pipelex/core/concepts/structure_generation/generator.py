"""Build a concept's structure class from its structure blueprint, with `pydantic.create_model`.

The class is built from data: the blueprint's fields are resolved through the neutral resolved-field layer shared by
every emitter (`resolve_structure_fields`), each resolved type is mapped to a Python annotation, and `create_model`
builds the class from those annotations and their `Field` definitions. No Python source is written or run, so a name
a field is given shadows nothing and an authored text is only ever a value: a description, a choice, a default.

The class has the shape the `python-structures` codegen emitter writes for the same concept, which a parity test
holds the two to: the same JSON schema.
"""

import copy
from datetime import date, datetime, time
from typing import Any, Literal, Optional, cast

from mthds.protocol.problem.registry import CoreCode
from pydantic import Field, create_model

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.concepts.helpers import extract_concept_code_from_concept_ref_or_code, make_qualified_structure_class_name
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.resolved_fields import ResolvedField, ResolvedType, ResolvedTypeKind, resolve_structure_fields
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError, ConceptStructureValidationError
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.non_null_any import NonNullAny
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.system.registries.class_registry_access import get_class_registry
from pipelex.tools.misc.python_literals import class_doc_value

# The module a generated class names as its own, which marks it as importable from no module.
_GENERATED_CLASS_MODULE = "builtins"


class StructureGenerator:
    """Build Pydantic BaseModel classes from concept structure blueprints."""

    def __init__(self, local_domain: str | None = None):
        """Initialize the StructureGenerator.

        Args:
            local_domain: Optional domain to use when resolving bare concept refs
                (refs without a domain prefix, e.g. "ColorPalette") to their
                domain-qualified structure class name.
        """
        self.local_domain = local_domain
        # The classes the class being built refers to by forward reference, by name, each with the concept ref it was
        # spelled from.
        self._forward_refs: dict[str, str] = {}

    def generate_from_structure_blueprint(
        self,
        *,
        class_name: str,
        structure_blueprint: dict[str, ConceptStructureBlueprint],
        base_class_name: str | None = None,
        description: str = "",
    ) -> type[StuffContent]:
        """Build the structure class a structure blueprint describes.

        Args:
            class_name: Name of the class to build
            structure_blueprint: Dictionary mapping field names to their ConceptStructureBlueprint definitions
            base_class_name: Optional base class name to inherit from (defaults to StructuredContent): a native
                content class, or a class registered in the class registry
            description: Description for the class docstring (uses class_name if empty)

        Returns:
            The class, whose forward references to other concepts' classes are resolved by the library's rebuild

        Raises:
            ConceptStructureGeneratorError: If a field is named like a class the structure refers to, or the class
                cannot be built, its cause then being what pydantic raised, or a `ConceptStructureValidationError`
                when the base class is not found or is not a content class
        """
        self._forward_refs = {}
        try:
            base_class = self._base_class(base_class_name=base_class_name)
        except ConceptStructureValidationError as exc:
            msg = f"Error building the structure class '{class_name}': {exc}"
            raise ConceptStructureGeneratorError(msg) from exc
        resolved_fields = resolve_structure_fields(structure_blueprint, local_domain=self.local_domain)
        # Typed `Any` as `create_model` takes its fields: by keyword, beside its own `__`-led options.
        field_definitions: dict[str, Any] = {resolved_field.name: self._field_definition(resolved_field) for resolved_field in resolved_fields}
        self._refuse_fields_named_like_forward_refs(class_name=class_name, field_names=frozenset(field_definitions))

        # pydantic writes the docstring to the schema's description through `inspect.cleandoc`, so the value set is the
        # one that reads back as the authored text.
        doc = class_doc_value(description or f"Generated {class_name} class")
        try:
            # mypy's pydantic plugin types the class `create_model` returns as a new class of its own, pyright as its base.
            the_class = cast(  # pyright: ignore[reportUnnecessaryCast]
                "type[StuffContent]",
                create_model(class_name, __base__=base_class, __doc__=doc, __module__=_GENERATED_CLASS_MODULE, **field_definitions),
            )
        except Exception as exc:
            # Unbounded code (case 2): building the class runs the metaclass and the subclass hooks of its base, which
            # may be a class registered from a method's own Python, so its exception surface cannot be enumerated.
            msg = f"Error building the structure class '{class_name}': {exc}"
            raise ConceptStructureGeneratorError(msg) from exc
        # `create_model` leaves an empty docstring unset, and `inspect.getdoc` would then read the base's.
        the_class.__doc__ = doc
        return the_class

    ############################################################
    # Private methods
    ############################################################

    @classmethod
    def _base_class(cls, *, base_class_name: str | None) -> type[StuffContent]:
        """The class the built class inherits from: the native content class or the registered class of that name."""
        if not base_class_name:
            return StructuredContent
        found_class: type | None
        if NativeConceptCode.is_native_structure_class(base_class_name):
            found_class = NativeConceptCode.get_native_structure_class(base_class_name)
            if found_class is None:
                msg = f"Native structure class '{base_class_name}' not found"
                raise ConceptStructureGeneratorError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
        else:
            found_class = get_class_registry().get_class(name=base_class_name)
            if found_class is None:
                msg = f"Base class '{base_class_name}' not found in native classes or class registry"
                raise ConceptStructureValidationError(msg)
        if not issubclass(found_class, StuffContent):
            msg = (
                f"Base class '{base_class_name}' does not inherit from StuffContent. MRO: {[mro_class.__name__ for mro_class in found_class.__mro__]}"
            )
            raise ConceptStructureValidationError(msg)
        return found_class

    def _refuse_fields_named_like_forward_refs(self, *, class_name: str, field_names: frozenset[str]) -> None:
        """Refuse a field named like a class the built class refers to by forward reference.

        A forward reference is a string pydantic resolves by name when it builds the class, reading the class namespace
        first, where every field is bound to its `FieldInfo`. So a field named like the class it or another field refers
        to (`repro__Person`, the class of the concept `repro.Person`) would be read in place of that class. The name of a
        forward reference is the key the loaded classes are found by, so such a field is refused.

        Raises:
            ConceptStructureGeneratorError: When a field has the name of a class the built class refers to, its
                `finding` naming the field and the concept.
        """
        shadowed_class_names = sorted(field_names & self._forward_refs.keys())
        if not shadowed_class_names:
            return
        findings = [
            f"its field '{shadowed_class_name}' has the name of the Python class of the concept '{self._forward_refs[shadowed_class_name]}', "
            "which the structure refers to"
            for shadowed_class_name in shadowed_class_names
        ]
        finding = "; ".join(findings)
        msg = f"Cannot generate the structure class '{class_name}': {finding}."
        raise ConceptStructureGeneratorError(msg).with_params(finding=finding)

    def _field_definition(self, resolved_field: ResolvedField) -> tuple[Any, Any]:
        """The annotation and the `Field` of one resolved field, as `create_model` takes them."""
        annotation = self._annotation(resolved_field.resolved_type)

        # Only a field that may hold nothing admits `None`: by the standard's rule, one that is neither required nor
        # defaulted. A binding step reading a field derives its absence from that rule alone, so a required or
        # defaulted field holding `None` would be an absence its readers ruled out: a defaulted field is therefore
        # `X = Field(default=…)`, and an explicit `null` for it is refused rather than kept. `Optional` is spelled
        # rather than `| None` because a forward reference is a string, which does not implement `|`.
        if resolved_field.may_hold_nothing:
            annotation = Optional[annotation]  # ruff: ignore[non-pep604-annotation-optional]
        elif annotation is Any:
            # `Any` admits `None` by itself, so an open field that never holds nothing (one naming `native.Anything`, or
            # of an unspecified type) takes the annotation that refuses it.
            annotation = NonNullAny

        default_value = resolved_field.default_value
        if resolved_field.required:
            # The blueprint validator rejects `required = true` beside a `default_value` (E3), so a required field can
            # never carry a default here: the invariant is asserted loudly instead of one of the two being dropped.
            if default_value is not None:
                msg = (
                    f"Field '{resolved_field.name}' is required AND carries default_value {default_value!r} — "
                    f"the blueprint validator rejects this pair, so reaching the generator with it is a bug."
                )
                raise ConceptStructureGeneratorError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
            return annotation, Field(..., description=resolved_field.description)
        # The default is copied, so the class never shares a mutable value with the blueprint it was built from.
        return annotation, Field(default=copy.deepcopy(default_value), description=resolved_field.description)

    def _annotation(self, resolved_type: ResolvedType) -> Any:
        """Map a neutral resolved type to a Python annotation."""
        match resolved_type.kind:
            case ResolvedTypeKind.TEXT:
                return str
            case ResolvedTypeKind.NUMBER:
                return float
            case ResolvedTypeKind.INTEGER:
                return int
            case ResolvedTypeKind.BOOLEAN:
                return bool
            case ResolvedTypeKind.DATE:
                return date
            case ResolvedTypeKind.DATETIME:
                return datetime
            case ResolvedTypeKind.TIME:
                return time
            case ResolvedTypeKind.LITERAL:
                return Literal[tuple(resolved_type.choices or ())]  # pyright: ignore[reportInvalidTypeArguments]
            case ResolvedTypeKind.CONCEPT:
                return self._concept_annotation(resolved_type)
            case ResolvedTypeKind.LIST:
                item_annotation = self._annotation(resolved_type.item) if resolved_type.item else Any
                return list[item_annotation]  # type: ignore[valid-type]
            case ResolvedTypeKind.DICT:
                key_annotation = self._annotation(resolved_type.key) if resolved_type.key else str
                value_annotation = self._annotation(resolved_type.value) if resolved_type.value else Any
                return dict[key_annotation, value_annotation]  # type: ignore[valid-type]
            case ResolvedTypeKind.ANY:
                return Any

    def _concept_annotation(self, resolved_type: ResolvedType) -> Any:
        """Resolve a CONCEPT node to a Python annotation.

        The concept ref is already normalized by the resolved-field layer (natives flagged, bare refs promoted to the
        local domain). Returns:
        - for native concepts: the native content class, or `Any` for `native.Anything`, which has no content class;
        - otherwise: the domain-qualified class name, a forward reference the library's rebuild resolves.
        """
        concept_ref = resolved_type.concept_ref
        if not concept_ref:
            return Any

        if resolved_type.is_native:
            native_concept_code = extract_concept_code_from_concept_ref_or_code(concept_ref)
            try:
                native_code = NativeConceptCode(native_concept_code)
            except ValueError:
                native_code = None
            if native_code is not None:
                # `native.Anything` has no content class: a field holding it holds any value, and a forward reference
                # to its code would name a class no namespace has.
                return native_code.structure_class or Any

        concept_code = extract_concept_code_from_concept_ref_or_code(concept_ref)
        parsed_ref = QualifiedRef.parse_stripping_cross_package(concept_ref)
        if parsed_ref.domain_path and not NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
            referenced_class_name = make_qualified_structure_class_name(domain_code=parsed_ref.domain_path, concept_code=concept_code)
        else:
            referenced_class_name = concept_code
        self._forward_refs[referenced_class_name] = concept_ref
        return referenced_class_name
