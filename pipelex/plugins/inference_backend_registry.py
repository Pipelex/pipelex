import importlib.util
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, TypeAlias

from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.plugins.exceptions import InferenceBackendNotFoundError
from pipelex.system.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from pipelex.cogt.llm.llm_job_components import LLMJobParams
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class InferenceFamily(StrEnum):
    LLM = "llm"
    IMG_GEN = "img_gen"
    EXTRACT = "extract"
    SEARCH = "search"
    DOC_GEN = "doc_gen"
    JUDGMENT = "judgment"


# The uniform inference-backend factory. A backend plugin registers one of these
# per (family, sdk) it serves. It is import-light to *reference* (a plain
# callable) and only imports its SDK lazily when *called*.
#
# Called by the family worker factory as:
#     make_worker(*, inference_model, backend, sdk_clients, reporting_delegate)
# where ``sdk_clients`` is the process-wide ``SdkClientRegistry`` (for client
# caching) and ``reporting_delegate`` is the per-call reporting delegate.
MakeWorkerFn: TypeAlias = Callable[..., InferenceWorkerAbstract]


class CheckLLMRequestFn(Protocol):
    """The checks the LLM worker a backend builds applies to a request before calling its provider.

    A backend plugin registers one beside the ``make_worker`` of an LLM sdk, and bundle validation calls it
    with the spec of the model a pipe's setting resolves to, so a setting the worker would refuse is refused
    when the method loads, before a run spends anything. Like ``make_worker`` it is import-light to
    reference and imports its worker only when called; it builds no SDK client. It delegates to the
    worker class's own ``check_request``, the check the worker runs before every call, so the two never
    disagree. An LLM sdk that registers none is checked against ``LLMWorkerAbstract.check_request``, the
    rule every worker shares.

    A refusal is an ``LLMCapabilityError``, and a validation verdict shows it to whoever wrote the setting.
    A built-in backend's refusal is shown with the model named by its deck handle, since this library writes
    those messages. An external plugin's refusal is shown as written only when the plugin raises it as
    caller-facing copy (``as_caller_fault()``), vouching that it names nothing the plugin keeps private;
    any other is named by its title alone.
    """

    def __call__(self, *, inference_model: "InferenceModelSpec", job_params: "LLMJobParams", is_structured: bool) -> None: ...


@dataclass(frozen=True)
class LLMRequestCheck:
    """A registered request check, and whether a built-in plugin registered it, which decides how its refusals are shown."""

    check: CheckLLMRequestFn
    is_builtin: bool


def require_sdk(*, spec: str | Sequence[str], extra: str, msg: str, dependency_name: str | None = None) -> None:
    """Raise ``MissingDependencyError`` if any of ``spec`` is not importable.

    The DRY replacement for the repeated ``find_spec(...) is None`` guard that
    used to sit in every dispatch arm. Called *inside* ``make_worker`` so a
    missing optional extra fails when the backend is actually used, not at boot.

    - ``spec``: the import name(s) to probe (e.g. ``"anthropic"`` or
      ``["boto3", "aiobotocore"]`` when several are required together).
    - ``dependency_name``: the human-facing package name shown in the error;
      defaults to the joined names of the *missing* specs only (override when the
      import name differs from the distribution name, e.g. spec
      ``"google.genai"`` / dependency ``"google-genai"``).
    - ``extra``: the pip extra to install (drives the ``pipelex[<extra>]`` hint).
    """
    specs = [spec] if isinstance(spec, str) else list(spec)
    missing: list[str] = []
    for one_spec in specs:
        try:
            if importlib.util.find_spec(one_spec) is None:
                missing.append(one_spec)
        except ModuleNotFoundError:
            # ``find_spec`` imports the parent of a dotted spec (e.g. ``google`` for
            # ``google.genai``); an entirely absent parent raises ModuleNotFoundError
            # rather than returning None, so treat that as "missing" too.
            missing.append(one_spec)
    if missing:
        # Name only the specs that are actually absent, so a user who already has
        # one of several required SDKs is not told to (re)install it.
        raise MissingDependencyError(dependency_name or ",".join(missing), extra, msg)


class InferenceBackendRegistry:
    """Read view over the inference backends contributed by discovered plugins.

    Keyed by ``(family, sdk)``. Built once at boot from the registrar's
    accumulated backends and stored on the hub; the family worker factories look
    up their ``make_worker`` here instead of branching on a ``match`` over SDK
    strings.
    """

    def __init__(
        self,
        backends: dict[tuple[InferenceFamily, str], MakeWorkerFn],
        llm_request_checks: dict[str, LLMRequestCheck] | None = None,
    ):
        self._backends: dict[tuple[InferenceFamily, str], MakeWorkerFn] = dict(backends)
        self._llm_request_checks: dict[str, LLMRequestCheck] = dict(llm_request_checks or {})

    def lookup(self, *, family: InferenceFamily, sdk: str) -> MakeWorkerFn:
        make_worker = self._backends.get((family, sdk))
        if make_worker is None:
            raise InferenceBackendNotFoundError(family=family, sdk=sdk)
        return make_worker

    def lookup_llm_request_check(self, *, sdk: str) -> LLMRequestCheck | None:
        """The request check the LLM backend serving `sdk` registered, `None` when it registered none."""
        return self._llm_request_checks.get(sdk)

    def has(self, *, family: InferenceFamily, sdk: str) -> bool:
        return (family, sdk) in self._backends

    def with_family(self, *, family: InferenceFamily, backends: dict[str, MakeWorkerFn]) -> "InferenceBackendRegistry":
        """A copy whose backends of one family are exactly `backends`, keyed by sdk, the other families' kept as they are.

        What a test uses to stand stub workers in for a family, or to remove it, without rebooting the runtime.
        """
        kept = {key: make_worker for key, make_worker in self._backends.items() if key[0] != family}
        kept.update({(family, sdk): make_worker for sdk, make_worker in backends.items()})
        return InferenceBackendRegistry(kept, llm_request_checks=self._llm_request_checks)

    @property
    def keys(self) -> list[tuple[InferenceFamily, str]]:
        return list(self._backends)
