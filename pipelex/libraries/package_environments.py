"""The Python environment a method's PipeFunc steps run in, as the check of its `requirements.txt` reads it.

Where a PipeFunc runs decides what its requirements are checked against:

- In the `direct` execution mode it runs in this interpreter, so the check reads the distributions installed here and
  this interpreter's own marker environment, and can follow a requirement's extras through their metadata.
- In any other mode it runs in a sandbox this process never sees, such as the Daytona sandbox, whose packages are the
  whole offer. The plugin providing the mode states them (`pipelex/plugins/pipe_func_package_offer_registry.py`), and
  the check reads that statement alone: a marker variable it does not state cannot be judged, and an extra's needs,
  which it does not state, cannot be followed. A mode with no statement fails closed.

How an environment names itself in a refusal depends on who reads it: this interpreter is named by its path on the
host, and its advice gives the exact install command, only where the refusal may name paths on the host.
"""

import shlex
import sys
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, distribution
from typing import Protocol

from packaging.markers import default_environment
from packaging.utils import canonicalize_name
from typing_extensions import override

from pipelex.config import get_config, get_pipe_func_execution_mode, is_pipe_func_sandbox_hosted
from pipelex.interpreter_hub import get_pipe_func_package_offer_registry
from pipelex.libraries.exceptions import PipeFuncPackageSetUnstatedError
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOffer


class PythonPackageEnvironment(Protocol):
    """The Python packages and the marker environment a method's requirements are judged against."""

    @property
    def description(self) -> str:
        """The environment as a refusal names it, a noun phrase such as "this Python interpreter (/usr/bin/python3)"."""
        ...

    @property
    def marker_environment(self) -> Mapping[str, str]:
        """The PEP 508 marker values the environment states; a variable missing here cannot be judged."""
        ...

    def version_of(self, *, distribution_name: str) -> str | None:
        """The version of the distribution the environment holds under this name, or None when it holds none."""
        ...

    def dependencies_of(self, *, distribution_name: str) -> list[str] | None:
        """The requirements the distribution's metadata declares (its Requires-Dist), or None when the environment does not state them."""
        ...

    def advice(self, *, requirement_texts: list[str]) -> str:
        """What the method's author can do about the requirements given, as written in the file, that the environment does not meet."""
        ...


class InterpreterPackageEnvironment(PythonPackageEnvironment):
    """This interpreter, where a PipeFunc runs in the `direct` execution mode: its installed distributions, read as needed.

    Its path on the host is named, in its description and in the install command its advice gives, only when
    `names_host_paths` says the refusal may name paths on the host.
    """

    def __init__(self, *, names_host_paths: bool) -> None:
        self._executable = sys.executable
        self._names_host_paths = names_host_paths
        self._marker_environment: dict[str, str] = {variable: str(value) for variable, value in default_environment().items()}

    @property
    @override
    def description(self) -> str:
        if self._names_host_paths:
            return f"this Python interpreter ({self._executable})"
        return "the Python interpreter Pipelex runs in"

    @property
    @override
    def marker_environment(self) -> Mapping[str, str]:
        return self._marker_environment

    @override
    def version_of(self, *, distribution_name: str) -> str | None:
        try:
            return distribution(distribution_name).version
        except PackageNotFoundError:
            return None

    @override
    def dependencies_of(self, *, distribution_name: str) -> list[str] | None:
        try:
            return distribution(distribution_name).requires or []
        except PackageNotFoundError:
            return []

    @override
    def advice(self, *, requirement_texts: list[str]) -> str:
        quoted = " ".join(shlex.quote(requirement_text) for requirement_text in requirement_texts)
        if self._names_host_paths:
            return (
                f"Install them into this interpreter with: uv pip install --python {shlex.quote(self._executable)} {quoted}. "
                "Pipelex never installs a method's requirements itself."
            )
        return (
            f"Install them into the Python interpreter Pipelex runs in, for instance with: uv pip install {quoted}. "
            "Pipelex never installs a method's requirements itself."
        )


class OfferedPackageEnvironment(PythonPackageEnvironment):
    """The package set a plugin states for the sandbox an out-of-process execution mode runs a PipeFunc in."""

    def __init__(self, *, offer: PipeFuncPackageOffer):
        self._offer = offer
        self._versions: dict[str, str] = {canonicalize_name(name): version for name, version in offer.distributions.items()}

    @property
    @override
    def description(self) -> str:
        return self._offer.environment

    @property
    @override
    def marker_environment(self) -> Mapping[str, str]:
        return self._offer.marker_environment

    @override
    def version_of(self, *, distribution_name: str) -> str | None:
        return self._versions.get(canonicalize_name(distribution_name))

    @override
    def dependencies_of(self, *, distribution_name: str) -> list[str] | None:
        return None

    @override
    def advice(self, *, requirement_texts: list[str]) -> str:
        return (
            f"PipeFunc steps on this deployment run with the packages of {self._offer.environment} and no others, "
            "so require versions it holds, or remove the requirements it cannot meet."
        )


def resolve_pipe_func_package_environment(*, names_host_paths: bool) -> PythonPackageEnvironment:
    """The environment this process's PipeFunc steps run in, as its execution mode decides.

    Args:
        names_host_paths: Whether a refusal naming the environment may name paths on this host, such as this
            interpreter's.

    Raises:
        PipeFuncPackageSetUnstatedError: The mode runs PipeFunc steps out of this process and no plugin states, or the
            stating plugin could not state, the packages found there.
    """
    if not is_pipe_func_sandbox_hosted():
        return InterpreterPackageEnvironment(names_host_paths=names_host_paths)
    execution_mode = get_pipe_func_execution_mode()
    offer_factory = get_pipe_func_package_offer_registry().get_optional(mode=execution_mode)
    if offer_factory is None:
        raise PipeFuncPackageSetUnstatedError(execution_mode=execution_mode, offer_registered=False)
    offer = offer_factory(get_config().interpreter.pipe_func)
    if offer is None:
        raise PipeFuncPackageSetUnstatedError(execution_mode=execution_mode, offer_registered=True)
    return OfferedPackageEnvironment(offer=offer)
