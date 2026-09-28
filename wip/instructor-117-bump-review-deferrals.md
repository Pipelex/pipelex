# Deferred review findings from the instructor 1.17 and aiobotocore bump

Status: deferred. Both findings below came out of round 2 of `/rev` on `chore/Bumping` (item L-260927-56ef15, with L-260927-61a69f for the aiobotocore swap). The pass ran at the `defects` bar, which fixes only confirmed defects that matter, so both were sorted as improvements and deferred **without verification**: each rests on the reviewers' reading alone, and whoever picks one up should confirm it first.

## The Anthropic worker compares a structure method with `!=` (unverified)

Raised by cubic and Codex. `pipelex/providers/anthropic/anthropic_llm_worker.py`, in `_structure_method_kwargs`, tests `structure_method != StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS` to decide whether to leave the tool choice to the model. The repository's standard is to branch on an enum with an exhaustive `match`/`case`, or through a property on the enum, so that adding a member forces someone to decide how it behaves here. As written, a new structure method silently takes the forced-tool-choice path. The suggested shape is a property such as `StructureMethod.forces_tool_choice`, or a `match` over the members that reach the Anthropic worker.

## The `inference-backend@3` migration entry has no test of its own (unverified)

Raised by cubic. `pipelex/migration/ledgers/inference-backend.toml` carries the `@3` entry that reports a backend file still setting `sdk = "bedrock_aioboto3"`. That entry is the only thing that tells a user about the renamed handle, since the boot does not detect it (the boot-time check is L-260927-dd296f), and the changelog promises that `pipelex migrate` names each such file. The `@2` entry has its own test (`test_backend_back_entry.py`); `@3` has none, and the ledger gates would not notice a typo in its `mapping` or `table_path`, because the reference documents never contain the old handle. The suggested test replays the ledger over an old-shape Bedrock backend file and asserts that it is reported as blocked under `inference-backend@3`, with the guidance naming `bedrock_aioboto`.
