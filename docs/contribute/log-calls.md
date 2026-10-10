---
title: "Log-Call Guard"
description: "The guard that holds Pipelex's own log calls to the log-call conventions: what it reads, what it refuses, and the baseline that only shrinks."
---

# Log-call guard

Pipelex's log calls follow the [log-call conventions](../tools/logging.md#log-call-conventions): a fixed message, worded as one short sentence, its values in `fields`, no markup and no exception in its text. Most of them are for review; the ones that can be read off the source are held by `make check-log-calls` on every call: a message at INFO and above is a literal written at the call, no message holds Rich markup, a message keeps the mechanical rules of its wording, and no message splices a handled exception into its text. This page is the guard's specification. The calls that broke the rules when the guard arrived were listed in a committed baseline that can only shrink, so that new code was held to the conventions from the start while the existing calls were converted. Every one of them has been converted since: the baseline lists no call, and since it can only shrink, it stays empty, so every log call is held to the rules.

## What it reads

The guard parses every Python module in `pipelex/`, except the facade's own package `pipelex/tools/log/`, and in the API server's `api/pipelex_api/`, which logs through the same facade. It reads the calls of the `log` facade, however a module reaches it: the name it imports `log` under, from `pipelex` or from `pipelex.tools.log.log`, an alias, a relative import and a star import included, or an attribute path through a module it imports, `pipelex.log.warning(...)` after `import pipelex`, `m.log.info(...)` after `from pipelex.tools.log import log as m`, `x.log.info(...)` after `import pipelex.tools.log.log as x`. The receiver is read where the call is made, through the bindings of its name that can reach the call, as a message's names are below, save that a name captured from an enclosing function is followed, through every binding that function makes: it is the facade when one of them imports the facade, so a parameter or a local named `log`, a stdlib logger say, is not the facade, and neither is a `log` imported in another function, while one imported in an enclosing function is. A call's message is its first positional argument, or its `content=` keyword, and its `title=` and `inline=` keywords count as part of it, since the dispatch renders both into the message. A title or an inline title that is statically `None`, `title=None` or a name bound only to `None` and literals, is no message text at all. A `**` expansion of a dict literal whose keys are all strings passes its `content`, `title` and `inline` entries like keywords, `log.warning(**{"content": f"Value {value}"})` being read as `log.warning(content=f"Value {value}")`; any other `**` expansion in a facade call, `log.warning(**params)`, could carry the message or a title, so the call is refused as `non-literal`, at every level, since no rule can read through it.

## The rules

### A literal message at INFO and above

On `log.info`, `log.warning`, `log.error` and `log.critical`, the message is a literal written at the call. These are accepted:

- a string constant, implicit concatenation of constants included;
- an f-string without a placeholder;
- a `+` between literals, or a conditional expression between literals;
- a name whose every binding that can reach the call is one of the above, `msg += " the library"` and `msg = msg + " the library"` included when what is added is a literal.

Anything else is refused, under the name of its form:

| Rule | What it refuses |
| --- | --- |
| `f-string` | An f-string with a placeholder, `f"Loaded '{alias}'"` |
| `percent-format` | A `%` format, `"Loaded %s" % alias`, or a name formatted with `%=` |
| `concatenation` | A `+` with a side that is not a literal, `"Loaded " + alias`, or a name extended with `+=` by something that is not |
| `format-call` | A `.format()` call, `"Loaded {}".format(alias)` |
| `non-literal` | Any other expression: a parameter, an attribute, a call's result, a mapping or a model, and a `**` expansion the guard cannot read |

A name is resolved by Python's own scoping. The scope the call is made in comes first, a comprehension reading as part of the scope it is written in; then the enclosing functions, a class body never being one; then the module.

Within that scope, only the bindings that can reach the read count, by the scope's control flow: along straight-line code, the nearest binding before the read; across the branches of an `if`, a `try` or a `match`, the nearest on each path, a handler seeing whatever its `try` body had bound by then; in a loop, a binding later in its body too, which the next pass carries back; and after a `return`, a `raise`, a `break` or a `continue`, nothing. So `msg = "Loaded"`, `log.info(msg)`, then `msg = f"Could not load {alias}"` and `raise ValueError(msg)` passes: the later binding cannot reach the call, and stays out of its signature. A binding's own value is read where that binding stands, so in `msg = msg + "red]Loaded"` the `msg` added to is the one bound before. Where the flow depends on what runs, the guard counts what may: a `with` body may stop at any line, since its context manager may swallow an exception, and a comprehension's body may run any number of times. A module name read from a class body counts the module's bindings that reach the class statement; read from a function, also every module binding made after the function's definition, since the function may be called at any later point. A `global` or `nonlocal` assignment counts as a binding of the scope that owns the name, and reaches every read of it, since the function making it may run at any time. One index of every scope's bindings and control flow is built per module, in one walk, then each scope's flow is run once, so a lookup never reads a scope again.

