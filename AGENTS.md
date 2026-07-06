# Pipelex Coding Rules

## Codex Cloud Commands

### Linting

   After making code changes, you must always lint using `make agent-check`.

   ```bash
   make agent-check
   # If the current system doesn't have the `make` command,
   # lookup the "agent-check" target in the Makefile and run the commands one by one (targets fix-unused-imports format lint pyright mypy)
   ```

   This runs multiple code quality tools:
   - Pyright: Static type checking
   - Ruff: Fix unused imports, lint, format  
   - Mypy: Static type checker
   - plxt: Format and lint TOML, MTHDS, and PLX files

   Always fix any issues reported by these tools before proceeding.

### Keyword-only arguments check

   Non-subject function parameters across `pipelex/` source must be keyword-only (a bare `*` after the subject). The convention is mechanically enforced and already runs as part of `make agent-check`, but you can invoke it on its own:

   ```bash
   make check-keyword-only   # alias: make cko — read-only gate; hard-blocks on any violation
   make fix-keyword-only     # alias: make fko — auto-insert a bare * for mechanically-fixable violations
   ```

   `check-keyword-only` owns the pass/fail gate; `fix-keyword-only` rewrites what it can and reports the shapes it can't fix mechanically (resolve those by hand). See [`docs/contribute/keyword-only-arguments.md`](docs/contribute/keyword-only-arguments.md) for the full convention.

### Cleaning Derived Files

   If you need to clean derived files and caches, typically after you erased files or moved tests, the linters can get confused, the pytest collection can be off...

   ```bash
   make cleanderived
   ```

### Running Tests in Codex Cloud

    To test everything that can be tested from within the Codex Cloud sandbox, run this:

    ```bash
    make codex-tests
    # It's equivalent to running pytest with `-m "(dry_runnable or not inference) and not (pipelex_api or codex_disabled)"`
    # If some test fails, re-run it with `-s -vv` to see more details
    ```

---

