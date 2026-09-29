---
title: "StuffArtefact & Image Rendering"
description: "How StuffArtefact enables Jinja2 template access to Stuff objects and the ImageRenderable protocol extracts images from nested content."
---

# StuffArtefact & Image Rendering

StuffArtefact is a thin delegation adapter that wraps `Stuff` objects for Jinja2 template access. The `ImageRenderable` protocol enables image extraction from nested content without circular imports between the template layer and domain layer.

---

## Design Principle

Two problems, one pattern:

1. **Template Access**: Templates need to access content fields via `{{ my_stuff.field_name }}` without knowing Pydantic internals
2. **Image Extraction**: The `with_images` filter needs to traverse content hierarchies without importing concrete types

**Solution**: StuffArtefact delegates attribute access to underlying content. ImageRenderable uses `@runtime_checkable` Protocol for duck-typed image extraction.

```
StuffArtefact wraps Stuff → delegates to StuffContent → Protocol enables traversal
```

!!! info "Protocol over Inheritance"
    ImageRenderable uses duck typing. Any class that defines a `render_with_images()` method satisfies the protocol, with no base class required. The filters check the class rather than the instance, so a value that merely holds such a method as an attribute is never rendered through it.

---

## Template Access Patterns

| Pattern | Result |
|---------|--------|
| `{{ doc.title }}` | Content field value |
| `{{ doc.pages }}` | Nested content (list, struct, etc.) |
| `{{ combo.summary }}` | A named part of a `Composite` output |
| `{{ doc._stuff_name }}` | Metadata: variable name |
| `{{ doc._content_class }}` | Metadata: content class name |
| `{{ doc._concept_code }}` | Metadata: concept code |
| `{{ doc._stuff_code }}` | Metadata: stuff code |
| `{{ doc \| with_images }}` | Text with `[Image N]` tokens |
| `{{ doc \| tag }}` | Tagged output (no images) |

These are the only underscore names a template may read on an input. Templates render under the [Template Sandbox](template-sandbox.md), which refuses every other private name. The wrapped `Stuff` is not an attribute of the artefact at all: Python code reaches it through `unwrap_stuff_artefact(artefact=...)`.

---

## Image Extraction Behavior

| Content Type | `render_with_images()` Behavior |
|-------------|--------------------------------|
| `ImageContent` | Self-registers, returns `[Image N]` |
| `ListContent` | Iterates items, recurses into nested |
| `TextAndImagesContent` | Renders text first, then images |
| `StructuredContent` | Iterates model fields, recurses into nested lists/tuples/dicts |
| `StuffArtefact` | Delegates to underlying content |

---

## Architecture

```mermaid
flowchart TB
    subgraph TEMPLATE["Jinja2 Template"]
        VAR["{{ doc | with_images }}"]
    end

    subgraph FILTER["with_images Filter"]
        direction TB
        CHECK["ImageRenderable, defined by its class?"]
        CALL["value.render_with_images(registry=registry, text_format=text_format)"]
        CHECK --> CALL
    end

    subgraph ARTEFACT["StuffArtefact"]
        DELEGATE["Delegates to _stuff.content"]
    end

    subgraph CONTENT["Content Implementations"]
        direction TB
        IMG["ImageContent: register + return token"]
        LIST["ListContent: iterate items"]
        TEXT["TextAndImagesContent: text then images"]
        STRUCT["StructuredContent: iterate model_fields"]
    end

    subgraph REGISTRY["ImageRegistry"]
        direction TB
        STORE["Append to list (0-based)"]
        DEDUP["Skip if URL exists"]
    end

    VAR --> CHECK
    CALL --> DELEGATE
    DELEGATE --> IMG & LIST & TEXT & STRUCT
    IMG --> STORE
    STORE --> DEDUP
```

---

## StuffArtefact Implementation

### Attribute Access Priority

StuffArtefact uses `__getattribute__` to intercept all attribute access:

