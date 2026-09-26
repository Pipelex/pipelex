---
title: "Stuff factory"
description: "Reference for the `StuffFactoryError` Pipelex error class."
---

<!-- pipelex:authored -->

# Stuff factory

A stuff could not be built from the content given for its concept. It is raised from many places, and whose fault it is depends on the place.

When a `PipeParallel` combines its branch results into its declared output, a mismatch is the caller's fault: which branch feeds which field, what each branch produces and whether it produces a list are all written in the caller's method. A branch declared `Idea[]` feeding a field that holds one `Idea`, a branch concept its field does not accept, or a required field no branch feeds, all fail there. That error is in the `input` domain, so an HTTP surface answers 422, its message survives STRICT disclosure, and its next step says to change the method. The run's report locates it at the parallel: ``Pipe 'analyze' failed (flow → analyze): Error combining stuffs for concept Report, stuff named `report`: …``, followed by the validation errors of the fields.

Raised from any other place, it carries no domain and its message is redacted under STRICT disclosure.

| Field | Value |
|---|---|
| `error_type` | `StuffFactoryError` |
| `title` | Stuff factory |
| `type_uri` | `https://docs.pipelex.com/latest/errors/stuff-factory-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.core.stuffs.exceptions` |
| Parent class | [`StuffError`](stuff-error.md) |

[Back to Error Reference](index.md)