### Prerequisites for running command lines: use virtual environment

   **CRITICAL**: Before running any `pipelex` commands or `pytest`, you MUST use the appropriate Python virtual environment. The only exceptions are our `make` commands which already include the env activation.

   Call the CLI directly from the virtual environment:

   ```bash
   .venv/bin/pytest -s -v -k test_render_jinja2_from_text
   .venv/bin/pipelex validate --all
   ```

   For standard installations, the virtual environment is named `.venv`. Always check this first. On Windows, the path is `.venv\Scripts\` instead of `.venv/bin/`.

### Pipelex Dev CLI (`pipelex-dev`)

   The `pipelex-dev` CLI provides internal development tools that are not distributed with the package. It is available in the virtual environment.

   ```bash
   .venv/bin/pipelex-dev --help
   ```

   Key commands:

   - **`generate-mthds-schema`**: Regenerate the MTHDS JSON Schema (`derived/mthds_schema.json`). Run this after modifying `mthds_schema_generator.py`.

     ```bash
     .venv/bin/pipelex-dev generate-mthds-schema
     ```

   - **`generate-error-pages`**: Regenerate the per-class error reference pages under `docs/errors/` — one Markdown page per `PipelexError` subclass, which is what each error's `type_uri` dereferences to. Run after adding or renaming an error class. Pages a maintainer claims with a `<!-- pipelex:authored -->` marker are preserved across runs. Also available as `make generate-error-pages` (alias `make gep`).

     ```bash
     .venv/bin/pipelex-dev generate-error-pages
     ```

### Pipelex CLI Commands

   To run the Pipelex CLI commands without the logo, you can use the `--no-logo` flag, this will avoid useless tokens in the console output.

   ```bash
   .venv/bin/pipelex --help
   .venv/bin/pipelex build --help --no-logo
   .venv/bin/pipelex run --help --no-logo
   .venv/bin/pipelex validate --help --no-logo
   .venv/bin/pipelex doctor --help --no-logo
   .venv/bin/pipelex init --help --no-logo
   ```

## Coding Standards & Best Practices for Python Code

### Python Version Compatibility

- The project supports Python 3.11+ (`requires-python = ">=3.11,<3.15"`). Never use features introduced after Python 3.11 without a compatibility fallback.
- `StrEnum`, `Self`, `datetime.UTC`, `tomllib`, and `ExceptionGroup` / `except*` are all available at 3.11 — use them directly, no shim.
- Common pitfalls:
  - `StrEnum` is still imported from `pipelex.types` (the project's single canonical import site), not from `enum` directly.
  - `type` statement (PEP 695) was added in Python 3.12. Use `TypeAlias` from `typing` instead.

### Variables, loops and indexes

- Variable names should have a minimum length of 3 characters. No exceptions: name your `for` loop indexes like `index_foobar`, your exceptions `exc` or more specific like `validation_error` when there are several layers of exceptions, and use `for key, value in ...` for key/value pairs.
- When looping on the keys of a dict, use `for key in the_dict` rather than `for key in the_dict.keys()` otherwise you won't pass linting.
- Avoid inline for loops, unless it's ultra-simple and holds on oneline.
- If you have a variable that will get its value differently through different code paths, declare it first with a type, e.g. `pipe_code: str` but DO NOT give it a default value like `pipe_code: str = ""` unless it's really justified. We want the variable to be unbound until all paths are covered, and the linters will help us avoid bugs this way.

### Enums and tests

- When defining enums related to string values, always inherit from `StrEnum`
- When you need the enum value as a string, don't use `str(enum_var)` or `enum_var.value`, just use `enum_var` itself, that is the point of using StrEnum!
- Never test equality to an enum value: use match/case, even to single out 1 case out of 10 cases. To avoid heavy match/case code in awkward places, add @property methods to the enum class such as `is_foobar()`. This is to avoid bugs: when new enum values are added we want the linter to complain. Use the `|` operator to group cases
- As our match/case constructs over enums are always exhaustive, NEVER add a default `case _: ...`. Otherwise, you won't pass linting.
- `StrEnum` must be imported from `pipelex.types` (the project's single canonical import site):
  ```python
  from pipelex.types import StrEnum
  ```

### Optionals

- Don't write things like `a = b if b else c`, write `a = b or c` instead.

### Filesystem Paths

- **Use `pathlib.Path` for all filesystem paths.** Any function parameter, return type, or variable that holds a location of a file or directory on disk must be typed `Path`, not `str`. Convert to/from `str` only at genuine boundaries.
- **Boundaries where `str` is correct** (convert at the edge, then work with `Path` internally):
  - CLI argument parsing (typer/click options and arguments arrive as `str`).
  - Config / TOML (de)serialization — Pydantic config fields and `.toml` values are `str`.
  - Env-var parsing, e.g. splitting `PIPELEXPATH` on `os.pathsep`.
  - URIs / URLs — these are not filesystem paths.
  - `importlib.resources` package-resource traversables.
  - Third-party calls whose signature requires `str`.
- **Prefer `Path` idioms over `os.path`:** `base / "sub" / "file.txt"` (not `os.path.join`), `.parent` (not `os.path.dirname`), `.name` (not `os.path.basename`), `.suffix`, `.stem`, `.exists()`, `.is_dir()`, `.is_file()`, `.mkdir(parents=True, exist_ok=True)` (not `os.makedirs`), `.iterdir()` / `.rglob(...)` (not `os.listdir` / `os.walk`), `.read_text()` / `.read_bytes()` / `.write_text()` / `.write_bytes()` (not `open()`), `.unlink()`.
- **Watch the semantic shifts when porting `os.path` code — these are NOT drop-in equivalents:**
  - `os.path.relpath(p, base)` returns a relative path that may walk up with `..`; `Path.relative_to(base)` raises `ValueError` when `p` is not under `base`. Never swap one for the other blindly.
  - `os.path.abspath(p)` collapses `.`/`..` lexically but does **not** resolve symlinks. No single `Path` method matches it: `Path.resolve()` both normalizes `..` *and* follows symlinks, while `Path.absolute()` only prepends the cwd and normalizes neither (`Path("a/../b").absolute()` stays `<cwd>/a/../b`, whereas `os.path.abspath("a/../b")` is `<cwd>/b`). Reach for `Path.resolve()` in the common case; if you genuinely need abspath's no-symlink semantics, normalize explicitly (`Path(os.path.normpath(p.absolute()))`).
- **Logical (non-filesystem) "paths" stay `str`.** Dotted module/import paths, domain paths, and variable/key paths (`variable_path`, `dotted_path`, `var_path`, `key_path`, and similar) are identifiers, not locations on disk — keep them `str`. This rule is about files and directories, not everything named `*_path`.

### Imports

#### Imports at the top of the file

- Avoid as much as possible import statements outside of a module's top-level scope.
- Do not import libraries in functions or classes unless in very specific cases, to be discussed with the user, as they would required a `# noqa: ...` comment to pass linting
- Do not bother with ordering the imports or removing unused imports, our Ruff linter will handle it for us.
- `if TYPE_CHECKING:` blocks must always be the **last** block in the imports section, placed after all regular imports.

