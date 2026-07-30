# The boundary re-validation round trip is lossy in ways nobody has audited

Deferred out of PR #1076 (`refactor/Exec`). **Pre-existing, unchanged by that PR, and it must stay** — it is the boundary conversion. Recorded so the next person to touch it knows what has and has not been checked.

## What it is

`_revalidate_against_object_class` (`pipelex/cogt/content_generation/content_generator.py`) converts a leaf result into the caller's class with:

```python
object_class.model_validate(raw_obj.model_dump(serialize_as_any=True))
```

After #1076 this only runs on the **boundary** path — a worker that held only the serialized `ObjectAssignment` returns an instance of a class rebuilt from the JSON schema, which is never a subclass of `object_class`, so the `isinstance` short-circuit does not catch it. In-process the object is returned untouched.

## Why it is worth a look eventually

The dump→validate round trip is not identity-preserving in general, and the ways it can lose are not covered by any test:

- **Subclass erasure.** A dumped subclass instance revalidates as the declared class, silently dropping the subclass's extra fields and its type.
- **Dumped-by-field-name data has to revalidate cleanly.** This currently happens to work only because of compensating configuration elsewhere: `PipeSearchSpec` / `PipeComposeSpec` set `populate_by_name=True`, and `PipeComposeSpec` carries a `normalize_construct_field` before-validator. A new aliased model on this path would not automatically inherit that luck.
- **Validators run on the dumped form**, not the constructed form. For a model whose validators are not total over their own serialized output, that is a different input than the one they were written against.

None of these is currently reachable in-process (the short-circuit sees to that) and none has a known live trigger on the boundary path either — which is exactly why this is a note and not a change.

## What would close it

An audit of what actually crosses this conversion on the boundary path, plus a round-trip property test over the models that do. If the audit finds a real loss, the fix is probably to have the boundary return raw data rather than a reconstructed instance, so there is one validation instead of a dump of one.

## Related

- The in-process arm of this same function was a genuine double-validation regression, found by the PR bots on #1076 and fixed there with an `isinstance` short-circuit. See that PR's `TODOS.md` for the reasoning.
