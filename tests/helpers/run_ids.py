import re

from pipelex.system.job_metadata import PIPELINE_RUN_ID_MAX_LENGTH

_OUTSIDE_THE_RUN_ID_ALPHABET = re.compile(r"[^A-Za-z0-9_-]+")


def run_id_for_test(*, node_id: str, suffix: str) -> str:
    """A run id naming the test it runs in, held to the one rule of a run id (`validate_pipeline_run_id`).

    A pytest node id holds `/`, `.`, `:`, `[` and spaces, which a run id refuses, so each run of them becomes a `_`, and
    a long node id keeps its end, the test's name and parameters, so the id and its suffix fit within the limit.
    """
    room = PIPELINE_RUN_ID_MAX_LENGTH - len(suffix) - 1
    readable_node_id = _OUTSIDE_THE_RUN_ID_ALPHABET.sub("_", node_id)
    return f"{readable_node_id[-room:]}-{suffix}"