A binding is what Python counts as one: an assignment to the name itself or through a tuple, a list or a starred target, an annotated or augmented assignment, a `:=`, a `for`, `with` or `except ... as` target, a comprehension target, a `match` capture, a parameter of a function or a lambda, an import and a definition. An assignment that only mentions the name, `cache[msg] = 1` or `msg.attr = value`, does not rebind it. A name bound to an f-string is refused as an `f-string`, the report naming the line of the binding; a name bound by anything the guard does not read, a parameter, a loop or comprehension target, a `with` or `except` target, a `match` capture, an unpacking, an import, or not bound at all, is `non-literal`. A name bound in an enclosing function is not followed, and is `non-literal` too, whatever the module binds under the same name.

The `non-literal` rule is the guard's choice rather than the conventions' letter: it refuses a message built elsewhere and passed in, by a helper or a caller, because nothing can tell that such a message is fixed, and every one the first census found was in fact built from values. A message that must vary is a fixed message with fields. A structured content, a mapping or a model logged as the message, is `non-literal` at INFO and above for the same reason: its values belong in fields, and its payload belongs nowhere.

`log.debug` and `log.verbose` are outside this rule: a person at a terminal reads them, and an f-string is allowed there.

### No markup at any level

On every method, `log.verbose` and `log.debug` included, no literal text of a message, its title or its inline title holds a Rich markup tag. The literal text is the string constants written at the call, the literal parts of an f-string, the format string of a `%` or a `.format()`, and the literals a name read as above is bound to. It is read the way it reaches the console: a `+` whose operands are known, named literals, `+=` extensions and a name rebuilt from itself included, is folded into one text before the scan, so `"[" + "red]Loaded"` holds `[red]`, while a value the guard cannot read keeps the texts around it apart, and so does a `+` whose two sides could combine into more texts than a fixed bound, each side then scanned on its own.

A markup tag is what Rich reads as one, matched with Rich's own tag pattern:

- a closing tag, `[/red]` or `[/]`;
- an `@` handler, `[@click=app.bell]`;
- an opening tag whose text Rich parses as a style, `[red]`, `[bold green]`, `[on blue]`, `[link=https://pipelex.com]`, or names a style of Rich's default theme, `[repr.number]`.

