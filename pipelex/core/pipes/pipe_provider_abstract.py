"""The read-side pipe-resolution contract, owned by `core/` rather than by the library.

The counterpart of :class:`~pipelex.core.concepts.concept_provider_abstract.ConceptProviderAbstract`
for pipes: `core/` sometimes has to follow a pipe reference it discovers *inside* a pipe graph (a
condition's mapped pipes, a sequence's last step), which the caller cannot pre-resolve for it. It
declares that need as a parameter instead of reaching for `method_hub.get_required_pipe`.

Managing the pipe library — adding, listing, setup/teardown — stays high, on `PipeLibraryAbstract`,
which extends this. See ``docs/contribute/hub-layering.md``.
"""

from abc import ABC, abstractmethod

from pipelex.core.pipes.pipe_abstract import PipeAbstract


class PipeProviderAbstract(ABC):
    """Resolves pipe codes into pipes."""

    @abstractmethod
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        """Resolve a pipe code, raising when it is not known."""
