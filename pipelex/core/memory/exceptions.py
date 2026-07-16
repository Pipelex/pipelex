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
    does not build into the declared content class.
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
