from abc import ABC, abstractmethod

from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


class PipeLibraryAbstract(ABC):
    """A loaded method's pipe library: pipe resolution plus the management half.

    There is deliberately no read-side `PipeProviderAbstract` in `core/` mirroring
    :class:`~pipelex.core.concepts.concept_provider_abstract.ConceptProviderAbstract`: no core module
    takes pipe resolution as a parameter. The two places that follow a pipe reference found *inside* a
    pipe graph — a condition's mapped pipes and a sequence's last step, both in
    `pipe_machinery/rendering/` — are interpreter-layer and call `interpreter_hub.get_required_pipe`
    directly. Split the read half out if and when a kernel-layer caller needs it.

    One caveat before the split: "strict" describes same-package refs. A cross-package
    `alias->bare_code` ref is still resolved by searching that alias's entries, because the
    qualification pass leaves `alias->…` refs untouched and there is no canonical spelling to point
    an author at yet. It is alias-scoped, so it cannot reach a host pipe.

    Two resolution surfaces live here and the split is the point. `get_optional_pipe` /
    `get_required_pipe` resolve an **in-body** reference — one pipe naming another from inside a
    method — and are strict: the ref names its own domain or it names nothing. `get_optional_entry_pipe`
    / `get_required_entry_pipe` resolve a code a **human** supplied at an entry point, where a bare
    code is still matched across domains because the user is not writing a reference, they are
    pointing at a pipe. Reaching for the in-body pair to serve a hand-typed code makes the CLI stricter
    than it should be; reaching for the entry pair from inside a controller reopens the cross-domain
    hole the strict rule closes.
    """

    @abstractmethod
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        """Resolve an in-body pipe reference, raising when it is not known."""

    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        self.teardown()
        self.setup()

    @abstractmethod
    def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None:
        """Resolve an in-body pipe reference, returning None when it is not known."""

    @abstractmethod
    def get_optional_entry_pipe(self, pipe_code: str) -> PipeAbstract | None:
        """Resolve a human-supplied pipe code, returning None when nothing matches.

        Matches a bare code across domains and raises on ambiguity; ignores `[exports]`.
        """

    @abstractmethod
    def get_required_entry_pipe(self, pipe_code: str) -> PipeAbstract:
        """Resolve a human-supplied pipe code, raising when nothing matches."""

    @abstractmethod
    def get_pipes(self) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def get_pipes_dict(self) -> dict[str, PipeAbstract]:
        pass

    def remove_pipes_by_refs(self, pipe_refs: list[str]) -> None:
        pass

    @abstractmethod
    def pretty_list_pipes(self) -> None:
        pass

    @abstractmethod
    def add_new_pipe(self, pipe: PipeAbstract) -> None:
        pass

    @abstractmethod
    def add_pipes(self, pipes: list[PipeAbstract]) -> None:
        pass
