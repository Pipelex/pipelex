"""Fix planner — translates enriched validation error data into ``SuggestedFix`` payloads.

Pure functions keyed strictly on ``error_type`` + structured fields, never message strings.
The planner runs inside report assembly (``build_validation_error_items``), so every consumer
of the validation report — CLI, API, MCP — sees fixes with zero extra plumbing.
"""

from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.suggested_fix import FixOp, FixOpKind, FixSafety, SuggestedFix, TomlScalar

MATCH_SEQUENCE_OUTPUT_FIX_CODE = "match-sequence-output"
SYNC_CONTROLLER_INPUTS_FIX_CODE = "sync-controller-inputs"
STRIP_NATIVE_CONCEPT_REDECL_FIX_CODE = "strip-native-concept-redecl"
STRIP_NAMESPACE_FIX_CODE = "strip-namespace"

# Every fix-rule code the planner can emit — the validation set for user-facing rule filters
# (``--select`` / ``--ignore``). A new rule constant above must be added here; the CLI rejects
# codes outside this set loudly (a typo'd filter selects *behavior*, so lenient-ignore is wrong).
KNOWN_FIX_CODES: frozenset[str] = frozenset(
    {
        MATCH_SEQUENCE_OUTPUT_FIX_CODE,
        SYNC_CONTROLLER_INPUTS_FIX_CODE,
        STRIP_NATIVE_CONCEPT_REDECL_FIX_CODE,
        STRIP_NAMESPACE_FIX_CODE,
    }
)


def plan_fix_for_pipe_validation_error(error_data: PipesAndConceptValidationErrorData) -> SuggestedFix | None:
    """Derive a suggested fix from one pipe-validation error data, or ``None`` when not fixable.

    Each rule fires only when its enrichment is present — set only at the raise sites that know
    the correct value — so the same error types raised elsewhere (PipeParallel / PipeCondition /
    operator pipes) carry no enrichment and are suppressed here structurally.
    """
    if error_data.error_type.is_inadequate_output:
        return _plan_match_sequence_output(error_data)
    if error_data.error_type.is_controller_input_drift:
        return _plan_sync_controller_inputs(error_data)
    return None


def _plan_match_sequence_output(error_data: PipesAndConceptValidationErrorData) -> SuggestedFix | None:
    """``match-sequence-output``: an ``INADEQUATE_OUTPUT_*`` carrying the enriched
    ``expected_output_ref`` becomes a ``set_key`` of the pipe's ``output``.
    """
    if error_data.expected_output_ref is None or error_data.pipe_code is None:
        return None
    return SuggestedFix(
        fix_code=MATCH_SEQUENCE_OUTPUT_FIX_CODE,
        description=f"Set output of pipe '{error_data.pipe_code}' to '{error_data.expected_output_ref}' to match its last step",
        safety=FixSafety.SAFE,
        source=error_data.source,
        ops=[
            FixOp(
                kind=FixOpKind.SET_KEY,
                table_path=["pipe", error_data.pipe_code],
                key="output",
                value=error_data.expected_output_ref,
            ),
        ],
    )


def _plan_sync_controller_inputs(error_data: PipesAndConceptValidationErrorData) -> SuggestedFix | None:
    """``sync-controller-inputs``: an input-drift error carrying the enriched ``expected_inputs``
    + ``declared_inputs`` mappings becomes a minimal diff of the pipe's ``inputs`` table —
    ``set_key`` for added/changed variables, ``delete_key`` for extraneous ones. Because the
    mappings are complete, one fix repairs all input drift for the pipe even though validation
    aborts at the first error. With nothing declared there is no table to patch in place, so a
    single ``set_key`` writes the whole mapping.
    """
    if error_data.expected_inputs is None or error_data.declared_inputs is None or error_data.pipe_code is None:
        return None

    if not error_data.declared_inputs:
        if not error_data.expected_inputs:
            return None
        variables = ", ".join(f"'{var_name}'" for var_name in error_data.expected_inputs)
        return SuggestedFix(
            fix_code=SYNC_CONTROLLER_INPUTS_FIX_CODE,
            description=f"Declare inputs of pipe '{error_data.pipe_code}' as needed by its steps: {variables}",
            safety=FixSafety.SAFE,
            source=error_data.source,
            ops=[
                FixOp(
                    kind=FixOpKind.SET_KEY,
                    table_path=["pipe", error_data.pipe_code],
                    key="inputs",
                    value=dict[str, TomlScalar](error_data.expected_inputs),
                ),
            ],
        )

    inputs_table_path = ["pipe", error_data.pipe_code, "inputs"]
    added: list[str] = []
    updated: list[str] = []
    removed: list[str] = []
    ops: list[FixOp] = []
    for var_name, expected_ref in error_data.expected_inputs.items():
        declared_ref = error_data.declared_inputs.get(var_name)
        if declared_ref == expected_ref:
            continue
        (added if declared_ref is None else updated).append(var_name)
        ops.append(FixOp(kind=FixOpKind.SET_KEY, table_path=inputs_table_path, key=var_name, value=expected_ref))
    for var_name in error_data.declared_inputs:
        if var_name not in error_data.expected_inputs:
            removed.append(var_name)
            ops.append(FixOp(kind=FixOpKind.DELETE_KEY, table_path=inputs_table_path, key=var_name))
    if not ops:
        # The renderings already agree (e.g. two concepts that render to the same relative ref):
        # an empty diff would be a no-op fix the loop applies forever — suppress instead.
        return None

    change_parts: list[str] = []
    if added:
        change_parts.append("add " + ", ".join(f"'{var_name}'" for var_name in added))
    if updated:
        change_parts.append("update " + ", ".join(f"'{var_name}'" for var_name in updated))
    if removed:
        change_parts.append("remove " + ", ".join(f"'{var_name}'" for var_name in removed))
    return SuggestedFix(
        fix_code=SYNC_CONTROLLER_INPUTS_FIX_CODE,
        description=f"Sync inputs of pipe '{error_data.pipe_code}' with its steps' needs: {'; '.join(change_parts)}",
        safety=FixSafety.SAFE,
        source=error_data.source,
        ops=ops,
    )


