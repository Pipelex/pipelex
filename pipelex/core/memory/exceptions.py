from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.tools.misc.exceptions import ContextProviderError


class WorkingMemoryFactoryError(PipelexError):
    pass


class WorkingMemoryError(PipelexError):
    pass


class WorkingMemoryConsistencyError(WorkingMemoryError):
    pass


class WorkingMemoryVariableError(WorkingMemoryError, ContextProviderError):
    pass


class WorkingMemoryTypeError(WorkingMemoryVariableError):
    pass


class WorkingMemoryStuffAttributeNotFoundError(WorkingMemoryVariableError):
    pass


class WorkingMemoryStuffNotFoundError(WorkingMemoryVariableError):
    # Not classified as the caller's fault: a step that names a variable nothing produces, a batch
    # over one included, is refused when the bundle loads, so a miss at run time is the runtime's own
    # bookkeeping going wrong, not a mistake in the caller's method.
    def __init__(self, message: str, variable_name: str, pipe_code: str | None = None, concept_code: str | None = None):
        super().__init__(message, variable_name)
        self.pipe_code = pipe_code
        self.concept_code = concept_code


class InputShapingError(PipelexError):
    """Base for signature-driven input-shaping failures (Smart Inputs, D4).

    Every subclass describes a fault in the *caller's own* provided inputs — the input name,
    the declared concept, what was provided, and the expected shape rendered from the pipe's
    signature. ``error_domain = INPUT`` (the caller can fix it) and ``_authors_caller_facing_message``
    (the copy names only the caller's inputs and method, so it survives STRICT disclosure).

    Each subclass sets a per-instance ``user_action`` (advice tailored to the specific failure)
    rather than a class-level one, because the actionable fix differs per failure mode.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(self, message: str, *, variable_name: str, user_action: UserAction | None = None):
        self.variable_name = variable_name
        if user_action is not None:
            self.user_action = user_action
        super().__init__(message)


class WrongScalarKindError(InputShapingError):
    """A provided bare value has the wrong JSON kind for the declared concept (D5).

    E.g. a string for a Number-refining input, a boolean for a Text input. No cross-type parsing
    is attempted — JSON already distinguishes scalars — so the mismatch is a hard error.
    """

    @classmethod
    def make(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        expected_kind: str,
        provided_description: str,
        expected_shape: str,
    ) -> "WrongScalarKindError":
        message = (
            f"Input '{variable_name}' declares concept '{declared_concept_ref}', which expects {expected_kind}, "
            f"but you provided {provided_description}.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(kind=UserActionKind.CHANGE_INPUT, detail=f"Provide {expected_kind} for input '{variable_name}'.")
        return cls(message, variable_name=variable_name, user_action=user_action)


class ListWhereSingularError(InputShapingError):
    """A list was provided where the signature declares a single value (D2)."""

    @classmethod
    def make(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        provided_description: str,
        expected_shape: str,
    ) -> "ListWhereSingularError":
        message = (
            f"Input '{variable_name}' declares a single '{declared_concept_ref}', but you provided {provided_description}. "
            f"A list where a single value is declared is ambiguous.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Provide a single value for input '{variable_name}', or declare it as a list ('{declared_concept_ref}[]') in the method.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)


class MultiplicityCountMismatchError(InputShapingError):
    """A fixed-count list input received the wrong number of items (D2)."""

    @classmethod
    def make(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        expected_count: int,
        provided_count: int,
        expected_shape: str,
    ) -> "MultiplicityCountMismatchError":
        message = (
            f"Input '{variable_name}' declares exactly {expected_count} items of '{declared_concept_ref}' "
            f"('{declared_concept_ref}[{expected_count}]'), but you provided {provided_count}.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Provide exactly {expected_count} items for input '{variable_name}'.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)


class StructureValidationError(InputShapingError):
    """A provided value failed to validate against the declared concept's structure (D4/D5).

    Covers a structured-concept dict missing a required field, a malformed ``{"url": ...}`` for a
    file concept, a non-ISO string for a Date concept — any value that is the right JSON kind but
    does not build into the declared content class. It also covers the bare values an input reading
    values by their own shape refuses (R8): one it has no reading for, such as a list of plain objects
    at a ``Dynamic`` input, where the fix is usually the input's declaration; one it reads as a concept
    the input does not accept, such as a string at a ``Choice`` input; the content of the declared
    concept sent without the envelope that names it, such as ``{"choice": "billing"}`` at a ``Choice``
    input; and a scalar at an input of a verdict native, such as a bare level at a ``Rating`` input.
    The last three are fixed in the value, sent in the expected shape.
    """

    @classmethod
    def make(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        reason: str,
        expected_shape: str,
    ) -> "StructureValidationError":
        message = f"Input '{variable_name}' could not be built as '{declared_concept_ref}': {reason}\nExpected shape:\n{expected_shape}"
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Fix input '{variable_name}' so it matches the expected shape for '{declared_concept_ref}'.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)

    @classmethod
    def make_for_unreadable_bare_value(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        provided_description: str,
        suggested_declaration: str,
        expected_shape: str,
    ) -> "StructureValidationError":
        """The refusal for a bare value that an input of this concept, which reads a value by its own shape, cannot read.

        The advice names the declaration to change rather than an envelope, because the person who
        sent the value usually also declared the input, and an envelope helps only a caller who knows
        a concept both compatible with the input and able to hold the value. `suggested_declaration`
        is the one that reads this value: `'JSON'` for an object, `'JSON[]'` for a list of objects,
        `'Anything'` or `'Anything[]'` for anything else.
        """
        message = (
            f"Input '{variable_name}' could not be built as '{declared_concept_ref}': you provided {provided_description}, "
            f"and an input of this concept reads a bare value by its own shape, with no reading for this one.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=(
                f"Declare input '{variable_name}' in the method as {suggested_declaration}, "
                "or as a concept with a structure that describes the value."
            ),
        )
        return cls(message, variable_name=variable_name, user_action=user_action)

    @classmethod
    def make_for_content_without_its_envelope(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        provided_description: str,
        expected_shape: str,
    ) -> "StructureValidationError":
        """The refusal for the declared concept's own content, sent bare at an input that takes it in its envelope.

        An input of a native read bottom-up takes its value in the `{"concept", "content"}` envelope, so
        `{"choice": "billing"}` at a `Choice` input has no reading. The value is right in substance and
        wrong in form, so the advice is the expected shape: a declaration that reads the bare object, such
        as `JSON`, would discard the concept the method asked for.
        """
        message = (
            f"Input '{variable_name}' could not be built as '{declared_concept_ref}': you provided {provided_description}, "
            f"which is the content of a '{declared_concept_ref}' without the envelope that names its concept, "
            f"and an input of this concept takes its value in that envelope.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Send input '{variable_name}' in the expected shape, which names its concept and spells out its content.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)

    @classmethod
    def make_for_scalar_at_a_verdict_input(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        provided_description: str,
        expected_shape: str,
    ) -> "StructureValidationError":
        """The refusal for a scalar, or a list of scalars, at an input of a verdict native.

        A `Choice` or a `Rating` input takes its value in the `{"concept", "content"}` envelope, and a
        caller naturally sends its key or its level alone, as a `Number` or a `YesNo` input would take
        it. A verdict is more than its key or its level, so the value has no reading, and a declaration
        that reads it, such as `Anything`, would discard the verdict the method branches on: the advice
        is the expected shape.
        """
        message = (
            f"Input '{variable_name}' could not be built as '{declared_concept_ref}': you provided {provided_description}, "
            f"and an input of this concept takes its value in the envelope that names its concept, with its content spelled out."
            f"\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Send input '{variable_name}' in the expected shape, which names its concept and spells out its content.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)

    @classmethod
    def make_for_bare_value_of_another_concept(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        provided_description: str,
        built_concept_ref: str,
        expected_shape: str,
    ) -> "StructureValidationError":
        """The refusal for a bare value the bottom-up fallback reads as a concept the input does not accept.

        An input of a native read bottom-up (`Html`, `Page`, `SearchResult`, `Choice`, `Rating`) takes
        its value in its envelope, so a bare string there reads as a `Text`, which is no such native.
        The value is right in substance and wrong in form, so the advice is the expected shape, not a
        different declaration.
        """
        message = (
            f"Input '{variable_name}' could not be built as '{declared_concept_ref}': you provided {provided_description}, "
            f"which reads as '{built_concept_ref}', and a '{built_concept_ref}' is not a '{declared_concept_ref}'.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Send input '{variable_name}' in the expected shape, which names its concept and spells out its content.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)


class ExplicitConceptIncompatibleError(InputShapingError):
    """An explicit envelope/object names a concept incompatible with the declared one (D6).

    The escape-hatch ``{"concept": C, "content": ...}`` (and a directly-provided ``StuffContent``)
    is now checked: ``C`` must be compatible with — refine or equal — the declared concept.
    """

    @classmethod
    def make(
        cls,
        *,
        variable_name: str,
        declared_concept_ref: str,
        provided_concept_ref: str,
        expected_shape: str,
    ) -> "ExplicitConceptIncompatibleError":
        message = (
            f"Input '{variable_name}' declares concept '{declared_concept_ref}', but you provided a value typed as "
            f"'{provided_concept_ref}', which is not compatible with it.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Provide a '{declared_concept_ref}' (or a concept that refines it) for input '{variable_name}'.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)


class UnknownInputNameError(InputShapingError):
    """A provided input name is not declared by the pipe's signature (D8).

    With a signature in hand, an unknown name is a typo detector: the run fails loudly and lists
    the declared names, instead of silently carrying an input that is never read.
    """

    @classmethod
    def make(cls, *, variable_name: str, declared_names: list[str]) -> "UnknownInputNameError":
        declared_display = ", ".join(f"'{name}'" for name in declared_names) if declared_names else "(none)"
        message = f"Input '{variable_name}' is not declared by this pipe. Declared inputs: {declared_display}."
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Remove input '{variable_name}' or rename it to one of the declared inputs: {declared_display}.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)


class NullInputError(InputShapingError):
    """A provided input value is ``null`` at the top level (D9).

    Absence is expressed by *omitting* the key (Optionals), never by a null value, so a top-level
    null is a hard error rather than a silently-dropped or mis-shaped input.
    """

    @classmethod
    def make(cls, *, variable_name: str, declared_concept_ref: str, expected_shape: str) -> "NullInputError":
        message = (
            f"Input '{variable_name}' (declared '{declared_concept_ref}') was provided as null. "
            f"Absence is expressed by omitting the key, not by a null value.\nExpected shape:\n{expected_shape}"
        )
        user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=f"Provide a value for input '{variable_name}', or omit the key entirely if the input is optional.",
        )
        return cls(message, variable_name=variable_name, user_action=user_action)