```python
def __getattribute__(self, key: str) -> Any:
    # 1. Passthrough: _stuff, methods, magic attributes
    if key in _PASSTHROUGH_ATTRS or key.startswith("__"):
        return object.__getattribute__(self, key)

    # 2. Content fields, then 3. metadata fields (_stuff_name, _content_class, _concept_code, _stuff_code)
    try:
        return _get_template_value(stuff=stuff, key=key)
    except KeyError:
        # 4. Fallback to normal lookup
        return object.__getattribute__(self, key)
```

`_get_template_value` is the whole of what a string key resolves to: a content field (a declared field, or a public extra field such as a `Composite`'s named parts), else one of the four metadata fields, else `KeyError`.

!!! warning "Content Field Priority"
    Content fields shadow StuffArtefact methods. If your content has a field named `items`, accessing `artefact.items` returns the field value, not the iteration method. Use `artefact.iter_items()` for explicit dict-like iteration.

### Dict-like Access

StuffArtefact supports bracket notation and iteration:

| Method | Purpose |
|--------|---------|
| `artefact["field"]` | Bracket access (via `__getitem__`): a content field or a metadata field only |
| `artefact.get("field", default=...)` | Safe access with default, resolving the same keys as brackets |
| `"field" in artefact` | Membership test |
| `artefact.iter_keys()` | Iterate field names |
| `artefact.iter_items()` | Iterate (key, value) pairs |
| `artefact.iter_values()` | Iterate values |

Bracket access and `get` never resolve to the artefact's own attributes, such as the wrapped `Stuff` or a method. The accessors above and the four metadata fields are what `StuffArtefact` declares as its template surface: the only methods a template may call on it and the only underscore names it may read.

---

## ImageRenderable Protocol

### Definition

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class ImageRenderable(Protocol):
    """Protocol for types that can render with image extraction."""

    def render_with_images(
        self,
        *,
        registry: ImageRegistry,
        text_format: TextFormat,
    ) -> str:
        """Render to string, registering images to the registry.

        Returns:
            String with [Image N] tokens where images appear.
        """
        ...
```

### Why Protocol?

- **Avoids circular imports**: `tools/jinja2/` can check types from `core/stuffs/` without importing them
- **Duck typing**: No inheritance required—any matching method signature works
- **Runtime checking**: `isinstance(value, ImageRenderable)` works at runtime, and the filters add `type_implements(value=value, protocol=ImageRenderable)`, which reads the members from the class, since on Python 3.11 the `isinstance` check alone accepts an instance merely holding the method

---

## Content Implementations

### ImageContent

Self-registers and returns a token:

```python
def render_with_images(self, *, registry, text_format) -> str:
    image_index = registry.register_image(self)
    return f"[Image {image_index + 1}]"
```

### ListContent

Iterates items, delegating to nested ImageRenderable objects:

```python
def render_with_images(self, *, registry, text_format) -> str:
    parts: list[str] = []
    for item in self.items:
        if isinstance(item, ImageRenderable):
            rendered = item.render_with_images(registry=registry, text_format=text_format)
        else:
            rendered = item.rendered_markdown()
        if rendered:
            parts.append(rendered)
    return "\n".join(parts)
```

### TextAndImagesContent

Renders text first, then registers each image:

```python
def render_with_images(self, *, registry, text_format) -> str:
    parts: list[str] = []
    if self.text:
        parts.append(self.text.rendered_for_prompt(text_format=text_format))
    if self.images:
        for image in self.images:
            image_index = registry.register_image(image)
            parts.append(f"[Image {image_index + 1}]")
    return "\n".join(parts)
```

### StructuredContent

Default implementation for structured models iterates Pydantic model fields:

```python
def render_with_images(self, *, registry, text_format) -> str:
    parts: list[str] = []
    for field_name in type(self).model_fields:
        field_value = getattr(self, field_name)
        if field_value is None:
            continue
        rendered = self._render_value_with_images(field_value, registry=registry, text_format=text_format)
        if rendered:
            parts.append(f"{field_name}: {rendered}")
    return "\n".join(parts)
```

The `_render_value_with_images` helper recurses: a nested `ImageRenderable` gets `render_with_images(...)`, plain lists/tuples/dicts are traversed item by item, a non-renderable `StuffContent` falls back to `rendered_for_prompt(text_format=text_format)`, and anything else to `str(value)`. A plain `StuffContent` subclass that is not a `StructuredContent` does not implement the protocol.

---

## Image Numbering

### Registry Behavior

| Operation | Result |
|-----------|--------|
| First image registered | Returns index `0` |
| Second image registered | Returns index `1` |
| Same URL registered again | Returns existing index (deduplication) |
| Display in template | `[Image {index + 1}]` (1-based) |

### Example

```python
registry = ImageRegistry()

idx = registry.register_image(img_a)  # idx=0 → [Image 1]
idx = registry.register_image(img_b)  # idx=1 → [Image 2]
idx = registry.register_image(img_a)  # idx=0 → [Image 1] (same URL)

len(registry.images)  # 2 (deduplicated)
```

---

## The `with_images` Filter

### Execution Flow

```python
@pass_context
def with_images(context: Context, value: Any, _: Any = None) -> str:
    # 1. Validate input
    if isinstance(value, Undefined):
        raise Jinja2ContextError("Cannot use with_images on undefined")

    # 2. Get/create registry from context
    registry = context.get(Jinja2ContextKey.IMAGE_REGISTRY)
    if registry is None:
        registry = ImageRegistry()

    # 3. Get text format: no fallback, a render without a templating style fails loudly
    text_format = TextFormat(require_templating_style_value(context=context, jinja2_context_key=Jinja2ContextKey.TEXT_FORMAT))

    # 4. Protocol-based rendering, licensed by the value's class, never by an attribute the instance holds
    if isinstance(value, ImageRenderable) and type_implements(value=value, protocol=ImageRenderable):
        return value.render_with_images(registry=registry, text_format=text_format)

    # 5. Handle plain sequences
    if isinstance(value, (list, tuple)):
        return _render_sequence_with_images(value, registry=registry, text_format=text_format)

    # 6. Reject unsupported types
    raise Jinja2ContextError(f"{type(value).__name__} does not implement ImageRenderable")
```

!!! warning "Filter Order Matters"
    `with_images` must receive structured data to extract images. Place it **before** any filter that converts to string.

    | Pattern | Works? |
    |---------|--------|
    | `{{ doc \| with_images }}` | Yes |
    | `{{ doc \| with_images \| tag }}` | Yes |
    | `{{ doc \| tag \| with_images }}` | No—`tag` stringifies first |

---

## Syntax Quick Reference

| Pattern | Purpose |
|---------|---------|
| `{{ x.field }}` | Access content field |
| `{{ x["field"] }}` | Bracket access |
| `{{ x._stuff_name }}` | Variable name metadata |
| `{{ x._content_class }}` | Content class name |
| `{{ x._concept_code }}` | Concept code |
| `{{ x._stuff_code }}` | Stuff code |
| `{{ x \| with_images }}` | Extract images as tokens |
| `{{ x \| with_images \| tag }}` | Extract then wrap in tags |

---

## Files Reference

| File | Purpose |
|------|---------|
| `pipelex/core/stuffs/stuff_artefact.py` | Thin delegation adapter for Jinja2 |
| `pipelex/tools/jinja2/image_renderable.py` | `@runtime_checkable` Protocol for images |
| `pipelex/tools/jinja2/tag_renderable.py` | `@runtime_checkable` Protocol for tagging |
| `pipelex/tools/jinja2/jinja2_with_images_filter.py` | `with_images` filter |
| `pipelex/tools/jinja2/jinja2_filters.py` | `tag` and `format` filters |
| `pipelex/tools/jinja2/image_registry.py` | Image tracking with deduplication |
| `pipelex/core/stuffs/structured_content.py` | Field-iterating `render_with_images()` for structured models |
| `pipelex/core/stuffs/image_content.py` | Self-registering image token |
| `pipelex/core/stuffs/list_content.py` | List iteration for images |
| `pipelex/core/stuffs/text_and_images_content.py` | Text + images rendering |

---

## Next Steps

- [:material-image-multiple: Image Handling in LLM Prompts](./image-handling-in-llm-prompts.md){ .md-button .md-button--primary }
- [:material-sitemap: Architecture Overview](./architecture-overview.md){ .md-button }
