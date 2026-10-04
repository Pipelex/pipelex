---
title: "Structure validation"
description: "Reference for the `StructureValidationError` Pipelex error class."
---

<!-- pipelex:authored -->

# Structure validation

A provided input value could not be built as the concept its input declares.

Most often the value is the right JSON kind but does not fit the concept's structure: an object missing a required field, a malformed `{"url": ...}` for an image or a document, a string that is not an ISO date for a `Date` input. The message names the input and the declared concept, and ends with the expected shape rendered from the method's signature. The fix is the value.

The other case is a value that an input reading bare values by their own shape has no reading for, or reads as a concept the input does not accept. An input declared `Dynamic`, as one of the container natives (`Html`, `Page`, `TextAndImages`, `SearchResult`, `Composite`), or as a `Choice` or a `Rating`, reads a bare value that way. A bare string reads as a text, which only a `Dynamic` input takes: at a `Choice` input the message is `Input 'team' could not be built as 'native.Choice': you provided a string ("billing"), which reads as 'native.Text', and a 'native.Text' is not a 'native.Choice'.`, and the fix is the value, sent in the expected shape the message ends with. So it is for the input's own content sent without its envelope: `{"choice": "billing"}` at a `Choice` input is refused as `the content of a 'native.Choice' without the envelope that names its concept`, and declaring the input `JSON` instead would discard the concept the method asked for. A bare level or key at a `Rating` or a `Choice` input, such as `2`, is refused the same way, as a value that `takes its value in the envelope that names its concept`, since declaring the input `Anything` would discard the verdict. Some values have no reading at all: a number, or a list of plain objects. The message says so, `Input 'records' could not be built as 'native.Dynamic': you provided a list of 2 item(s), and an input of this concept reads a bare value by its own shape, with no reading for this one.`, and its next step names the declaration that would read the value: `JSON` for an object, `JSON[]` for a list of objects, `Anything` or `Anything[]` for anything else, or a concept with a structure that describes it. The fix is usually the method's declaration rather than the value.

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
