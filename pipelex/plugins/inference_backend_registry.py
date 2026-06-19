import importlib.util
from collections.abc import Callable, Sequence
from typing import TypeAlias

from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.system.exceptions import MissingDependencyError
from pipelex.types import StrEnum


class InferenceFamily(StrEnum):
    LLM = "llm"
    IMG_GEN = "img_gen"
    EXTRACT = "extract"
    SEARCH = "search"


# The uniform inference-backend factory. A backend plugin registers one of these
# per (family, sdk) it serves. It is import-light to *reference* (a plain
# callable) and only imports its SDK lazily when *called*.
#
# Called by the family worker factory as:
#     make_worker(*, inference_model, backend, sdk_clients, reporting_delegate)
# where ``sdk_clients`` is the process-wide ``SdkClientRegistry`` (for client
# caching) and ``reporting_delegate`` is the per-call reporting delegate.
MakeWorkerFn: TypeAlias = Callable[..., InferenceWorkerAbstract]


def require_sdk(*, spec: str | Sequence[str], extra: str, msg: str, dependency_name: str | None = None) -> None:
    """Raise ``MissingDependencyError`` if any of ``spec`` is not importable.

    The DRY replacement for the repeated ``find_spec(...) is None`` guard that
    used to sit in every dispatch arm. Called *inside* ``make_worker`` so a
    missing optional extra fails when the backend is actually used, not at boot.

    - ``spec``: the import name(s) to probe (e.g. ``"anthropic"`` or
      ``["boto3", "aioboto3"]`` when several are required together).
    - ``dependency_name``: the human-facing package name shown in the error;
      defaults to the joined ``spec`` (override when the import name differs from
      the distribution name, e.g. spec ``"google.genai"`` / dependency
      ``"google-genai"``).
    - ``extra``: the pip extra to install (drives the ``pipelex[<extra>]`` hint).
    """
    specs = [spec] if isinstance(spec, str) else list(spec)
    try:
        # ``find_spec`` imports the parent of a dotted spec (e.g. ``google`` for
        # ``google.genai``); an entirely absent parent raises ModuleNotFoundError
        # rather than returning None, so treat that as "missing" too.
        is_missing = any(importlib.util.find_spec(one_spec) is None for one_spec in specs)
    except ModuleNotFoundError:
        is_missing = True
    if is_missing:
        raise MissingDependencyError(dependency_name or ",".join(specs), extra, msg)


class InferenceBackendRegistry:
    """Read view over the inference backends contributed by discovered plugins.

    Keyed by ``(family, sdk)``. Built once at boot from the registrar's
    accumulated backends and stored on the hub; the family worker factories look
    up their ``make_worker`` here instead of branching on a ``match`` over SDK
    strings.
    """

    def __init__(self, backends: dict[tuple[InferenceFamily, str], MakeWorkerFn]):
        self._backends: dict[tuple[InferenceFamily, str], MakeWorkerFn] = dict(backends)

    def lookup(self, *, family: InferenceFamily, sdk: str) -> MakeWorkerFn:
        make_worker = self._backends.get((family, sdk))
        if make_worker is None:
            msg = f"No inference backend registered for sdk '{sdk}' in the {family} family. Is its plugin installed?"
            raise NotImplementedError(msg)
        return make_worker

    def has(self, *, family: InferenceFamily, sdk: str) -> bool:
        return (family, sdk) in self._backends

    @property
    def keys(self) -> list[tuple[InferenceFamily, str]]:
        return list(self._backends)
