"""No production module passes a transport to the fetch helpers, since a transport replaces the guard."""

import ast
from pathlib import Path

FETCH_FUNCTION_NAMES = frozenset({"fetch_file_from_url_httpx", "fetch_file_and_content_type_from_url_httpx"})
PIPELEX_SOURCE_ROOT = Path(__file__).resolve().parents[6] / "pipelex"
FETCH_HELPER_SOURCE = PIPELEX_SOURCE_ROOT / "tools" / "misc" / "file_fetch_utils.py"


def _fetch_calls_passing_transport(source_path: Path) -> tuple[int, list[str]]:
    """Count the calls to the fetch helpers in ``source_path``, and list those passing ``transport``."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    nb_fetch_calls = 0
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if func_name not in FETCH_FUNCTION_NAMES:
            continue
        nb_fetch_calls += 1
        if any(keyword.arg in {"transport", None} for keyword in node.keywords):
            offenders.append(f"{source_path.relative_to(PIPELEX_SOURCE_ROOT.parent)}:{node.lineno}")
    return nb_fetch_calls, offenders


class TestTransportIsATestSeamOnly:
    def test_no_production_module_passes_a_transport_to_the_fetch_helpers(self) -> None:
        """Passing a transport replaces the guard, so only tests may do it.

        The helper's own forwarding from one fetch function to the other is the one exception.
        Calls with ``**kwargs`` count as passing one, since they could.
        """
        nb_fetch_calls = 0
        offenders: list[str] = []
        for source_path in sorted(PIPELEX_SOURCE_ROOT.rglob("*.py")):
            if source_path == FETCH_HELPER_SOURCE:
                continue
            nb_calls_in_file, offenders_in_file = _fetch_calls_passing_transport(source_path)
            nb_fetch_calls += nb_calls_in_file
            offenders.extend(offenders_in_file)

        assert nb_fetch_calls > 0, "found no call to the fetch helpers at all: the scan is looking in the wrong place"
        assert offenders == []
