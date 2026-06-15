# Suspects — package `kit`

Reviewed: 8 Section A + 0 primitive lone-subjects. Suspects: 2.

## High confidence

- `pipelex/kit/single_file_agent_rules.py:12` — `_read_agent_file` — `def _read_agent_file(agents_dir: Traversable, *, name: str) -> str` — `agents_dir` is a lookup-table/context directory; `name` is the file being read — the real acted-on object. The pattern "read [name] from [agents_dir]" has the semantic subject keyworded and the context positional. Call site (line 79): `_read_agent_file(agents_dir, name=name)` confirms `name` carries the meaning. Suggested fix: make fully keyword-only — `def _read_agent_file(*, agents_dir: Traversable, name: str) -> str`

## Medium / low confidence

- `pipelex/kit/single_file_agent_rules.py:49` — `build_merged_rules` — `def build_merged_rules(kit_index: KitIndex, *, agent_set: str | None=None, file_list: list[str] | None=None) -> str` — `kit_index` is a configuration/registry object used as a data source and lookup table, not the semantic object being acted on. The function "builds merged rules" by consulting the index; `kit_index` reads more like a context/config argument than a subject. Lower confidence because a KitIndex could reasonably be seen as "the thing being merged from". Suggested fix: make fully keyword-only — `def build_merged_rules(*, kit_index: KitIndex, agent_set: str | None=None, file_list: list[str] | None=None) -> str`