A bracketed word that is no style, `list[int]`, `[Errno 2]` or `items[index]`, is text and passes, and so does a tag escaped with a backslash. The tests that check the messages a live run logs, described under [Messages are plain text](../tools/logging.md#messages-are-plain-text), read tags by this same rule, the guard's `find_markup_tags`, so the source and the run are held to one definition.

### The wording of a message

The text of a message is held to the rules of [Wording a message](../tools/logging.md#wording-a-message) that can be read off the source; the rest of that section, the subject first, one thing per sentence, the past tense, is for review.

| Rule | Where | What it refuses |
| --- | --- | --- |
| `lowercase-start` | Every level | A message whose first letter is lowercase, `"loaded the library"`, leading whitespace skipped |
| `trailing-period` | Every level | A message that ends with a period or an ellipsis, `.`, `...` or `…`, trailing whitespace skipped |
| `backtick` | Every level | A backtick anywhere in the message |
| `identifier` | INFO and above | A word holding an underscore, `needs_inference` or `PIPELEX_API_KEY`, or a call written with empty parentheses, `setup()` or `Loader.load()` |
| `length` | INFO and above | A message of more than 80 characters |

A word of Pipelex's own vocabulary is a word like any other, so `PipeBatch`, `METHODS.toml` and a plural written `model(s)` pass. On `log.debug` and `log.verbose`, which a person at a terminal reads, a message may name an identifier and run long, but it still starts with a capital, ends with no period and holds no backtick.

The rules read the text the markup rule reads: the literal text of the message, of its title and of its inline title, each as a text of its own, folded across concatenations, named literals and `+=` extensions the way it reaches the console, the format string of a `%` or a `.format()` read as written. A message can reach the console as several texts, a conditional between two literals or a name bound to a different literal on each branch, and each of them is read: one that breaks a rule is enough, so `"Loaded" if cached else "loading..."` breaks `lowercase-start` and `trailing-period`.

A value the guard cannot read, an f-string's placeholder or a name bound to no literal, keeps the texts around it apart, as it does for markup, and could be anything. So a text that starts with such a value passes `lowercase-start`, `f"{count} pipes were loaded"`, and one that ends with one passes `trailing-period`, while `backtick` and `identifier` read every literal part, never across a value. A `+` whose two sides could combine into more texts than the fold's bound reads as if such a value stood between them: its left side keeps the start of the message, its right side the end. The length counts the literal parts alone, since a value is at least empty: a message whose literal text runs past 80 characters is refused whatever it splices, `the message is at least 95 characters long`, while one that only its values would push past the bound is not. At INFO and above the message is a literal anyway, by the first rule, so the length is exact there for every message that passes that rule.

### No exception in the text

On every method, no value a message splices into its text reaches a handled exception, which rides the record or its fields and never the message, as [Exceptions](../tools/logging.md#exceptions) explains. A call that breaks it is refused as `spliced-exception`.

The values a message splices are an f-string's placeholders, the right operand of a `%`, the arguments of a `.format()` call, and any part of the message that is no literal text, a call's result or an attribute, the message itself included: `log.debug(exc)` and `log.debug("A cleanup failed: " + str(exc))` splice the exception as surely as `log.debug(f"A cleanup failed: {exc}")`. A message held in a name is read through its bindings, as above, so `msg = f"A cleanup failed: {exc}"` then `log.debug(msg)` is refused too.

A spliced value reaches a handled exception when it:

- reads a name one of whose bindings that can reach the read is an `except ... as` target, `{exc}`, `{exc!r}` or `{type(exc).__name__}`;
- reads a name bound to a value that reaches one in turn, however many bindings away, `detail = str(exc)` then `{detail}`;
- calls a method named `exception`, a finished task's `t.exception()`, a retry outcome's or `sys.exception()`, which return an exception no handler binds.

A name captured from an enclosing function is read through every binding that function makes, as the facade's receiver is, so a callback a handler registers, `lambda: log.debug(f"A cleanup failed: {exc}")`, splices the handler's exception. A name bound by a handler and rebound before the read holds what it was rebound to, and a handler's target reaches nothing past its handler, where Python deletes it. A value that reaches the exception counts whatever it takes from it, its text, its class's name or a count of its errors: what a line needs of an exception rides in `error_fields`, and anything else in a field of its own.

## The baseline

`log_call_baseline.toml`, at the repo root, lists the calls exempted from the rules until they are converted. It started with every call that broke one when the guard arrived, and lists none now that they are all converted. Its key is the call's file and enclosing qualified name, `<relative_path>::<qualified_name>`, the classes and functions joined by dots, or `<module>` for a call made at module level. Under the key, each call is listed by its **signature**, once per call that carries it. A signature is the call's method, its message's source text with any `**` expansion it cannot read, the rules it breaks between brackets, and, after `where`, every binding the guard read to judge it, sorted, which is every binding that can reach the names it read, a binding it does not read written as what binds it (`<parameter>`, `<for target>`, `<enclosing function>`, `<unbound>`), and, for a call that splices an exception, the bindings that exception is reached through, the handler's own binding written as `<except target>`. In a baseline that still listed calls, two entries would read like these, made up for the example:

```toml
version = 1

["pipelex/example/bundle_loader.py::BundleLoader.load"]
calls = [
  "info: f\"Loaded the bundle '{bundle_path}' with {pipe_count} pipes\" [f-string]",
]

["pipelex/example/bundle_loader.py::report_load_failure"]
calls = [
  "warning: message [f-string] where message = f\"Could not load the bundle '{bundle_path}': {load_error}\"",
]
```

So the identity of a call is what it logs, not only how the call is written: rewording the f-string a grandfathered `log.warning(message)` is bound to, or adding markup to a module constant its message concatenates, changes its signature, and the exemption is spent. A line number never enters the baseline, so an edit elsewhere in a file moves nothing. A signature is rendered the same on every Python the check runs on: `ast.unparse` writes an f-string by quoting rules that changed with Python 3.12, so the guard writes f-strings itself, and everything else through `ast.unparse`, whose output for other expressions does not move. The file is written through the repo's TOML writer (`pipelex/tools/misc/toml_utils.py`, tomlkit), laid out exactly as `make format` leaves it, so a prune moves nothing else.

The comparison is exact, both ways:

- **A call the baseline does not list fails the check.** That is every new call that breaks a rule, and a second identical call beside a listed one.
- **A listed signature no call carries any more fails the check too**, until it is removed from the file: the call now complies, or it moved to another function, or its message, a binding of it or the rules it breaks changed. The check names the stale signature.

So changing a listed call's message, or moving the call, is converting it: its old signature goes stale, and the new form must comply, since nothing lists it.

### It only shrinks

Agreeing with the tree is not enough, since a change could add a violating call and its entry together. So the check also holds the baseline to the one committed at a trusted revision, the base the change merges into, read with `git show <ref>:log_call_baseline.toml`: a signature the working baseline lists more times than the trusted one, a new entry or a higher count, fails, named under its key with both counts. Removing an entry, or a call, always passes. A trusted revision that runs the guard but holds no baseline file has an empty one; a revision from before the guard existed has nothing to compare with, and the check says so and runs against the tree alone. A trusted revision that does not resolve, or whose baseline is of another `version`, fails the check: a gate that cannot compare does not pass. A future change to the signature's format bumps `version` and has to teach the comparison to read the previous one.

The baseline is never added to. It is the debt the conversion of the existing calls pays off, and it ends empty.

## Running it

`make check-log-calls`, alias `make clc`, runs `pipelex-dev check-log-calls --quiet --against-merge-base origin/dev`, so a local run holds the baseline to the one at the merge base of `HEAD` and `origin/dev`, and says plainly when that merge base does not resolve, `origin/dev` not fetched for instance. `make check-log-calls LOG_CALL_BASELINE_REF=<ref>` compares with another revision. It is part of `make agent-check` and `make check`. CI runs it as the `Lint (log calls)` job, which `Lint (all)` requires, fetching the pull request's base and passing it as `LOG_CALL_BASELINE_REF`, and in the pre-main fresh check the same way; a manual run of the fresh check has no pull request base, and says it checks the tree alone. Run directly, the command takes these options:

- `--quiet` keeps a pass to one line, which says how many calls the baseline still lists and, when it compared, that it adds nothing to the trusted revision; a failure always prints in full.
- `--prune` removes the stale signatures from the baseline, then checks. It never adds one, so a call the baseline does not list still fails.
- `--report` prints the baseline's calls by package area, the largest first, and gates nothing: the measure of what is left to convert.
- `--against <ref>` holds the baseline to the one committed at `<ref>`, which must resolve.
- `--against-merge-base <ref>` holds it to the one at the merge base of `HEAD` and `<ref>`, and skips the comparison, saying so, when that merge base does not resolve. It and `--against` are exclusive.

A failure lists each call the baseline does not list, at its file and line, with its enclosing qualified name and every rule it breaks, then each rule's remedy, then each stale signature under its key, then each signature added since the trusted revision.

## Converting a call

1. Rewrite the call by the [conventions](../tools/logging.md#log-call-conventions): a fixed message worded as [Wording a message](../tools/logging.md#wording-a-message) says, its advice in `user_action`, its values in `fields` under the names of the vocabulary table, a handled exception through `error_fields` at WARNING and below or `include_exception=True` at ERROR and above, except one that is re-raised, one that failed while another propagated and a swallowed `ValidationError`, which ride as `error_fields` at every level.
2. Run `make check-log-calls`. It reports the call's signature as stale; editing what a listed call logs without converting it reports the old signature as stale and the new one as unlisted.
3. Remove the signature, by hand or with `.venv/bin/pipelex-dev check-log-calls --prune`, and commit the file with the change.

`pipelex/libraries/library_manager.py` is the worked example: every one of its calls follows the conventions, its warnings as fixed messages with fields, and it has no baseline entry.

There is no escape hatch, no comment that exempts a call: a message that has to vary is a fixed message with fields.