#### Removing unused imports

- To remove unused imports, run `make fix-unused-imports` or `make fui` (shorthand). This is faster and cheaper than rewriting with LLM.

#### No re-exports in `__init__.py`

- Do NOT fill `__init__.py` files with re-exports.
- Always use direct full-path imports everywhere.

#### Logging and Pretty Printing

- Both `log()` and `pretty_print()` can be imported from `pipelex` directly:
  ```python
  from pipelex import log, pretty_print

  log.info("Hello, world!")
  ```
- Both have a title arg which is handy when logging/printing objects:
  ```python
  log.verbose("Hello, world!", title="Your first Pipelex log")
  pretty_print(output_object, title="Your first Pipelex output")
  ```
- Both handle formatting json using Rich, pretty_print makes it prettier.

#### StrEnum and Self type

- Both `StrEnum` and `Self` must be imported from `pipelex.types` (the project's single canonical import site):
  ```python
  from pipelex.types import Self, StrEnum
  ```

### Typing

#### Always Use Type Hints

- Every function parameter must be typed
- Every function return must be typed
- Use type hints for all variables where type is not obvious
- Use dict, list, tuple types with lowercase first letter: dict[], list[], tuple[]
- Use type hints for all fields
- Use Field(default_factory=...) for mutable defaults
- Use `# pyright: ignore[specificError]` or `# type: ignore` only as a last resort. In particular, if you are sure about the type, you often solve issues by using cast() or creating a new typed variable.

#### Data-holder shapes (NamedTuple, dataclass, BaseModel)

The deciding question is **does this value ever get serialized** — sent across a process or network boundary, persisted to disk or a database, or round-tripped through (de)serialization? If yes, it must be one of the two serialization-safe forms (a `BaseModel` or a pydantic dataclass): a `NamedTuple` or stdlib `@dataclass` loses its type on the way through and silently corrupts the data across the boundary. (A distributed executor like Temporal is the canonical case — its payloads cross the wire between worker processes — but the same applies to any cache, queue, API response, or on-disk record.) Stdlib `@dataclass` is banned outright; pick one of these four forms:

- **`NamedTuple`** (`from typing import NamedTuple`) — small fixed records replacing bare tuples, or any holder of a `@runtime_checkable` Protocol / arbitrary non-pydantic field (avoids `arbitrary_types_allowed`). Not serialization-safe, zero validation. Avoid when the value is returned in a union beside a real `tuple` — it would also satisfy `isinstance(x, tuple)` and blur the two arms; use a frozen `BaseModel` there instead.
- **pydantic dataclass** (`from pydantic.dataclasses import dataclass`) — internal records that are built and field-read but never serialized; the lowest-churn swap from a stdlib `@dataclass` (just change the decorator). Default to `frozen=True`; drop it only when the instance is genuinely mutated in place after construction.
- **frozen `BaseModel`** (`model_config = ConfigDict(frozen=True)`) — immutable value objects that need the full model API (`model_dump`, validators, discriminated unions), must sit in a uniformly-`BaseModel` layer, or must stay type-distinct from a `tuple` in a union.
- **mutable `BaseModel`** — objects genuinely mutated in place that also want the model API or layer consistency.

Never reach for `TypeAdapter` — needing it means the shape was chosen wrong. And don't convert an existing serialized `BaseModel` to a dataclass just because dataclasses are serialization-safe too: a model that relies on discriminated unions or validators must stay a `BaseModel`. When a serialized dataclass/model field references a type from an optional dependency, alias it to `Any` at runtime so it validates as `Any` without importing the extra (e.g. `if TYPE_CHECKING: from temporalio.common import RetryPolicy` / `else: RetryPolicy = Any`) — a bare forward ref instead raises `PydanticUserError` on construction.

Once you've landed on a `BaseModel` (the default for anything that serializes), respect Pydantic v2 standards:

- Use the modern `ConfigDict` when needed, e.g. `model_config = ConfigDict(extra="forbid", strict=True)`
- Keep models focused and single-purpose
- For list fields with non-string items, use `empty_list_factory_of()` to avoid linter complaints:
  ```python
  from pydantic import BaseModel, Field
  from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

  class MyModel(BaseModel):
      names: list[str] = Field(default_factory=list)  # OK for strings
      numbers: list[int] = Field(default_factory=empty_list_factory_of(int), description="A list of numbers")
      items: list[MyItem] = Field(default_factory=empty_list_factory_of(MyItem), description="A list of items")
  ```

### Keyword-only arguments

Across `pipelex/` source, non-subject function parameters must be **keyword-only**, so call sites are self-documenting: `do_thing(retries=3, timeout=30)` over the opaque `do_thing(3, 30)`. The compliant shape places a bare `*` after the subject:

- `def f(subject, *, opt1, opt2): ...` — the first non-`self`/`cls` parameter (the subject) may stay positional; everything after it must be keyword-only. Making the subject keyword-only too (`def f(*, a, b)`, `def m(self, *, a, b)`) is always allowed and is the form the auto-fixer produces.
- A lone subject (`def render(node)`) is compliant; a second bare positional (`def f(a, b)`, `def truncate(text, max_length=80)`) is a violation.

The rule is mechanically enforced by the `check-keyword-only` AST guard (`make cko`), which runs in `make agent-check`, in the `make check` aggregate, in CI, and via a Claude Code `PostToolUse` hook that checks each edited file at edit time. The tree is fully compliant, so it hard-blocks on **any** violation. Carve-outs — dunders, pydantic validators/serializers, Typer/pytest/Jinja2 framework entrypoints, `@override` impls, and a small curated symmetric-tuple allowlist — are skipped automatically. A genuinely justified one-off uses an inline `# kw-only: ignore` comment on the `def` line (place it right after the open paren so `ruff format` keeps it on the header line).

**Auto-fix.** `make fix-keyword-only` (alias `fko`, or `pipelex-dev check-keyword-only --fix`) rewrites every mechanically-fixable violation by inserting a bare `*` as far left as possible — right after `self`/`cls` — so every non-`self`/`cls` parameter becomes keyword-only, and re-parses each rewrite before writing (a rewrite that would not parse is discarded and reported instead). It runs automatically early in `make agent-check`, before `ruff format`. It is **non-gating**: it mutates and reports but never exits non-zero — the read-only `check-keyword-only` (run last in `agent-check`, and the variant `make check` / CI use) owns the pass/fail gate. A few shapes a single `*` insert cannot fix are reported for a manual fix instead of rewritten: a `*args` is present, a keyword-only section already exists, or two-or-more positional-only params remain.

Auto-fix is not a substitute for review: the guard is blind to functions a framework or the interpreter invokes positionally (callbacks, `__import__` hooks, route handlers, Jinja2 filters) — pyright/mypy will pass a wrongly-keywordized callback, so `make agent-test` is the safety net after a bulk fix.

### Factory Pattern

- Use factory pattern for object creation when dealing with multiple implementations
- Our factory methods are named `make_from_...` and such

### Protocols and Interfaces

- When a getter (e.g. `get_report_delegate()`, `get_library_manager()`) returns a `Protocol` type, callers must only rely on methods declared on that `Protocol`. If you need to call a method that lives on a concrete implementation, **extend the `Protocol`** — do not work around it with `isinstance(...)` checks, `cast(...)`, or inline imports of the concrete class.
- When extending the `Protocol`, also update every implementation (including no-op / null implementations) so structural typing is satisfied. For implementations where the method has nothing to do, give it a `pass` body — that is the whole point of having a `Protocol` rather than a concrete base class.
- Smell to watch for: an inline `from ... import ConcreteImpl  # noqa: PLC0415` followed by `if isinstance(delegate, ConcreteImpl): delegate.some_method(...)`. This is almost always a missing method on the `Protocol`. Promote it.
- Use `@override` (from `typing_extensions`) on every implementation of a `Protocol` method, so that signature drift between the `Protocol` and its implementations is caught by the type checker.

### Error Handling

- Always catch exceptions at the place where you can add useful context to it.
- Use try/except blocks with specific exceptions
- Convert third-party exceptions to our custom ones except in pydantic validators where you can raise a ValueError or a TypeError
- **NEVER write `except Exception:` (or bare `except:`).** Catching the generic `Exception` is FORBIDDEN except in two cases, each of which REQUIRES a one-line comment directly under the `except` naming which case applies: **(1)** the absolute root of a CLI command or an API endpoint handler; **(2)** the wrapped call invokes genuinely unbounded code whose exception surface cannot be enumerated — a user-registered callback or function, dynamic plugin dispatch, or a third-party SDK with no documented exception types (this is only for genuinely open-ended surfaces; "I didn't look the exceptions up" does NOT qualify). There are NO other exceptions to this rule. The following are NOT valid justifications and the agent must reject them when tempted:
    - "I want to log and re-raise" → just let it propagate; logging happens at the root.
    - "I want to swallow it just in case" → don't. Unknown failures must surface.
    - "I want to convert it to our error type" → only if you know which specific exception(s) the call can raise; catch those explicitly. Catching a project base class (`PipelexError`) or a package base (`CogtError`, `ToolError`) is acceptable when the operation legitimately fails in many domain-specific ways — that is still specific. Catching `Exception` is not.
    - "The third-party lib isn't well typed" → look up the actual exceptions it raises and catch those by name.
    - "It's safer this way" → it isn't. It hides bugs. Crashing loudly on an unexpected exception is the desired behavior.
    If you find yourself writing `except Exception` outside the two cases above, STOP and ask the user before proceeding.
- **Do NOT add try/except speculatively.** Only add a `try`/`except` when (a) a specific exception type is documented or known to be raised by the call, AND (b) you have a concrete recovery path or a meaningful context to attach. Otherwise, let the error bubble up — that is the correct behavior, not a gap to fill.
- **Use `try`/`finally` (without `except`) for required cleanup.** When a piece of code MUST run on the way out — releasing a resource, closing a tracer, tearing down a library, clearing per-context state on a manager — put it in a `finally` block (or a `with`/context manager). This is the correct way to guarantee cleanup on both the happy path and the error path: it does NOT suppress the exception, it just ensures cleanup happens before the exception propagates. Do not invent an `except Exception` just to attach cleanup; use `finally` instead. Conversely, do not move cleanup into the success path "to keep things simple" — if it must run on errors too, it belongs in `finally`.
- When reviewing existing code, treat any `except Exception` you encounter as a bug to fix (replace it with the specific exception(s) actually raised, or remove the try/except entirely), not as a precedent to follow.
- **`from exc` on raise statements — default yes.** `raise NewError(msg) from exc` whenever you raise a new exception while handling another. The point is preserving the cause for debugging tracebacks.

  Carve-out — translation helpers. When the actual `raise` lives one frame down inside a translation helper (`raise_validation_error(message=str(exc))`, an API 4xx shaper, anything `(msg: str) -> NoReturn` whose job is shaping the outgoing response), Python's implicit `__context__` chaining already preserves the original — the helper's `raise` runs while your `except` frame is still active, structured logs walk the chain either way, and only the traceback intro line differs ("During handling of the above exception" vs "The above exception was the direct cause"). Don't bolt a `cause=exc` parameter onto every such helper just to swap implicit `__context__` for explicit `__cause__`. Revisit only if a helper grows an internal try/except that would break the implicit chain, or if a downstream tool (Sentry-style) is wired to distinguish the two.

- Always write the error message as a variable before raising it, for cleaner error traces

  ```python
  try:
      self.models_manager.setup()
  except RoutingProfileLibraryNotFoundError as exc:
      msg = "The routing library could not be found, please call `pipelex init config` to create it"
      raise PipelexSetupError(msg) from exc
  ```

### Error class location

Put every custom error class in a module named `exceptions.py` (default — one per package directory) or `<topic>_exceptions.py` (when a directory needs several separate-concern error modules); the base error class gets its own module. This is a discoverability contract, not style: tooling that enumerates errors (doc generation, URI/uniqueness checks) finds them by importing these well-known module names, so an error defined in a sibling non-error module (worker, factory, parser) may never be imported and silently escapes that tooling.

- **Default:** append to the package's existing `exceptions.py`.
- **Topical split:** when appending would cause a circular import, or a package hosts genuinely separate error families, use `<topic>_exceptions.py` importing only the base error class.
- **Forbidden:** `*_errors.py` (synonym, drift magnet), or defining an error alongside non-error code.

Use one casing per acronym (`LLMError` vs `LlmError` collide when kebab-cased into filenames/URIs). Enforce the convention with a test in CI.

### Documentation

1. **Docstring Format**
   ```python
   def process_image(image_path: str, size: tuple[int, int]) -> bytes:
       """Process and resize an image.

       Args:
           image_path: Path to the source image
           size: Tuple of (width, height) for resizing

       Returns:
           Processed image as bytes
       """
       pass
   ```

2. **Class Documentation**
   ```python
   class ImageProcessor:
       """Handles image processing operations.

       Provides methods for resizing, converting, and optimizing images.
       """
   ```

## Standards related to developing the Pipelex codebase

### Spec vs Blueprint Architecture

- **Blueprints** (`pipelex/pipe_operators/`, `pipelex/pipe_controllers/`, `pipelex/core/`) are the MTHDS language reference — what `.mthds` files parse into.
- **Specs** (`pipelex/builder/pipe/`) are a convenience authoring format for AI agents. Each spec has `to_blueprint()` that transforms it into the corresponding blueprint. Spec-level fields may differ from blueprint-level fields.

When adding validation or fields, decide which layer they belong to. Language rules go on blueprints; authoring convenience goes on specs. See `pipelex/builder/CLAUDE.md` for details.

### Main config

- The main config model is defined using `ConfigModel` classes, derived from `pydantic BaseModel`
- The model is defined in `pipelex/system/configuration/configs.py`, some of the submodels being defined in their respective sub-packages
- When adding new configs, place them where it makes most sense, ask the user if you need arbitrage
- As per our python standards, use StrEnum for multiple-value enums. In that case they must not be strict pydantic fields, i.e. add `= Field(strict=False)`
- **Important**: NEVER EVER set default values for config attributes in the class definition. All the default values are defined in the main config file `pipelex/pipelex.toml`. The only exception si for Optional values which must be set to `None` in the class definition.
- If (and only if) you add some config that will clearly make sense for client projects to override, for instance if it's a case of user preference, then you can also add a copy of the settings to the project override config file `.pipelex/pipelex.toml`. NEVER add them commented out: commented-out TOML is never parsed or validated, so it rots silently when keys are refactored. Instead, write the actual default values (matching `pipelex/pipelex.toml`, even empty ones like `activity_queues = {}`) so the override file stays valid and behaves like setting nothing. Plain prose comments explaining the setting are fine — it's commented-out keys/values that are forbidden.
- The different `pipelex.toml` files and the python model `configs.py` must be up to date with each other in terms of structure and attributes, otherwise the loading of teh config fails. To check quickly that you're good, just run `make tb` which tests the boot sequence, which includes the config loading.

### Keyword-only arguments

Non-subject function parameters across `pipelex/` source must be **keyword-only**, so call sites are self-documenting: `do_thing(retries=3, timeout=30)` over the opaque `do_thing(3, 30)`. The compliant shape places a bare `*` after the subject:

- `def f(subject, *, opt1, opt2): ...` — the first non-`self`/`cls` parameter (the subject) may stay positional; everything after it must be keyword-only. Making the subject keyword-only too (`def f(*, a, b)`) is always allowed and often preferable.
- A lone subject (`def render(node)`) is compliant; a second bare positional (`def f(a, b)`, `def truncate(text, max_length=80)`) is a violation.

The rule is mechanically enforced by the `check-keyword-only` AST guard, which runs in `make agent-check`, in the `make check` aggregate, and in CI; the tree is fully compliant, so it hard-blocks on **any** violation. Carve-outs (dunders, pydantic validators/serializers, Typer/pytest/Jinja2 framework entrypoints, `@override` impls) are skipped automatically. A genuinely justified one-off uses an inline `# kw-only: ignore` comment on the `def` line (place it right after the open paren so `ruff format` keeps it on the header line). Watch for functions a framework or the interpreter invokes positionally (callbacks, `__import__` hooks, route handlers): the type checker is blind to those, so `make agent-test` is the safety net.

The full specification — the two exceptions, the carve-out list, the symmetric-tuple allowlist, the escape hatch, and worked examples — is in [`docs/contribute/keyword-only-arguments.md`](docs/contribute/keyword-only-arguments.md).

## Writing Tests

### Unit test generalities

NEVER USE unittest.mock. Instead YOU MUST USE pytest-mock: `from pytest_mock import MockerFixture`.
NEVER EVER put more than one TestClass into a test module.

#### Test file structure

- Name test files with `test_` prefix
- Place test files in the appropriate test category directory:
    - `tests/unit/` - for unit tests that test individual functions/classes in isolation
    - `tests/integration/` - for integration tests that test component interactions
    - `tests/e2e/` - for end-to-end tests that test complete methods
- Do NOT add `__init__.py` files to test directories. Test directories do not need to be Python packages.
- Fixtures are defined in conftest.py modules at different levels of the hierarchy, their scope is handled by pytest
- Test data is placed inside test_data.py at different levels of the hierarchy, they must be imported with package paths from the root like `from tests.integration.pipelex.cogt.test_data`. Their content is all constants, regrouped inside classes to keep things tidy.
- Always put tests inside Test classes: 1 TestClass per module.
- NEVER EVER put more than one TestClass into a test module.
- Put fixtures into conftest.py files for easy sharing.

#### Markers

Apply the appropriate markers:
- "gha_disabled: will not be able to run properly on GitHub Actions"
- "llm: uses an LLM to generate text or objects"
- "img_gen: uses an image generation AI"
- "extract: uses text/image extraction from documents"
- "inference: uses either an LLM or an image generation AI"
- never add "@pytest.mark.dry_runnable" if you haven't set the "inference" marker

Several markers may be applied. For instance, if the test uses an LLM, then it uses inference, so you must mark with both `inference` and `llm`.

#### Important rules

- Never use the unittest.mock. Use pytest-mock.

#### Test Class Structure

- Always group the tests of a module into a test class:

```python
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestFooBar:
    @pytest.mark.parametrize(
        "topic, test_case_blueprint",
        [
            TestCases.CASE_1,
            TestCases.CASE_2,
        ],
    )
    async def test_pipe_processing(
        self,
        request: FixtureRequest,
        topic: str,
        test_case_blueprint: StuffBlueprint,
    ):
        # Test implementation
```

- Never more than 1 class per test module.
- When testing one method, if possible, limit the number of test functions, but with different test cases in parameters

#### Test Data Organization

- If it's not already there, create a `test_data.py` file in the proper test directory
- Note how we avoid initializing a default mutable value within a class instance, instead we use ClassVar.
- Also note that we provide a topic for the test case, which is purely for convenience.

### Best Practices for Testing

- Use strong asserts: test value, not just type and presence.
- Use parametrize for multiple test cases
- Test both success and failure cases
- Verify working memory state
- Check output structure and content
- Use meaningful test case names
- Include concise docstrings explaining test purpose but not on top of the file and not on top of the class.
- Log outputs for debugging

## Writing Docs

We use Material for MkDocs. All markdown in our docs must be compatible with Material for MkDocs and done using best practices to get the best results with Material for MkDocs.

### MkDocs Markdown Requirements

- Always add a blank line before any bullet lists or numbered lists in MkDocs markdown.
