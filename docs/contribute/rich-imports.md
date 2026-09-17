---
title: "Rich Imports"
description: "Rich is the cli extra: where the runtime may import it, how a rendering outside the CLI imports it, and the guard and the test that hold a server free of it."
---

# Rich imports

[Rich](https://github.com/Textualize/rich) renders everything Pipelex shows in a terminal: the CLI's tables and panels, the `console` log sink, the "Output of pipe" panels of the `rich` pretty-print mode. None of that has a place in a server, which writes JSON lines to a log agent and prints nothing. So Rich is not a core dependency of `pipelex`. It is the **`cli` extra**, which the command-line tools install and a server leaves out:

```bash
uv tool install "pipelex[cli]"   # the pipelex and pipelex-agent commands
uv pip install pipelex           # a process that embeds the runtime
```

That split holds only if the runtime never imports Rich on the way to running a method. This page is the specification of the convention that keeps it so, and of the checks that enforce it.

## The rule

> **Outside `pipelex/cli/`, no module imports Rich at module level, and no module reaches Rich through a module-level import of a CLI module.**

The CLI package installs the extra, so its modules import Rich at the top of the file like any other dependency. Every other module that renders through Rich imports it inside the function that renders, so importing the module costs a process without Rich nothing.

"Module level" means what importing the module executes. An import statement counts wherever it sits outside a function body: at the top of the file, inside a module-level `try` or `if` block, in a class body. Two places are exempt, because nothing in them runs at import time:

- a function or coroutine body;
- the body of an `if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:` block. Its `else` branch is runtime code and is checked, and so is the body of `if not TYPE_CHECKING:`.

There is no escape hatch. A module that genuinely needs Rich at import time is a CLI module, and it belongs under `pipelex/cli/`.

## Rendering through Rich outside the CLI

A function that renders checks that Rich is installed first, then imports what it renders with. The check raises `MissingDependencyError`, which names the `cli` extra and the install command, so a process without Rich gets an instruction rather than a bare `ModuleNotFoundError`:

```python
from typing import TYPE_CHECKING

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.pretty import require_rich_for_rendering

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable


class TextContent(StuffContent):
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> "PrettyPrintable":
        require_rich_for_rendering()
        from rich.markdown import Markdown

        return Markdown(self.text)
```

- **`require_rich_for_rendering()`** (`pipelex.tools.misc.pretty`) is the check for a rendering: the `rendered_pretty` methods of the content types and the builder specs, and the `rich` pretty-print mode. Its message points at the Rich-free pretty-print modes as well as at the extra.
- **`require_rich(message=...)`** (`pipelex.tools.misc.rich_extra`) is the check for anything else, with a message saying what needed Rich: the `console` log sink uses it, and so does `get_console()`.
- **`is_rich_installed()`**, in the same module, answers without raising, for a caller that has a Rich-free fallback. The stuff viewer page uses it, and shows the JSON rendering in its Pretty tab when Rich is absent.
- **A type-only import goes under `if TYPE_CHECKING:`.** In a module with `from __future__ import annotations`, the annotation can stay unquoted; in a pydantic model module without it, quote the annotation, as `"PrettyPrintable"` is quoted above, since pydantic resolves annotations at class creation.

Ruff agrees with the convention: `pyproject.toml` bans `rich` as a module-level import under `flake8-tidy-imports.banned-module-level-imports` (rule `TID253`), which also exempts a deferred Rich import from `import-outside-top-level`, so none needs a suppression comment. The CLI package and the test suite, which installs every extra, are exempt from the ban in `per-file-ignores`. The ruff rule gives the warning in the editor; the guard below is the gate, because ruff sees neither the import graph nor the allowlist as one declaration.

## What a process without Rich gives up

Nothing a server needs. What needs Rich stops as early as it can, naming the extra:

| Surface | Without Rich |
|---------|--------------|
| `sink = "console"` in `[runtime.log]` | The boot stops, naming the extra and the `json` sink. |
| `pretty_print_mode = "rich"` in `[runtime.log]` | The boot stops, naming the extra and the `poor` and `silent` modes. |
| `pretty_print_mode = "poor"` | Plain text in a drawn frame, with no Rich import. A panel title's Rich markup is read by a Rich-free parser, `plain_markup_text`, which follows Rich's own tag grammar. |
| `pretty_print_mode = "silent"` | Nothing is built or printed. |
| `get_console()` | Raises `MissingDependencyError` when called. |
| A `rendered_pretty()` or `rendered_pretty_text()` call | Raises `MissingDependencyError`. |
| The stuff viewer page | The Pretty tab shows the JSON rendering. |

The boot checks the sink and the pretty-print mode together, in `runtime_boot.py`, so a server that forgot either setting fails at startup rather than at the first pipe that logs or prints its output.

## Enforcement

The convention is checked twice, by a static guard and by a run, because they fail independently: the guard reads source and cannot see an import assembled at runtime or one a dependency performs, and the run covers one path through the runtime rather than every module.

### The rule: `make check-rich-imports`

```bash
make check-rich-imports   # alias: make cri
```

An AST guard (`pipelex-dev check-rich-imports`, core in `pipelex/cli/dev_cli/commands/rich_import_guard.py`) that runs in `make agent-check`, in the `make check` aggregate, and in CI as the `Lint (rich imports)` job and a step of the pre-main fresh lint. It scans `pipelex/` and checks two rules:

1. **The direct rule.** A module outside `pipelex/cli/` may not import `rich` or any `rich.*` module at module level. The match is on the package boundary, so a module named `richer` or `rich_extra` is not Rich, and a relative import never is.
2. **The transitive rule.** A module outside `pipelex/cli/` may not reach a CLI module that imports Rich at module level, through any chain of module-level imports. It walks the module-level import graph the [hub-layering guard](hub-layering.md) builds, with the same carve-outs and the same modelling of the package `__init__.py` files an import executes on the way, and reports the shortest chain at the line of its first hop. A module outside the CLI that imports Rich itself is the direct rule's finding only: removing that import is the fix for every module that reaches it.

The guard refuses to pass vacuously: a scan root that yields no module, none under `pipelex/cli/`, or an import graph that does not hold the modules the scan read raises instead of reporting a pass.

### The property: `tests/integration/pipelex/test_rich_free_run.py`

The test runs, in a subprocess, what a server does. A meta-path finder installed before the first `pipelex` import raises `ImportError` for `rich` and every `rich.*` module. The subprocess then boots the kernel with `sink = "json"`, runs a `PipeCompose` pipe in direct mode through `PipelexMTHDSProtocol`, which needs no inference and prints the operator's "Output of pipe" panel, and asserts that the run returns its output and that no Rich module was loaded. It runs once in the `silent` mode, where every line on stderr must be a JSON log record, and once in the `poor` mode, where the panel must print as plain text. A third case boots with `pretty_print_mode = "rich"` and asserts the boot refusal names the extra.

A subprocess is required rather than preferred: the test process has Rich loaded, since the suite installs every extra, and evicting it from `sys.modules` would leave duplicate classes behind for every later test.

The test blocks Rich rather than checking that it is absent from an ordinary environment, because an environment is not the measure. Whether Rich is installed also depends on what the other dependencies of `pipelex` require, and some third-party packages import Rich whenever it is installed. What the runtime owns is that it never needs Rich on a server's path, and that is what the blocked run measures.

`tests/unit/pipelex/tools/test_log_console_sink_without_rich.py` pins the `console` sink's own refusal the same way, and `tests/unit/pipelex/tools/misc/test_plain_markup_text.py` compares the Rich-free markup reading with Rich's.
