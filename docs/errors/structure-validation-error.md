---
title: "Structure validation"
description: "Reference for the `StructureValidationError` Pipelex error class."
---

<!-- pipelex:authored -->

# Structure validation

A provided input value could not be built as the concept its input declares.

Most often the value is the right JSON kind but does not fit the concept's structure: an object missing a required field, a malformed `{"url": ...}` for an image or a document, a string that is not an ISO date for a `Date` input. The message names the input and the declared concept, and ends with the expected shape rendered from the method's signature. The fix is the value.

The other case is a value that an input reading bare values by their own shape has no reading for. An input declared `Dynamic`, or as one of the container natives (`Html`, `Page`, `TextAndImages`, `SearchResult`, `Composite`), reads a bare value that way, and some values have none: a number, or a list of plain objects. The message says so, `Input 'records' could not be built as 'native.Dynamic': you provided a list of 2 item(s), and an input of this concept reads a bare value by its own shape, with no reading for this one.`, and its next step names the declaration that would read the value: `JSON` for an object, `JSON[]` for a list of objects, `Anything` or `Anything[]` for anything else, or a concept with a structure that describes it. The fix is usually the method's declaration rather than the value.

When no declaration reads the value, such as an empty list at a `Html[]` input, a list mixing prebuilt contents of different kinds, or a list holding nulls or nested lists, the message carries the reason itself.

The error is in the `input` domain, so an HTTP surface answers 422.

| Field | Value |
|---|---|
| `error_type` | `StructureValidationError` |
| `title` | Structure validation |
| `type_uri` | `https://docs.pipelex.com/latest/errors/structure-validation-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.core.memory.exceptions` |
| Parent class | [`InputShapingError`](input-shaping-error.md) |

[Back to Error Reference](index.md)
