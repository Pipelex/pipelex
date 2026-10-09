---
title: "Log-Call Guard"
description: "The guard that holds Pipelex's own log calls to the log-call conventions: what it reads, what it refuses, and the baseline that only shrinks."
---

# Log-call guard

Pipelex's log calls follow the [log-call conventions](../tools/logging.md#log-call-conventions): a fixed message, its values in `fields`, no markup. Most of them are for review; the ones that can be read off the source are held by `make check-log-calls` on every call: a message at INFO and above is a literal written at the call, and no message holds Rich markup at any level. This page is the guard's specification. The calls that broke the rules when the guard arrived are listed in a committed baseline that can only shrink, so that new code is held to the conventions from the start while the existing calls are converted.

## What it reads

The guard parses every Python module in `pipelex/`, except the facade's own package `pipelex/tools/log/`, and in the API server's `api/pipelex_api/`, which logs through the same facade. It reads the calls of the `log` facade: a method call on the name a module imports `log` under, from `pipelex` or from `pipelex.tools.log.log`, an alias included. A call's message is its first positional argument, or its `content=` keyword, and its `title=` and `inline=` keywords count as part of it, since the dispatch renders both into the message.

## The rules

### A literal message at INFO and above

On `log.info`, `log.warning`, `log.error` and `log.critical`, the message is a literal written at the call. These are accepted:

- a string constant, implicit concatenation of constants included;
- an f-string without a placeholder;
- a `+` between literals, or a conditional expression between literals;
- a name whose every binding, in the enclosing function or at module level, is one of the above.

Anything else is refused, under the name of its form:

| Rule | What it refuses |
| --- | --- |
| `f-string` | An f-string with a placeholder, `f"Loaded '{alias}'"` |
| `percent-format` | A `%` format, `"Loaded %s" % alias` |
| `concatenation` | A `+` with a side that is not a literal, `"Loaded " + alias`, or a name extended with `+=` |
| `format-call` | A `.format()` call, `"Loaded {}".format(alias)` |
| `non-literal` | Any other expression: a parameter, an attribute, a call's result, a mapping or a model |

A name is read through its bindings in the function that makes the call, then at module level when the function does not bind it. A name bound to an f-string is refused as an `f-string`, the report naming the line of the binding; a name the function receives as a parameter, binds in a loop or a `with`, or does not bind at all is `non-literal`. A variable captured from an enclosing function is not followed, and is `non-literal` too.

The `non-literal` rule is the guard's choice rather than the conventions' letter: it refuses a message built elsewhere and passed in, by a helper or a caller, because nothing can tell that such a message is fixed, and every one the first census found was in fact built from values. A message that must vary is a fixed message with fields. A structured content, a mapping or a model logged as the message, is `non-literal` at INFO and above for the same reason: its values belong in fields, and its payload belongs nowhere.

`log.debug` and `log.verbose` are outside this rule: a person at a terminal reads them, and an f-string is allowed there.

### No markup at any level

On every method, `log.verbose` and `log.debug` included, no literal text of a message, its title or its inline title holds a Rich markup tag. The literal text is the string constants written at the call, the literal parts of an f-string, the format string of a `%` or a `.format()`, and the literals a name read as above is bound to.

A markup tag is what Rich reads as one, matched with Rich's own tag pattern:

- a closing tag, `[/red]` or `[/]`;
- an `@` handler, `[@click=app.bell]`;
- an opening tag whose text Rich parses as a style, `[red]`, `[bold green]`, `[on blue]`, `[link=https://pipelex.com]`, or names a style of Rich's default theme, `[repr.number]`.

A bracketed word that is no style, `list[int]`, `[Errno 2]` or `items[index]`, is text and passes, and so does a tag escaped with a backslash.

## The baseline

`log_call_baseline.toml`, at the repo root, lists every call that broke a rule when the guard arrived. Its key is the call's file and enclosing qualified name, `<relative_path>::<qualified_name>`, the classes and functions joined by dots, or `<module>` for a call made at module level. Under the key, each call is listed by its **signature**, its method and its message's source text, once per call that carries it:

```toml
version = 1

["pipelex/methods/fetch_on_miss.py::resolve_address_based_method"]
calls = [
  "info: f\"Fetched method '{fetched.full_address}' at commit {fetched.commit_sha} and installed it into '{installed.path}'\"",
]
```

A line number never enters the baseline, so an edit elsewhere in a file moves nothing. A signature is rendered the same on every Python the check runs on: `ast.unparse` writes an f-string by quoting rules that changed with Python 3.12, so the guard writes f-strings itself, and everything else through `ast.unparse`, whose output for other expressions does not move.

The comparison is exact, both ways:

- **A call the baseline does not list fails the check.** That is every new call that breaks a rule, and a second identical call beside a listed one.
- **A listed signature no call carries any more fails the check too**, until it is removed from the file: the call now complies, or it moved to another function, or its message changed. The check names the stale signature.

So changing a listed call's message, or moving the call, is converting it: its old signature goes stale, and the new form must comply, since nothing lists it. The baseline is never added to. It is the debt the conversion of the existing calls pays off, and it ends empty.

## Running it

`make check-log-calls`, alias `make clc`, runs `pipelex-dev check-log-calls --quiet`. It is part of `make agent-check` and `make check`, and CI runs it as the `Lint (log calls)` job, which `Lint (all)` requires, and in the pre-main fresh check. Run directly, the command takes three options:

- `--quiet` keeps a pass to one line, which says how many calls the baseline still lists; a failure always prints in full.
- `--prune` removes the stale signatures from the baseline, then checks. It never adds one, so a call the baseline does not list still fails.
- `--report` prints the baseline's calls by package area, the largest first, and gates nothing: the measure of what is left to convert.

A failure lists each call the baseline does not list, at its file and line, with its enclosing qualified name and every rule it breaks, then each rule's remedy, then each stale signature under its key.

## Converting a call

1. Rewrite the call by the [conventions](../tools/logging.md#log-call-conventions): a fixed message, its values in `fields` under the names of the vocabulary table, a handled exception through `error_fields` at WARNING and below or `include_exception=True` at ERROR and above.
2. Run `make check-log-calls`. It reports the call's signature as stale.
3. Remove the signature, by hand or with `.venv/bin/pipelex-dev check-log-calls --prune`, and commit the file with the change.

`pipelex/libraries/library_manager.py` is the worked example: every one of its calls follows the conventions, its warnings as fixed messages with fields, and it has no baseline entry.

There is no escape hatch, no comment that exempts a call: a message that has to vary is a fixed message with fields.
