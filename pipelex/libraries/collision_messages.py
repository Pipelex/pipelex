from enum import StrEnum

from mthds.protocol.problem.registry import MethodNameConflictConflict

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData


class DeclarationKind(StrEnum):
    """The kind of declaration a merged library found declared twice."""

    CONCEPT = "concept"
    PIPE = "pipe"


def duplicate_ref_msg(
    *,
    ref_kind: DeclarationKind,
    ref: str,
    existing_source: str | None,
    incoming_source: str | None,
) -> str:
    """Build the error message for a duplicate concept/pipe declaration in a merged library.

    `ref_kind` is the singular noun ("concept" or "pipe"); the plural is formed by appending
    "s". Whether the two declarations live in the same file or different files is derived from
    the two sources, so callers do not pass a separate flag.

    Args:
        ref_kind: The kind of the declaration, whose value is its singular noun.
        ref: The fully qualified ref that is declared twice (e.g. "scoring.compute_score").
        existing_source: Source file of the already-seen declaration, or None if unknown.
        incoming_source: Source file of the colliding declaration, or None if unknown.

    Returns:
        A human-readable error message naming the offending ref and source files.
    """
    noun = ref_kind.capitalize()
    if existing_source is not None and existing_source == incoming_source:
        return f"{noun} '{ref}' is declared twice in the same bundle file: '{existing_source}'. Please remove the duplicate declaration."
    return (
        f"{noun} '{ref}' is declared in two different bundle files: "
        f"'{existing_source or 'unknown'}' and '{incoming_source or 'unknown'}'. "
        f"Please remove one of the declarations or rename one of the {ref_kind}s."
    )


def duplicate_ref_items(
    *,
    ref_kind: DeclarationKind,
    ref: str,
    existing_source: str | None,
    incoming_source: str | None,
) -> list[PipelexBundleBlueprintValidationErrorData]:
    """The faults of a declaration made twice, one per bundle that makes it, for a verdict to locate each in its bundle.

    Each item names the declaration by its qualified ref and the conflict, the parameters of ``method.name_conflict``,
    and is located on its bundle and its declaration, the table that declares it by its bundle-root path
    (``concept.Score``, ``pipe.compute_score``), so the verdict names both bundles: the one that declared it first and
    the one whose declaration was refused. A ref declared twice in one bundle is one item; two declarations whose
    bundles are unknown are two, since nothing shows them to be one bundle's.

    Args:
        ref_kind: The kind of the declaration.
        ref: The qualified ref declared twice, such as ``scoring.Score``.
        existing_source: The bundle of the declaration met first, when known.
        incoming_source: The bundle of the declaration refused, when known.

    Returns:
        The items, the refused declaration's first.
    """
    noun = ref_kind.capitalize()
    domain_code, _, code = ref.rpartition(".")
    params = {"name": ref, "conflict": MethodNameConflictConflict.DUPLICATE_DECLARATION}
    is_one_bundle = existing_source is not None and existing_source == incoming_source
    # Each declaration with the bundle of the other, the refused declaration's first.
    located_declarations = [(incoming_source, existing_source), (existing_source, incoming_source)]
    if is_one_bundle:
        located_declarations = located_declarations[:1]
    items: list[PipelexBundleBlueprintValidationErrorData] = []
    for source, other_source in located_declarations:
        if is_one_bundle:
            message = f"{noun} '{ref}' is declared twice in this bundle."
        else:
            message = f"{noun} '{ref}' is declared here and in '{other_source or 'unknown'}'."
        match ref_kind:
            case DeclarationKind.CONCEPT:
                items.append(
                    PipelexBundleBlueprintValidationErrorData(
                        source=source,
                        domain_code=domain_code or None,
                        concept_code=code,
                        field_path=f"{ref_kind}.{code}",
                        message=message,
                        params=params,
                    )
                )
            case DeclarationKind.PIPE:
                items.append(
                    PipelexBundleBlueprintValidationErrorData(
                        source=source,
                        domain_code=domain_code or None,
                        pipe_code=code,
                        field_path=f"{ref_kind}.{code}",
                        message=message,
                        params=params,
                    )
                )
    return items
