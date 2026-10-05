"""Nothing but `get_pipelex_home_dir` locates the home configuration directory, so `PIPELEX_HOME` moves it everywhere."""

import ast
import textwrap
from pathlib import Path

#: The one function allowed to join the user's home directory with `.pipelex`.
RESOLVER_SITE = ("pipelex/system/environment.py", "get_pipelex_home_dir")

REPO_ROOT = Path(__file__).resolve().parents[5]

#: The source trees the guard sweeps: the library and the API server member.
SWEPT_SOURCE_ROOTS = ("pipelex", "api/pipelex_api")


def _joins_the_home_directory_with_dot_pipelex(node: ast.AST) -> bool:
    """Whether `node` is `Path.home() / ".pipelex"` (or `/ CONFIG_DIR_NAME`), `Path.home().joinpath(".pipelex")`, or a `~/.pipelex` literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("\\", "/").startswith("~/.pipelex")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _is_home_call(node.left) and _names_dot_pipelex(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
        return _is_home_call(node.func.value) and bool(node.args) and _names_dot_pipelex(node.args[0])
    return False


def _is_home_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "home"


def _names_dot_pipelex(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("\\", "/").split("/")[0] == ".pipelex"
    return isinstance(node, ast.Name) and node.id == "CONFIG_DIR_NAME"


def _offending_joins(*, source: str, relative_path: str) -> list[str]:
    """The joins in one module outside the resolver, docstrings excluded (they describe the default, they do not compute it)."""
    tree = ast.parse(source)
    docstrings = {
        id(body[0].value)
        for owner in ast.walk(tree)
        if isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and (body := owner.body)
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    }
    allowed: set[int] = set()
    if relative_path == RESOLVER_SITE[0]:
        for owner in ast.walk(tree):
            if isinstance(owner, ast.FunctionDef) and owner.name == RESOLVER_SITE[1]:
                allowed.update(id(inner) for inner in ast.walk(owner))
    return [
        f"{relative_path}:{getattr(node, 'lineno', '?')}"
        for node in ast.walk(tree)
        if id(node) not in docstrings and id(node) not in allowed and _joins_the_home_directory_with_dot_pipelex(node)
    ]


class TestOneResolver:
    def test_the_detector_sees_every_spelling(self) -> None:
        """The control: without it, a detector that matched nothing would leave the sweep below green forever."""
        source = textwrap.dedent(
            """
            from pathlib import Path
            a = Path.home() / ".pipelex"
            b = Path.home() / CONFIG_DIR_NAME
            c = Path.home() / ".pipelex" / ".env"
            d = Path.home().joinpath(".pipelex")
            e = Path("~/.pipelex").expanduser()
            """
        )
        assert len(_offending_joins(source=source, relative_path="pipelex/somewhere.py")) == 5

    def test_nothing_but_the_resolver_joins_the_home_directory_with_dot_pipelex(self) -> None:
        offenders: list[str] = []
        for source_root in SWEPT_SOURCE_ROOTS:
            for module_path in sorted((REPO_ROOT / source_root).rglob("*.py")):
                relative_path = module_path.relative_to(REPO_ROOT).as_posix()
                offenders.extend(_offending_joins(source=module_path.read_text(encoding="utf-8"), relative_path=relative_path))
        assert not offenders, (
            f"only `{RESOLVER_SITE[0]}::{RESOLVER_SITE[1]}` may locate the home configuration directory, so that "
            f"`PIPELEX_HOME` moves it everywhere. Ask `get_pipelex_home_dir()` or `config_manager.global_config_dir` instead: "
            f"{offenders}"
        )
