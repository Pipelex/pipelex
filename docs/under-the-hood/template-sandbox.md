---
title: "Template Sandbox"
description: "Every Jinja2 template Pipelex renders runs under one sandbox policy: a template reads data and calls methods of plain values, and nothing else."
---

# Template Sandbox

A method's templates are code. PipeLLM prompts, PipeCompose templates and construct templates, PipeImgGen and PipeSearch prompts, and PipeCondition expressions are all Jinja2 templates, and they render inside the process that runs the method. When that process is shared, as it is on a hosted runner, a template must not be able to reach anything but the data it was given.

Pipelex therefore renders every template, its own included, under one policy: **a template reads data and calls methods of plain values, and nothing else.**

## What a template may do

| A template may | For example |
|---|---|
| Read the public fields of an input, with a dot or with brackets, the named parts of a `Composite` included | `{{ invoice.total }}`, `{{ invoice['total'] }}`, `{{ combo.summary }}` |
| Read an input's metadata fields | `{{ invoice._stuff_name }}`, `{{ invoice._content_class }}`, `{{ invoice._concept_code }}`, `{{ invoice._stuff_code }}` |
| Read any key of a plain dict with brackets, underscore keys included | `{{ record['_id'] }}`, `{{ record['__typename'] }}` |
| Call the dict-like accessors of an input | `{{ invoice.get('total') }}`, `{% for key, value in invoice.iter_items() %}` |
| Call methods of strings, numbers, dates and times, lists, tuples, dicts and sets | `{{ issued_at.isoformat() }}`, `{{ name.upper() }}`, `{{ record.get('a') }}` |
| Format a string, including with replacement fields | `{{ '{0} items'.format(count) }}` |
| Use Jinja's own constructs and globals | macros and `caller()`, `loop.cycle()`, `namespace()`, `cycler()`, `joiner()`, `range()`, `dict()` |
| Apply any filter | `{{ doc \| tag }}`, `{{ doc \| format }}`, `{{ page \| with_images }}`, `{{ items \| length }}` |

## What a template may not do

| A template may not | For example |
|---|---|
| Read a name starting with an underscore, other than the metadata fields and a plain dict's keys above | `{{ doc._stuff }}`, `{{ doc['_content'] }}`, `{{ doc.__class__ }}`, `{{ record._id }}` |
| Read the `Stuff` an input wraps | `{{ doc.stuff }}` is undefined |
| Call a method of anything that is not a plain value | `{{ pages[0].model_dump() }}`, `{{ photos[0].model_copy() }}` |
| Call a class method, even through an instance | `{{ issued_at.now() }}` |
| Change a list, a dict or a set | `{{ items.append(x) }}`, `{{ record.update(other) }}`, `{{ tags.intersection_update(other) }}` |
| Store a callable in a `namespace()` | `{% set ns.f = name.upper %}`, `namespace(items=doc.get)` |
| Include or extend another template | `{% include 'header.html' %}` |

A method template renders without a template loader, so `{% include %}`, `{% extends %}` and `{% import %}` find nothing to load.

## How a refusal shows up

Many refusals are visible in the template itself, and validation reports them before anything runs: a template that reads an undeclared underscore name with a dot fails with the `template_private_name` validation error, which names the pipe and the template (`prompt`, `system_prompt`, `template`, `expression`, or `construct field '<path>'`).

What validation cannot see, because it depends on the values at run time (a method call, a name computed while rendering, or a bracketed key, which is legitimate on a plain dict), is refused where it happens: the render raises [`Jinja2TemplateSecurityError`](../errors/jinja2-template-security-error.md), whose message names the refused attribute or callable and the type it was reached on. A refusal never renders as an empty string, so a prompt is never sent with a hole in it.

## How it is built

Every environment comes from one factory, `make_jinja2_env_from_loader` in `pipelex/tools/jinja2/jinja2_environment.py`, and that factory builds a `PipelexTemplateEnvironment` (`pipelex/tools/jinja2/jinja2_sandbox.py`), a subclass of Jinja's `ImmutableSandboxedEnvironment`. Rendering, parsing and compiling all go through it, including the condition pipe's compile at load and the load-time template walkers.

