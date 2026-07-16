"""Unit tests for the `main_pipe` cross-field dependency in DryRunFactory."""

from pydantic import BaseModel, Field

from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory

# =============================================================================
# Test Fixtures
# =============================================================================


class PipeStub(BaseModel):
    """Minimal stand-in for a pipe definition living inside the `pipe` dict."""

    description: str = Field(..., description="A pipe definition stand-in")


class BundleStub(BaseModel):
    """Mirrors the real bundle shape (`PipelexBundleBlueprint` / builder `BundleSpec`).

    The combination of a `pipe` dict and a `main_pipe` that must reference one of its
    keys is exactly what makes `DryRunFactory.make_dry_run_factory` register the
    `PostGenerated(_main_pipe_from_pipe_dict)` cross-field provider.
    """

    main_pipe: str = Field(..., description="The bundle's main pipe; must be a key in `pipe`")
    pipe: dict[str, PipeStub] = Field(..., description="Pipe definitions keyed by pipe code")


# =============================================================================
# Tests
# =============================================================================


class TestDryRunFactoryMainPipe:
    """Test that DryRunFactory resolves `main_pipe` against the generated `pipe` dict."""

    def test_build_does_not_raise_for_main_pipe_postgenerated(self) -> None:
        """Regression for the keyword-only refactor of `_main_pipe_from_pipe_dict`.

        A model carrying both `main_pipe` and `pipe` registers the callback via
        polyfactory `PostGenerated`, which invokes it positionally as `fn(name, values)`.
        Making `values` keyword-only breaks the build with
        `TypeError: _main_pipe_from_pipe_dict() takes 1 positional argument but 2 were given`.
        """
        factory = DryRunFactory.make_dry_run_factory(BundleStub)
        instance = factory.build()
        assert isinstance(instance.main_pipe, str)
        assert instance.main_pipe, "main_pipe must be a non-empty string"

    def test_main_pipe_references_a_generated_pipe_key(self) -> None:
        """The callback's whole purpose: `main_pipe` must point at one of the generated pipe keys."""
        factory = DryRunFactory.make_dry_run_factory(BundleStub)
        instance = factory.build()
        assert instance.pipe, "factory should generate at least one pipe entry"
        assert instance.main_pipe in instance.pipe, f"main_pipe {instance.main_pipe!r} must be one of the generated pipe keys {list(instance.pipe)!r}"
