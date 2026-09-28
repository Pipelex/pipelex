# Deferred review findings from the instructor 1.17 and aiobotocore bump

Status: deferred. The finding below came out of round 2 of `/rev` on `chore/Bumping` (item L-260927-56ef15, with L-260927-61a69f for the aiobotocore swap). The pass ran at the `defects` bar, which fixes only confirmed defects that matter, so it was sorted as an improvement and deferred **without verification**: it rests on the reviewers' reading alone, and whoever picks it up should confirm it first.

## The Anthropic worker compares a structure method with `!=` (unverified)

Raised by cubic and Codex. `pipelex/providers/anthropic/anthropic_llm_worker.py`, in `_structure_method_kwargs`, tests `structure_method != StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS` to decide whether to leave the tool choice to the model. The repository's standard is to branch on an enum with an exhaustive `match`/`case`, or through a property on the enum, so that adding a member forces someone to decide how it behaves here. As written, a new structure method silently takes the forced-tool-choice path. The suggested shape is a property such as `StructureMethod.forces_tool_choice`, or a `match` over the members that reach the Anthropic worker.
