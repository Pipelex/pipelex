from typing import ClassVar

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOffer


class CrateQualificationTestData:
    """A crate for the qualification pass, built fresh on each call since a test may change it."""

    @classmethod
    def crate(cls) -> LibraryCrate:
        """A crate carrying one bare ref of every kind the pass advertises."""
        return LibraryCrate(
            concepts={
                "alpha.Category": "a category",
                "alpha.Report": ConceptBlueprint(
                    description="a report",
                    structure={
                        "label": ConceptStructureBlueprint(
                            description="the label",
                            type=ConceptStructureBlueprintFieldType.CONCEPT,
                            concept_ref="Category",
                        ),
                        "tags": ConceptStructureBlueprint(
                            description="the tags",
                            type=ConceptStructureBlueprintFieldType.LIST,
                            item_type=ConceptStructureBlueprintFieldType.CONCEPT,
                            item_concept_ref="Category",
                        ),
                    },
                ),
                "alpha.Detailed": ConceptBlueprint(description="a detailed report", refines="Report"),
            },
            pipes={
                "alpha.leaf": PipeLLMBlueprint(description="leaf", inputs={"item": "Category"}, output="Report", prompt="use $item"),
                "alpha.seq": PipeSequenceBlueprint(description="seq", output="Report", steps=[SubPipeBlueprint(pipe="leaf")]),
                "alpha.par": PipeParallelBlueprint(
                    description="par",
                    output="Composite",
                    branches=[SubPipeBlueprint(pipe="leaf", result="one")],
                ),
                "alpha.cond": PipeConditionBlueprint(
                    description="cond",
                    output="Report",
                    expression="x",
                    outcomes={"hit": "leaf"},
                    default_outcome="leaf",
                ),
                "alpha.batched": PipeBatchBlueprint(
                    description="batch",
                    inputs={"items": "Category[]"},
                    output="Report[]",
                    branch_pipe_code="leaf",
                    input_list_name="items",
                    input_item_name="item",
                ),
            },
            domains={"alpha": DomainBlueprint(code="alpha", description="alpha domain")},
        )


class MethodRequirementsTestData:
    """Lines of a method's requirements.txt, as the MTHDS standard reads them, and a package set to judge them against."""

    # (topic, line, the requirement's name when the line declares one)
    ACCEPTED_LINES: ClassVar[list[tuple[str, str, str]]] = [
        ("bare name", "pandas", "pandas"),
        ("range", "pandas>=2.2,<3", "pandas"),
        ("pinned", "openpyxl==3.1.5", "openpyxl"),
        ("wildcard", "pandas==2.*", "pandas"),
        ("extras", "pandas[excel]>=2", "pandas"),
        ("marker", 'tzdata; python_version >= "3.12"', "tzdata"),
        ("spaced marker", "pandas >= 2.0 ; sys_platform == 'linux'", "pandas"),
        ("indented", "   numpy", "numpy"),
        ("dotted name", "zope.interface>=6", "zope.interface"),
    ]

    # (topic, line, a fragment of the reason the line is refused)
    REFUSED_LINES: ClassVar[list[tuple[str, str, str]]] = [
        ("direct reference", "name @ https://example.com/name-1.0.whl", "naming a URL"),
        ("bare URL", "https://example.com/name-1.0.whl", "naming a URL"),
        ("requirement file option", "-r base.txt", "option line"),
        ("editable option", "-e .", "option line"),
        ("constraint option", "-c constraints.txt", "option line"),
        ("index option", "--index-url https://example.com/simple", "option line"),
        ("trailing comment", "openpyxl==3.1.5  # spreadsheets", "comment after a requirement"),
        ("trailing comment mentioning a URL", "foo # see https://x.y", "comment after a requirement"),
        ("direct reference with a hash fragment", "name @ https://example.com/name-1.0.whl#sha256=abc", "naming a URL"),
        ("direct reference with a trailing comment", "name @ https://example.com/name-1.0.whl  # pinned", "naming a URL"),
        ("continued line", "pandas>=2 \\", "continued with a backslash"),
        ("local path", "./vendor/package", "not a PEP 508 requirement"),
        ("version without operator", "pandas 2.2", "not a PEP 508 requirement"),
    ]

    SANDBOX_ENVIRONMENT = "the Daytona sandbox snapshot 'pipelex-base-test'"
    # A Linux CPython 3.12, the marker environment of every box of the Daytona sandbox.
    SANDBOX_MARKER_ENVIRONMENT: ClassVar[dict[str, str]] = {
        "implementation_name": "cpython",
        "os_name": "posix",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "platform_system": "Linux",
        "python_version": "3.12",
        "sys_platform": "linux",
    }

    @classmethod
    def sandbox_offer(cls) -> PipeFuncPackageOffer:
        """A package set as the Daytona plugin would state it for its snapshot: canonical names, a Linux CPython 3.12."""
        return PipeFuncPackageOffer(
            environment=cls.SANDBOX_ENVIRONMENT,
            distributions={"pandas": "2.2.3", "openpyxl": "3.1.5", "numpy": "2.1.0rc1", "Zope.Interface": "7.0"},
            marker_environment=dict(cls.SANDBOX_MARKER_ENVIRONMENT),
        )

    @classmethod
    def environment_offer(cls, *, snapshot_name: str, distributions: dict[str, str]) -> PipeFuncPackageOffer:
        """An environment a sandbox mode builds for one method's requirements, as it would state it: its own snapshot and packages."""
        return PipeFuncPackageOffer(
            environment=f"the Daytona sandbox environment '{snapshot_name}'",
            distributions=distributions,
            marker_environment=dict(cls.SANDBOX_MARKER_ENVIRONMENT),
        )