def plan_fix_for_blueprint_validation_error(error_data: PipelexBundleBlueprintValidationErrorData) -> SuggestedFix | None:
    """Derive a suggested fix from one blueprint-validation error data, or ``None`` when not fixable.

    The blueprint channel carries an optional ``error_type``; only errors whose enrichment is
    present (set at the raise site that knows the correct value) become fixes, so uncategorized
    residuals and unrelated blueprint errors are suppressed structurally.
    """
    if error_data.error_type is None:
        return None
    if error_data.error_type.is_native_concept_redeclaration:
        return _plan_strip_native_concept_redecl(error_data)
    if error_data.error_type.is_invalid_pipe_code_syntax:
        return _plan_strip_namespace(error_data)
    return None


def _plan_strip_native_concept_redecl(error_data: PipelexBundleBlueprintValidationErrorData) -> SuggestedFix | None:
    """``strip-native-concept-redecl``: a native-concept redeclaration carrying the enriched
    ``concept_code`` becomes a ``delete_key`` of that key under ``["concept"]`` — the one op that
    covers every authoring form (``[concept.X]`` table, ``X = "…"`` shorthand, dotted
    ``concept.X``) since tomlkit represents them all as a ``concept`` table keyed by the code.
    """
    if error_data.concept_code is None:
        return None
    return SuggestedFix(
        fix_code=STRIP_NATIVE_CONCEPT_REDECL_FIX_CODE,
        description=f"Remove the redeclaration of native concept '{error_data.concept_code}'",
        safety=FixSafety.SAFE,
        source=error_data.source,
        ops=[
            FixOp(
                kind=FixOpKind.DELETE_KEY,
                table_path=["concept"],
                key=error_data.concept_code,
            ),
        ],
    )


def _plan_strip_namespace(error_data: PipelexBundleBlueprintValidationErrorData) -> SuggestedFix | None:
    """``strip-namespace``: a same-domain over-qualified pipe code carrying the enriched
    ``stripped_pipe_code`` becomes either a position-preserving ``rename_table_key`` of the
    ``[pipe]`` declaration key (when ``pipe_code`` holds the offending dotted key) or a root
    ``set_key`` of ``main_pipe`` (when it does not — a ``main_pipe`` value is not a table key).

    Only the declaration key and ``main_pipe`` are ever stripped: internal references
    (``steps[].pipe``, ``branches[].pipe``, …) keep resolving because a same-domain *qualified*
    ref resolves to the bare pipe, so they need no rewrite. Un-strippable syntax errors carry no
    ``stripped_pipe_code`` and are suppressed here structurally.
    """
    if error_data.stripped_pipe_code is None:
        return None
    if error_data.pipe_code is not None:
        return SuggestedFix(
            fix_code=STRIP_NAMESPACE_FIX_CODE,
            description=f"Strip the same-domain prefix from pipe '{error_data.pipe_code}' (rename to '{error_data.stripped_pipe_code}')",
            safety=FixSafety.SAFE,
            source=error_data.source,
            ops=[
                FixOp(
                    kind=FixOpKind.RENAME_TABLE_KEY,
                    table_path=["pipe"],
                    key=error_data.pipe_code,
                    new_key=error_data.stripped_pipe_code,
                ),
            ],
        )
    return SuggestedFix(
        fix_code=STRIP_NAMESPACE_FIX_CODE,
        description=f"Strip the same-domain prefix from main_pipe (set to '{error_data.stripped_pipe_code}')",
        safety=FixSafety.SAFE,
        source=error_data.source,
        ops=[
            FixOp(
                kind=FixOpKind.SET_KEY,
                table_path=[],
                key="main_pipe",
                value=error_data.stripped_pipe_code,
            ),
        ],
    )