Jinja's stock sandbox refuses internals, but not public methods, and every pydantic model has public constructors. Under the stock sandbox a template could call `model_validate` on a content object and forge an image pointing at a storage key of its choosing. The Pipelex policy closes that by allowing calls by kind rather than by name:

- **Jinja's own runtime**: macros, `caller`, `loop`, `cycler`, `joiner`, block references, and the environment's globals.
- **Methods a plain value type defines**, bound to an instance of that type. A subclass of a plain type (a `StrEnum` member is a `str`) cannot add or override a callable method, and a class method is refused because it is bound to the class. A method that changes a list, a dict or a set in place is refused by a list Pipelex keeps itself, since Jinja's own misses `set.intersection_update`.
- **The sandbox's own `str.format` wrapper**, which resolves replacement fields through the same attribute and item checks. The raw `str.format` stays refused.
- **The methods a type declares as its template surface** (`pipelex/tools/jinja2/template_surface.py`).

A type declares its template surface as a `__template_surface__` class attribute: the methods a template may call on an instance and the underscore names it may read. The sandbox reads the declaration from the type, never from the instance. `StuffArtefact`, the adapter every input is wrapped in, declares `get`, `iter_keys`, `iter_items` and `iter_values`, and its four metadata fields. The `Stuff` it wraps is not one of its attributes at all: Python code reaches it through `unwrap_stuff_artefact`, and its bracket access and `get` resolve a key to a content field or a metadata field only.

The sandbox refuses a bracketed name before trying `obj[name]`. Jinja only checks a bracketed name when the item lookup fails, so an object whose `__getitem__` answered any key would otherwise hand over what the dot spelling could not. A plain `dict` is the exception, because its items are data: a key it holds is returned, and a key it does not hold falls back to an attribute read, which the underscore rule refuses.

Filters are not calls in this sense: they are Pipelex's or Jinja's own code, registered by the environment. That makes each filter trusted code with one obligation: **a filter never calls a callable it was handed**, since that callable came from the template's values and the policy never vetted it. So `with_images`, `format` and `tag` call a value's rendering method only when the value's class defines it, and they check that on the type (`pipelex/tools/jinja2/renderable_dispatch.py`). A runtime-checkable Protocol alone would not do: on Python 3.11 it accepts a `namespace()` holding a callable of the template's choosing.

Jinja's own filters and markupsafe keep that obligation only for values whose attributes the template cannot choose: they look `__html__` up on a value when escaping, and `items` in `dictsort` and `xmlattr`, and call what they find. A `namespace()` answers any name with whatever the template stored under it, so the environment's `namespace` holds data only, and storing a callable in one, at construction or with `{% set ns.x = … %}`, is refused.

## Paths outside templates

A method also writes dotted paths that are not templates: a PipeCompose construct field's `from` and its `list_to_dict_keyed_by`, a PipeBatch's list, and the image and document references of a prompt. The runtime walks these with `getattr`, so the same rule applies to them: a segment starting with an underscore is refused. A construct's `from` path and `list_to_dict_keyed_by` are refused when the bundle is validated, and every path is refused again when it is walked.

## What the sandbox does not cover

- **Resource use.** The sandbox limits what a template can reach, not what it can spend. Jinja caps `range`, and a longer range fails the render with `Jinja2TemplateRenderError`, but nothing caps exponentiation, string repetition, nested loops or output size.
- **The URLs values carry.** A template cannot forge content under this policy, but a value can still carry a URL, and reading it is the storage layer's decision, not the template's.

## Related

- [StuffArtefact & Image Rendering](stuffartefact-and-image-rendering.md): how inputs reach templates, and how images are extracted from them.
- [`Jinja2TemplateSecurityError`](../errors/jinja2-template-security-error.md): the error a refusal raises at render time.
