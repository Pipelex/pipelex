---
title: "Template Sandbox"
description: "Every Jinja2 template Pipelex renders runs under one sandbox policy: a template reads data and calls methods of plain values, and nothing else, within a budget of work per render."
---

# Template Sandbox

A method's templates are code. PipeLLM prompts, PipeCompose templates and construct templates, PipeImgGen and PipeSearch prompts, and PipeCondition expressions are all Jinja2 templates, and they render inside the process that runs the method. When that process is shared, as it is on a hosted runner, a template must not be able to reach anything but the data it was given.

Pipelex therefore renders every template, its own included, under one policy: **a template reads data and calls methods of plain values, and nothing else.** And because a template that only reads data can still ask for a billion-character string, every render also spends from a [budget of work](#the-render-budget), and a render that would overdraw it is refused before it allocates.

## What a template may do

| A template may | For example |
|---|---|
| Read the public fields of an input, with a dot or with brackets, the named parts of a `Composite` included | `{{ invoice.total }}`, `{{ invoice['total'] }}`, `{{ combo.summary }}` |
| Read an input's metadata fields | `{{ invoice._stuff_name }}`, `{{ invoice._content_class }}`, `{{ invoice._concept_code }}`, `{{ invoice._stuff_code }}` |
| Read any key of a plain dict with brackets, underscore keys included | `{{ record['_id'] }}`, `{{ record['__typename'] }}` |
| Call the dict-like accessors of an input | `{{ invoice.get('total') }}`, `{% for key, value in invoice.iter_items() %}` |
| Call the methods of strings, numbers, dates and times, lists, tuples, dicts and sets that read them | `{{ issued_at.isoformat() }}`, `{{ name.upper() }}`, `{{ record.get('a') }}` |
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
| Encode a string, or turn an integer into bytes | `{{ name.encode('utf-8') }}`, `{{ (1).to_bytes(8) }}` |
| Spend more than its render budget, or compute an integer wider than 64 bits | `{{ 'x' * 10 ** 9 }}`, `{{ 2 ** 70 }}` |
| Store a callable in a `namespace()` | `{% set ns.f = name.upper %}`, `namespace(items=doc.get)` |
| Include or extend another template | `{% include 'header.html' %}` |

A method template renders without a template loader, so `{% include %}`, `{% extends %}` and `{% import %}` find nothing to load.

## How a refusal shows up

Many refusals are visible in the template itself, and validation reports them before anything runs: a template that reads an undeclared underscore name with a dot fails with the `template_private_name` validation error, which names the pipe and the template (`prompt`, `system_prompt`, `template`, `expression`, or `construct field '<path>'`).

What validation cannot see, because it depends on the values at run time (a method call, a name computed while rendering, or a bracketed key, which is legitimate on a plain dict), is refused where it happens: the render raises [`Jinja2TemplateSecurityError`](../errors/jinja2-template-security-error.md), whose message names the refused attribute or callable and the type it was reached on. A refusal never renders as an empty string, so a prompt is never sent with a hole in it.

A render that would overdraw its budget raises [`Jinja2TemplateBudgetError`](../errors/jinja2-template-budget-error.md), in the input domain, whose message names the operation that was refused and what it would have spent, never the template or a value: for example, *the operator '\*' needs about 1,000,000,000, and 134,217,062 are left*. A template whose macros or includes nest deeper than Python allows raises the same error.

## How it is built

Every environment comes from one factory, `make_jinja2_env_from_loader` in `pipelex/tools/jinja2/jinja2_environment.py`, and that factory builds a `PipelexTemplateEnvironment` (`pipelex/tools/jinja2/jinja2_sandbox.py`), a subclass of Jinja's `ImmutableSandboxedEnvironment`. Rendering, parsing and compiling all go through it, including the condition pipe's compile at load and the load-time template walkers.

Jinja's stock sandbox refuses internals, but not public methods, and every pydantic model has public constructors. Under the stock sandbox a template could call `model_validate` on a content object and forge an image pointing at a storage key of its choosing. The Pipelex policy closes that by allowing calls by kind rather than by name:

- **Jinja's own runtime**: macros, `caller`, `loop`, `cycler`, `joiner`, block references, and the environment's globals.
- **Methods a plain value type defines**, bound to an instance of that type. A subclass of a plain type (a `StrEnum` member is a `str`) cannot add or override a callable method, and a class method is refused because it is bound to the class. The methods allowed are an audited list, `PLAIN_VALUE_METHOD_COSTS` in `pipelex/tools/jinja2/jinja2_render_costs.py`, which also gives each method's cost: a method that changes a list, a dict or a set in place, `str.encode` and `int.to_bytes` are left out, each with its reason in `REFUSED_PLAIN_VALUE_METHODS`, and a method a new Python release adds to a plain type is refused until it is classified.
- **The sandbox's own `str.format` wrapper**, which resolves replacement fields through the same attribute and item checks. The raw `str.format` stays refused.
- **The methods a type declares as its template surface** (`pipelex/tools/jinja2/template_surface.py`).

A type declares its template surface as a `__template_surface__` class attribute: the methods a template may call on an instance and the underscore names it may read. The sandbox reads the declaration from the type, never from the instance. `StuffArtefact`, the adapter every input is wrapped in, declares `get`, `iter_keys`, `iter_items` and `iter_values`, and its four metadata fields. The `Stuff` it wraps is not one of its attributes at all: Python code reaches it through `unwrap_stuff_artefact`, and its bracket access and `get` resolve a key to a content field or a metadata field only.

The sandbox refuses a bracketed name before trying `obj[name]`. Jinja only checks a bracketed name when the item lookup fails, so an object whose `__getitem__` answered any key would otherwise hand over what the dot spelling could not. A plain `dict` is the exception, because its items are data: a key it holds is returned, and a key it does not hold falls back to an attribute read, which the underscore rule refuses.

Filters are not calls in this sense: they are Pipelex's or Jinja's own code, registered by the environment. That makes each filter trusted code with one obligation: **a filter never calls a callable it was handed**, since that callable came from the template's values and the policy never vetted it. So `with_images`, `format` and `tag` call a value's rendering method only when the value's class defines it, and they check that on the type (`pipelex/tools/jinja2/renderable_dispatch.py`). A runtime-checkable Protocol alone would not do: on Python 3.11 it accepts a `namespace()` holding a callable of the template's choosing.

Jinja's own filters and markupsafe keep that obligation only for values whose attributes the template cannot choose: they look `__html__` up on a value when escaping, and `items` in `dictsort` and `xmlattr`, and call what they find. A `namespace()` answers any name with whatever the template stored under it, so the environment's `namespace` holds data only, and storing a callable in one, at construction or with `{% set ns.x = … %}`, is refused.

## The render budget

The sandbox limits what a template can reach, not what it can spend, and a template needs no forbidden call to be expensive: `{{ 'x' * 10 ** 9 }}`, a width in `'%1000000000s' % x`, the `center`, `batch` or `format` filters, a string doubled with `~` in a loop, two empty nested loops and a recursive macro each spend what the template asks. Rendering runs in the process that runs the method, on its event loop and sometimes inside a Temporal workflow, so on a shared runner one method's template would stall or exhaust a process that serves others. A timeout cannot help: a render never yields to the event loop, so nothing can interrupt it.

So every render gets a budget of work units, roughly one byte read or allocated each, and every operation spends from it. The default, `DEFAULT_RENDER_BUDGET_UNITS` in `pipelex/tools/jinja2/jinja2_render_budget.py`, is 128 Mi units: it prints about a hundred megabytes of text, and in the measurements behind it the slowest refusal of a hostile template took about half a second. A template included by another spends from its includer's budget, and a macro from its caller's, unless it was imported without `with context` (see below).

Each operation is charged for its inputs before it runs and for its result after. An operation whose result can outgrow its inputs, such as `*`, `**`, `%`, a format width, `center`, `ljust`, `replace`, `join`, `batch`, `wordwrap` or `lipsum`, is estimated first and refused before it allocates anything. An operation that reads a fixed part of its value, such as `length`, `first`, `default` or `dict.get`, is charged a step and its arguments, whatever the size of the value. An object of the run's data, such as a text content, is converted to count its text when an estimate needs it, so repeating it (`([doc] * 20000) | join`) is refused like repeating a string. `str.format` charges each replacement field as it formats it, with its spec resolved, so a width passed as an argument or through `format_map` counts. A filter that orders or deduplicates its input, `sort`, `dictsort`, `groupby`, `min`, `max` or `unique`, is charged for its comparisons, each weighing the heaviest key, read the way the filter reads it, and so are a list's or a tuple's `count` and `index`. Work that grows faster than an operation's result, such as `striptags`, `wordwrap` on long words or `sum` over lists, is spent at every call, not only checked. Integer arithmetic stops at 64 bits, which also keeps a template from building the huge integers whose hashing and printing cost the square of their size. Jinja's own cap on `range` still applies: a range of more than a hundred thousand items fails the render with `Jinja2TemplateRenderError`.

The environment charges through the sandbox's hooks and one rewrite, all in `PipelexTemplateEnvironment`. They rely on internals of Jinja 3.1, which is why Pipelex requires a Jinja below 3.2.

- **Calls and operators** go through the sandbox's `call` and `call_binop` hooks, and every arithmetic operator is intercepted.
- **Filters and tests** are wrapped before a template compiles. A filter or a test registered on the environment must have a cost in `FILTER_COSTS` or `TEST_COSTS` (`pipelex/tools/jinja2/jinja2_render_costs.py`), or the first compile fails with a `TypeError` naming it.
- **Printed values** go through the environment's `finalize`, which charges the text it produces. A caller's own `finalize` is passed to the constructor and runs first.
- **What no hook reaches**, which is loop iteration, `~`, comparisons, slices, list, tuple and dict literals and the template's static text, is routed through internal charging filters by a rewrite of the parsed template (`pipelex/tools/jinja2/jinja2_render_rewrite.py`). The rewrite changes what is charged, never what a template renders. A tuple used as a key, in a dict literal or an item read, is also charged for hashing, since a tuple hashes every element again each time.
- **Converting Markdown to HTML** is charged where it happens, in `pipelex/tools/markdown/markdown_parser.py`, since markupsafe converts a Markdown value through its `__html__` wherever an HTML template prints, escapes, joins or formats one, and no hook sees that call. The template makes its budget the active one while it renders, and the conversion charges it 2,048 units for every character of its source and every cell of its tables before it parses, then checks that its output, bounded from the parsed tokens, fits what is left before it renders, since a reference link is printed at every use. A conversion costs microseconds a character, so a render converts at most about 65,000 characters of Markdown, a document printed twice counting twice.

The budget is the same for every template category and is not a setting in `pipelex.toml`: it is a safety bound, not a tuning knob. `PipelexTemplateEnvironment` takes it as the `render_budget_units` constructor argument, which the tests use to exercise small budgets.

## Paths outside templates

A method also writes dotted paths that are not templates: a PipeCompose construct field's `from` and its `list_to_dict_keyed_by`, a PipeBatch's list, and the image and document references of a prompt. The runtime walks these with `getattr`, so the same rule applies to them: a segment starting with an underscore is refused. A construct's `from` path and `list_to_dict_keyed_by` are refused when the bundle is validated, and every path is refused again when it is walked.

## What the sandbox does not cover

- **What a whole run spends.** The budget is per render. A method that renders many templates, or a batch that renders one per item, spends one budget per render.
- **Macros imported without context.** A macro imported with `{% import %}` or `{% from … import %}` and no `with context` spends from the budget of the module Jinja builds for the import, which Jinja caches on the imported template. Pipelex builds a new environment for every render, so that budget never outlives one render, and a customer template has no loader to import from.
- **The URLs values carry.** A template cannot forge content under this policy, but a value can still carry a URL, and reading it is the storage layer's decision, not the template's.

## Related

- [StuffArtefact & Image Rendering](stuffartefact-and-image-rendering.md): how inputs reach templates, and how images are extracted from them.
- [`Jinja2TemplateSecurityError`](../errors/jinja2-template-security-error.md): the error a refusal raises at render time.
- [`Jinja2TemplateBudgetError`](../errors/jinja2-template-budget-error.md): the error a render raises when it would overdraw its budget.
