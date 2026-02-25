import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mthds.client.models.pipeline_inputs import PipelineInputs
from mthds.package.bundle_scanner import build_domain_exports_from_scan, scan_bundles_for_domain_info
from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.manifest.parser import serialize_manifest_to_toml
from mthds.package.manifest.schema import MethodsManifest

from pipelex import builder, log
from pipelex.builder.builder import (
    PipelexBundleSpec,
    PipeSpecUnion,
    reconstruct_bundle_with_pipe_fixes,
)
from pipelex.builder.builder_errors import PipeBuilderError
from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpecFieldType
from pipelex.builder.exceptions import PipelexBundleSpecBlueprintError
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.core.pipes.pipe_blueprint import PipeCategory
from pipelex.core.pipes.variable_multiplicity import format_concept_with_multiplicity, parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import get_required_pipe
from pipelex.language.mthds_factory import MthdsFactory
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipeline.runner import PipelexRunner
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.tools.misc.file_utils import get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

if TYPE_CHECKING:
    from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition


class BuilderLoop:
    async def build_and_fix(
        self,
        builder_pipe: str,
        inputs: PipelineInputs | None = None,
        execution_config: PipelineExecutionConfig | None = None,
        is_save_first_iteration_enabled: bool = True,
        is_save_second_iteration_enabled: bool = True,
        is_save_working_memory_enabled: bool = True,
        output_dir: str | None = None,
    ) -> tuple[PipelexBundleSpec, GraphSpec | None]:
        # TODO: Doesn't make sense to be able to put a builder_pipe code but hardcoding the Path to the builder pipe.
        runner = PipelexRunner(
            library_dirs=[str(Path(builder.__file__).parent)],
            execution_config=execution_config,
        )
        response = await runner.execute_pipeline(
            pipe_code=builder_pipe,
            inputs=inputs,
        )
        pipe_output = response.pipe_output

        if is_save_working_memory_enabled:
            working_memory_path = get_incremental_file_path(
                base_path=output_dir or "results/pipe-builder",
                base_name="working_memory",
                extension="json",
            )
            save_as_json_to_path(object_to_save=pipe_output.working_memory.smart_dump(), path=str(working_memory_path), create_directory=True)

        pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
        if pipelex_bundle_spec.pipe:
            log.debug(f"Builder produced spec with pipe keys: {list(pipelex_bundle_spec.pipe.keys())}")
            log.debug(f"Builder produced spec with main_pipe: '{pipelex_bundle_spec.main_pipe}'")
        pipelex_bundle_spec = self._strip_native_concept_declarations(pipelex_bundle_spec=pipelex_bundle_spec)
        pipelex_bundle_spec = self._strip_namespace_from_pipe_codes(pipelex_bundle_spec=pipelex_bundle_spec)

        if pipelex_bundle_spec.pipe:
            for pipe_key, pipe_spec in pipelex_bundle_spec.pipe.items():
                pipe_detail = f"key='{pipe_key}', pipe_code='{pipe_spec.pipe_code}', type={pipe_spec.type}"
                if isinstance(pipe_spec, PipeBatchSpec):
                    pipe_detail += f", branch_pipe_code='{pipe_spec.branch_pipe_code}'"
                elif isinstance(pipe_spec, PipeSequenceSpec):
                    step_codes = [step.pipe_code for step in pipe_spec.steps]
                    pipe_detail += f", step_pipe_codes={step_codes}"
                elif isinstance(pipe_spec, PipeParallelSpec):
                    branch_codes = [branch.pipe_code for branch in pipe_spec.branches]
                    pipe_detail += f", branch_pipe_codes={branch_codes}"
                elif isinstance(pipe_spec, PipeConditionSpec):
                    pipe_detail += f", outcome_values={list(pipe_spec.outcomes.values())}"
                log.debug(f"  Pipe spec: {pipe_detail}")

        if is_save_first_iteration_enabled:
            try:
                mthds_content = MthdsFactory.make_mthds_content(blueprint=pipelex_bundle_spec.to_blueprint())
                first_iteration_path = get_incremental_file_path(
                    base_path=output_dir or "results/pipe-builder",
                    base_name="generated_pipeline_1st_iteration",
                    extension="mthds",
                )
                save_text_to_path(text=mthds_content, path=str(first_iteration_path), create_directory=True)
            except PipelexBundleSpecBlueprintError as exc:
                log.warning(f"Could not save first iteration MTHDS: {exc}")

        max_attempts = get_config().pipelex.builder_config.fix_loop_max_attempts
        for attempt in range(1, max_attempts + 1):
            log.debug(f"Fix loop attempt {attempt}/{max_attempts}")

            # Phase 1: Create blueprint from spec
            log.debug("Phase 1: creating blueprint from spec")
            try:
                bundle_blueprint = pipelex_bundle_spec.to_blueprint()
            except PipelexBundleSpecBlueprintError as exc:
                log.debug("Phase 1: blueprint creation failed")
                if attempt < max_attempts:
                    log.info(f"⚠️ Blueprint creation failed on attempt {attempt}/{max_attempts}, fixing undeclared concepts...")
                    pipelex_bundle_spec = await self._fix_undeclared_concept_references(pipelex_bundle_spec=pipelex_bundle_spec)
                    pipelex_bundle_spec = self._strip_native_concept_declarations(pipelex_bundle_spec=pipelex_bundle_spec)
                    pipelex_bundle_spec = self._strip_namespace_from_pipe_codes(pipelex_bundle_spec=pipelex_bundle_spec)
                    continue
                msg = f"Failed to create bundle blueprint after {max_attempts} attempts: {exc}"
                raise PipeBuilderError(msg) from exc

            log.debug("Phase 1: blueprint created successfully")

            # Phase 2: Validate the bundle
            log.debug("Phase 2: validating bundle")
            try:
                await validate_bundle(blueprints=[bundle_blueprint])
                log.debug("Phase 2: validation passed")
                if attempt > 1:
                    log.info(f"✅ Bundle validation passed after fixes (attempt {attempt}/{max_attempts})")
                break  # Validation passed
            except ValidateBundleError as exc:
                if attempt < max_attempts:
                    log.info(f"⚠️ Validation failed on attempt {attempt}/{max_attempts}, attempting fixes...")
                    pipelex_bundle_spec = self._fix_bundle_validation_error(
                        bundle_error=exc,
                        pipelex_bundle_spec=pipelex_bundle_spec,
                        is_save_second_iteration_enabled=is_save_second_iteration_enabled,
                        output_dir=output_dir,
                    )
                    if pipelex_bundle_spec.pipe:
                        log.debug(f"After Phase 2 fix: pipe keys={list(pipelex_bundle_spec.pipe.keys())}")
                    pipelex_bundle_spec = self._strip_native_concept_declarations(pipelex_bundle_spec=pipelex_bundle_spec)
                    pipelex_bundle_spec = self._strip_namespace_from_pipe_codes(pipelex_bundle_spec=pipelex_bundle_spec)
                else:
                    log.error(f"❌ Validation failed after {max_attempts} attempts, raising error")
                    # Save the last bundle state so the user can inspect/fix it manually
                    try:
                        mthds_content = MthdsFactory.make_mthds_content(blueprint=pipelex_bundle_spec.to_blueprint())
                        failed_bundle_path = get_incremental_file_path(
                            base_path=output_dir or "results/pipe-builder",
                            base_name="failed_bundle",
                            extension="mthds",
                        )
                        save_text_to_path(text=mthds_content, path=str(failed_bundle_path), create_directory=True)
                        log.warning(f"Last bundle state saved to: {failed_bundle_path}")
                        exc.failed_bundle_path = str(failed_bundle_path)
                    except Exception as save_exc:
                        log.warning(f"Could not save failed bundle state: {save_exc}")
                    raise

        return pipelex_bundle_spec, pipe_output.graph_spec

    async def _fix_undeclared_concept_references(
        self,
        pipelex_bundle_spec: PipelexBundleSpec,
    ) -> PipelexBundleSpec:
        """Fix undeclared concept references in pipe and concept specs.

        Collects all concept references from pipe specs and concept definitions (refines,
        structure concept_ref, item_concept_ref), determines which are undeclared,
        fixes PipeParallel combined_output references deterministically, and generates
        ConceptSpec definitions for any remaining undeclared concepts via an LLM pipeline.
        """
        # Step 1: Collect all local concept references from pipe specs and concept definitions
        concept_references: list[tuple[str, str, str]] = []  # (bare_concept_code, source_description, field_context)
        if pipelex_bundle_spec.pipe:
            for pipe_code, pipe_spec in pipelex_bundle_spec.pipe.items():
                source = f"pipe '{pipe_code}'"
                # Parse output — skip cross-package refs
                output_parse = parse_concept_with_multiplicity(pipe_spec.output)
                output_concept = output_parse.concept_ref_or_code
                if not QualifiedRef.has_cross_package_prefix(output_concept):
                    if "." not in output_concept or output_concept.split(".")[0] == pipelex_bundle_spec.domain:
                        bare_code = output_concept.split(".")[-1] if "." in output_concept else output_concept
                        concept_references.append((bare_code, source, "output"))

                # Parse inputs — skip cross-package refs
                if pipe_spec.inputs:
                    for input_name, input_concept_str in pipe_spec.inputs.items():
                        input_parse = parse_concept_with_multiplicity(input_concept_str)
                        input_concept = input_parse.concept_ref_or_code
                        if not QualifiedRef.has_cross_package_prefix(input_concept):
                            if "." not in input_concept or input_concept.split(".")[0] == pipelex_bundle_spec.domain:
                                bare_code = input_concept.split(".")[-1] if "." in input_concept else input_concept
                                concept_references.append((bare_code, source, f"input '{input_name}'"))

                # Parse PipeParallel combined_output — skip cross-package refs
                if isinstance(pipe_spec, PipeParallelSpec) and pipe_spec.combined_output:
                    combined_parse = parse_concept_with_multiplicity(pipe_spec.combined_output)
                    combined_concept = combined_parse.concept_ref_or_code
                    if not QualifiedRef.has_cross_package_prefix(combined_concept):
                        if "." not in combined_concept or combined_concept.split(".")[0] == pipelex_bundle_spec.domain:
                            bare_code = combined_concept.split(".")[-1] if "." in combined_concept else combined_concept
                            concept_references.append((bare_code, source, "combined_output"))

        # Collect concept references from concept definitions (refines, structure concept_ref, item_concept_ref)
        if pipelex_bundle_spec.concept:
            for concept_code, concept_spec_or_name in pipelex_bundle_spec.concept.items():
                if not isinstance(concept_spec_or_name, ConceptSpec):
                    continue
                source = f"concept '{concept_code}'"

                # Check refines — skip cross-package refs
                if concept_spec_or_name.refines:
                    ref = concept_spec_or_name.refines
                    if not QualifiedRef.has_cross_package_prefix(ref) and ("." not in ref or ref.split(".")[0] == pipelex_bundle_spec.domain):
                        bare_code = ref.split(".")[-1] if "." in ref else ref
                        concept_references.append((bare_code, source, "refines"))

                # Check structure fields — skip cross-package refs
                if concept_spec_or_name.structure:
                    for field_name, field_spec in concept_spec_or_name.structure.items():
                        if field_spec.concept_ref:
                            ref = field_spec.concept_ref
                            if not QualifiedRef.has_cross_package_prefix(ref):
                                if "." not in ref or ref.split(".")[0] == pipelex_bundle_spec.domain:
                                    bare_code = ref.split(".")[-1] if "." in ref else ref
                                    concept_references.append((bare_code, source, f"structure.{field_name}.concept_ref"))
                        if field_spec.item_concept_ref:
                            ref = field_spec.item_concept_ref
                            if not QualifiedRef.has_cross_package_prefix(ref):
                                if "." not in ref or ref.split(".")[0] == pipelex_bundle_spec.domain:
                                    bare_code = ref.split(".")[-1] if "." in ref else ref
                                    concept_references.append((bare_code, source, f"structure.{field_name}.item_concept_ref"))

        # Step 2: Determine which are undeclared
        declared_concepts: set[str] = set()
        if pipelex_bundle_spec.concept:
            declared_concepts = set(pipelex_bundle_spec.concept.keys())
        native_concept_codes = {native.value for native in NativeConceptCode.values_list()}

        undeclared: set[str] = set()
        undeclared_refs: list[tuple[str, str, str]] = []
        for ref_code, source_desc, field_context in concept_references:
            if ref_code not in declared_concepts and ref_code not in native_concept_codes:
                undeclared.add(ref_code)
                undeclared_refs.append((ref_code, source_desc, field_context))

        if not undeclared:
            return pipelex_bundle_spec

        log.info(f"🔍 Found {len(undeclared)} undeclared concept(s): {', '.join(sorted(undeclared))}")

        # Step 3: Fix PipeParallel combined_output deterministically (no pipeline needed)
        if pipelex_bundle_spec.pipe:
            for pipe_code, pipe_spec in pipelex_bundle_spec.pipe.items():
                if not isinstance(pipe_spec, PipeParallelSpec):
                    continue
                if not pipe_spec.combined_output:
                    continue

                combined_parse = parse_concept_with_multiplicity(pipe_spec.combined_output)
                combined_concept = combined_parse.concept_ref_or_code
                bare_combined = combined_concept.split(".")[-1] if "." in combined_concept else combined_concept

                if bare_combined not in undeclared:
                    continue

                if pipe_spec.add_each_output:
                    log.info(f"🔧 Removing undeclared combined_output '{pipe_spec.combined_output}' from PipeParallel '{pipe_code}'")
                    pipe_spec.combined_output = None

                    # Also fix output if it references an undeclared concept
                    output_parse = parse_concept_with_multiplicity(pipe_spec.output)
                    output_concept = output_parse.concept_ref_or_code
                    bare_output = output_concept.split(".")[-1] if "." in output_concept else output_concept
                    if bare_output in undeclared:
                        log.info(f"🔧 Setting output of PipeParallel '{pipe_code}' to 'Anything'")
                        pipe_spec.output = "Anything"

        # Recompute undeclared: some concepts may no longer be referenced after PipeParallel fixes
        still_referenced = self._collect_local_bare_concept_codes(pipelex_bundle_spec=pipelex_bundle_spec)
        no_longer_referenced = undeclared - still_referenced
        if no_longer_referenced:
            log.info(f"🔧 Concepts no longer referenced after PipeParallel fixes: {', '.join(sorted(no_longer_referenced))}")
            undeclared -= no_longer_referenced

        # Step 4: Create remaining undeclared concepts via pipeline
        if undeclared:
            # Build context for the LLM
            lines: list[str] = ["Missing concepts that need to be defined:\n"]
            for ref_code, source_desc, field_context in undeclared_refs:
                if ref_code in undeclared:
                    lines.append(f"- '{ref_code}' referenced in {source_desc} ({field_context})")

            lines.append("\nExisting declared concepts for context:")
            if pipelex_bundle_spec.concept:
                for concept_code, concept_spec_or_name in pipelex_bundle_spec.concept.items():
                    if isinstance(concept_spec_or_name, ConceptSpec):
                        lines.append(f"- {concept_code}: {concept_spec_or_name.description}")
                    else:
                        lines.append(f"- {concept_code}: {concept_spec_or_name}")
            else:
                lines.append("- (none)")

            undeclared_concepts = "\n".join(lines)
            log.info(f"🤖 Generating ConceptSpec definitions for {len(undeclared)} undeclared concept(s) via LLM...")

            concept_fixer_runner = PipelexRunner(
                library_dirs=[str(Path(builder.__file__).parent / "concept")],
            )
            concept_fixer_response = await concept_fixer_runner.execute_pipeline(
                pipe_code="generate_missing_concepts",
                inputs={"undeclared_concepts": undeclared_concepts},
            )
            concept_fixer_output = concept_fixer_response.pipe_output

            generated_concepts_list = concept_fixer_output.working_memory.get_stuff_as_list(
                name="generate_missing_concepts",
                item_type=ConceptSpec,
            )

            if pipelex_bundle_spec.concept is None:
                pipelex_bundle_spec.concept = {}

            for concept_spec in generated_concepts_list.items:
                pipelex_bundle_spec.concept[concept_spec.the_concept_code] = concept_spec
                log.info(f"🔧 Added generated concept '{concept_spec.the_concept_code}' to bundle")

        return self._prune_unreachable_specs(pipelex_bundle_spec=pipelex_bundle_spec)

    def _prune_unreachable_specs(self, pipelex_bundle_spec: PipelexBundleSpec) -> PipelexBundleSpec:
        """Remove unreachable pipes and unused concepts from the bundle spec.

        Walks the call graph from main_pipe to find all reachable pipes, removes
        unreachable ones, then collects all concept references from reachable pipes
        and concept definitions (transitively) to remove unused concepts.

        Args:
            pipelex_bundle_spec: The bundle spec to prune (modified in place)

        Returns:
            The pruned bundle spec
        """
        if not pipelex_bundle_spec.pipe:
            return pipelex_bundle_spec

        domain = pipelex_bundle_spec.domain

        # Step A: Find all reachable pipes by walking the call graph from main_pipe
        reachable_pipes: set[str] = set()
        to_visit: list[str] = [pipelex_bundle_spec.main_pipe]
        special_outcome_values = SpecialOutcome.value_list()

        while to_visit:
            pipe_code = to_visit.pop()
            if pipe_code in reachable_pipes:
                continue

            pipe_spec = pipelex_bundle_spec.pipe.get(pipe_code)
            if pipe_spec is None:
                log.warning(f"Pipe '{pipe_code}' is referenced but not found in bundle spec pipes")
                continue
            reachable_pipes.add(pipe_code)

            sub_pipe_codes: list[str] = []
            if isinstance(pipe_spec, PipeSequenceSpec):
                sub_pipe_codes = [step.pipe_code for step in pipe_spec.steps]
            elif isinstance(pipe_spec, PipeParallelSpec):
                sub_pipe_codes = [branch.pipe_code for branch in pipe_spec.branches]
            elif isinstance(pipe_spec, PipeBatchSpec):
                sub_pipe_codes = [pipe_spec.branch_pipe_code]
            elif isinstance(pipe_spec, PipeConditionSpec):
                for outcome_value in pipe_spec.outcomes.values():
                    if outcome_value not in special_outcome_values:
                        sub_pipe_codes.append(outcome_value)
                if pipe_spec.default_outcome not in special_outcome_values:
                    sub_pipe_codes.append(pipe_spec.default_outcome)

            to_visit.extend(sub_pipe_codes)

        # Step B: Remove unreachable pipes
        unreachable = set(pipelex_bundle_spec.pipe.keys()) - reachable_pipes
        for pipe_code in unreachable:
            del pipelex_bundle_spec.pipe[pipe_code]
            log.info(f"🧹 Removed unreachable pipe '{pipe_code}'")

        # Step C: Collect all concept references from reachable pipes
        referenced_concepts: set[str] = set()
        for pipe_code in reachable_pipes:
            pipe_spec = pipelex_bundle_spec.pipe.get(pipe_code)
            if pipe_spec is None:
                continue
            referenced_concepts.update(self._collect_concept_refs_from_pipe_spec(pipe_spec=pipe_spec, domain=domain))

        # Step D: Collect transitive concept references from concept definitions
        if pipelex_bundle_spec.concept:
            changed = True
            while changed:
                changed = False
                for concept_code in list(referenced_concepts):
                    concept_spec_or_name = pipelex_bundle_spec.concept.get(concept_code)
                    if not isinstance(concept_spec_or_name, ConceptSpec):
                        continue
                    new_refs = self._collect_concept_refs_from_concept_spec(concept_spec=concept_spec_or_name, domain=domain)
                    for bare_ref in new_refs:
                        if bare_ref not in referenced_concepts and bare_ref in pipelex_bundle_spec.concept:
                            referenced_concepts.add(bare_ref)
                            changed = True

        # Step E: Remove unused concepts
        if pipelex_bundle_spec.concept:
            unused = set(pipelex_bundle_spec.concept.keys()) - referenced_concepts
            for concept_code in unused:
                del pipelex_bundle_spec.concept[concept_code]
                log.info(f"🧹 Removed unused concept '{concept_code}'")

        return pipelex_bundle_spec

    @staticmethod
    def _extract_local_bare_code(concept_ref_or_code: str, domain: str) -> str | None:
        """Extract a bare concept code only if the reference is local.

        A reference is considered local if it has no domain prefix or if
        its domain prefix matches the bundle domain. Cross-package refs
        (containing '->') are never local.

        Args:
            concept_ref_or_code: A concept reference like "Document", "my_domain.Document", or "external.Document"
            domain: The bundle's domain

        Returns:
            The bare concept code if local, or None if external or cross-package
        """
        if QualifiedRef.has_cross_package_prefix(concept_ref_or_code):
            return None
        if "." not in concept_ref_or_code:
            return concept_ref_or_code
        prefix, bare_code = concept_ref_or_code.rsplit(".", maxsplit=1)
        if prefix == domain:
            return bare_code
        return None

    @staticmethod
    def _collect_concept_refs_from_pipe_spec(pipe_spec: PipeSpecUnion, domain: str) -> set[str]:
        """Collect local bare concept codes referenced by a single pipe spec.

        Scans output, inputs, and (for PipeParallelSpec) combined_output.

        Args:
            pipe_spec: The pipe spec to scan
            domain: The bundle's domain for locality filtering

        Returns:
            Set of bare concept codes referenced by this pipe spec
        """
        refs: set[str] = set()

        # Output
        output_parse = parse_concept_with_multiplicity(pipe_spec.output)
        bare_output = BuilderLoop._extract_local_bare_code(concept_ref_or_code=output_parse.concept_ref_or_code, domain=domain)
        if bare_output is not None:
            refs.add(bare_output)

        # Inputs
        if pipe_spec.inputs:
            for input_concept_str in pipe_spec.inputs.values():
                input_parse = parse_concept_with_multiplicity(input_concept_str)
                bare_input = BuilderLoop._extract_local_bare_code(concept_ref_or_code=input_parse.concept_ref_or_code, domain=domain)
                if bare_input is not None:
                    refs.add(bare_input)

        # PipeParallel combined_output
        if isinstance(pipe_spec, PipeParallelSpec) and pipe_spec.combined_output:
            combined_parse = parse_concept_with_multiplicity(pipe_spec.combined_output)
            bare_combined = BuilderLoop._extract_local_bare_code(concept_ref_or_code=combined_parse.concept_ref_or_code, domain=domain)
            if bare_combined is not None:
                refs.add(bare_combined)

        return refs

    @staticmethod
    def _collect_concept_refs_from_concept_spec(concept_spec: ConceptSpec, domain: str) -> set[str]:
        """Collect local bare concept codes referenced by a single concept spec.

        Scans refines, and structure fields' concept_ref and item_concept_ref.

        Args:
            concept_spec: The concept spec to scan
            domain: The bundle's domain for locality filtering

        Returns:
            Set of bare concept codes referenced by this concept spec
        """
        refs: set[str] = set()

        # Refines
        if concept_spec.refines:
            bare_ref = BuilderLoop._extract_local_bare_code(concept_ref_or_code=concept_spec.refines, domain=domain)
            if bare_ref is not None:
                refs.add(bare_ref)

        # Structure fields
        if concept_spec.structure:
            for field_spec in concept_spec.structure.values():
                if field_spec.concept_ref:
                    bare_ref = BuilderLoop._extract_local_bare_code(concept_ref_or_code=field_spec.concept_ref, domain=domain)
                    if bare_ref is not None:
                        refs.add(bare_ref)
                if field_spec.item_concept_ref:
                    bare_ref = BuilderLoop._extract_local_bare_code(concept_ref_or_code=field_spec.item_concept_ref, domain=domain)
                    if bare_ref is not None:
                        refs.add(bare_ref)

        return refs

    @staticmethod
    def _collect_local_bare_concept_codes(pipelex_bundle_spec: PipelexBundleSpec) -> set[str]:
        """Collect bare concept codes referenced locally from pipe specs and concept definitions.

        Only includes references whose domain prefix is absent or matches the bundle domain.
        This is used to determine which concepts are still actively referenced after spec mutations.

        Args:
            pipelex_bundle_spec: The bundle spec to scan

        Returns:
            Set of bare concept codes (without domain prefix) that are referenced
        """
        domain = pipelex_bundle_spec.domain
        referenced: set[str] = set()

        # Scan pipe specs
        if pipelex_bundle_spec.pipe:
            for pipe_spec in pipelex_bundle_spec.pipe.values():
                referenced.update(BuilderLoop._collect_concept_refs_from_pipe_spec(pipe_spec=pipe_spec, domain=domain))

        # Scan concept definitions
        if pipelex_bundle_spec.concept:
            for concept_spec_or_name in pipelex_bundle_spec.concept.values():
                if not isinstance(concept_spec_or_name, ConceptSpec):
                    continue
                referenced.update(BuilderLoop._collect_concept_refs_from_concept_spec(concept_spec=concept_spec_or_name, domain=domain))

        return referenced

    @staticmethod
    def _strip_native_concept_declarations(pipelex_bundle_spec: PipelexBundleSpec) -> PipelexBundleSpec:
        """Remove any concept declarations that collide with native concept codes.

        Native concepts are built-in and must not be redeclared in a bundle.
        This is a safety net for when the builder LLM ignores the instruction
        not to redefine them.
        """
        if not pipelex_bundle_spec.concept:
            return pipelex_bundle_spec
        native_codes = {native.value for native in NativeConceptCode.values_list()}
        to_remove = [code for code in pipelex_bundle_spec.concept if code in native_codes]
        for code in to_remove:
            del pipelex_bundle_spec.concept[code]
            log.info(f"Stripped native concept declaration '{code}' (native concepts are built-in)")
        return pipelex_bundle_spec

    @staticmethod
    def _strip_dotted_pipe_code(pipe_code: str) -> str:
        """Extract bare pipe code from a potentially dotted pipe code.

        If the code contains a dot, return the part after the last dot.
        Otherwise, return the code unchanged.

        Args:
            pipe_code: A pipe code like "my_pipe" or "domain.my_pipe" or "a.b.my_pipe"

        Returns:
            The bare pipe code (part after last dot, or unchanged if no dot)
        """
        if "." in pipe_code:
            return pipe_code.rsplit(".", maxsplit=1)[1]
        return pipe_code

    @staticmethod
    def _strip_namespace_from_pipe_codes(pipelex_bundle_spec: PipelexBundleSpec) -> PipelexBundleSpec:
        """Strip namespace prefixes from pipe definition codes and internal pipe references.

        The builder LLM sometimes generates dotted pipe codes (e.g., 'domain.my_pipe')
        for pipe definitions and internal references. Pipe definition codes must be bare
        snake_case since the namespace comes from the bundle's domain field.

        Pipe definition keys and pipe_code fields are always stripped (unconditionally).
        Internal pipe references in controllers (branch_pipe_code, steps, branches,
        outcomes) are only stripped when the stripped code matches a pipe defined in
        the same bundle — otherwise the reference may legitimately point to a pipe
        in another domain.

        Affected fields:
        - Pipe dict keys (unconditional)
        - main_pipe (unconditional)
        - PipeSpec.pipe_code inside each pipe value (unconditional)
        - PipeBatchSpec.branch_pipe_code (conditional on bundle membership)
        - PipeSequenceSpec.steps[*].pipe_code (conditional on bundle membership)
        - PipeParallelSpec.branches[*].pipe_code (conditional on bundle membership)
        - PipeConditionSpec.outcomes values and default_outcome (conditional on bundle membership)
        """
        strip = BuilderLoop._strip_dotted_pipe_code
        special_outcome_values = SpecialOutcome.value_list()

        # Strip main_pipe (unconditional — it always refers to a pipe in this bundle)
        stripped_main = strip(pipelex_bundle_spec.main_pipe)
        if stripped_main != pipelex_bundle_spec.main_pipe:
            log.info(f"Stripped namespace from main_pipe: '{pipelex_bundle_spec.main_pipe}' → '{stripped_main}'")
            pipelex_bundle_spec.main_pipe = stripped_main

        if not pipelex_bundle_spec.pipe:
            return pipelex_bundle_spec

        # Pass 1: Strip pipe dict keys and pipe_code fields (unconditional for definitions),
        # and build the set of defined bare pipe codes for reference resolution
        new_pipes: dict[str, PipeSpecUnion] = {}
        for key, pipe_spec in pipelex_bundle_spec.pipe.items():
            stripped_key = strip(key)
            if stripped_key != key:
                log.info(f"Stripped namespace from pipe key: '{key}' → '{stripped_key}'")

            stripped_pipe_code = strip(pipe_spec.pipe_code)
            if stripped_pipe_code != pipe_spec.pipe_code:
                log.info(f"Stripped namespace from pipe_code: '{pipe_spec.pipe_code}' → '{stripped_pipe_code}'")
                pipe_spec.pipe_code = stripped_pipe_code

            new_pipes[stripped_key] = pipe_spec

        pipelex_bundle_spec.pipe = new_pipes
        defined_pipe_codes = set(new_pipes.keys())

        # Pass 2: Strip internal pipe references when the stripped code matches
        # a pipe defined in this bundle OR the dotted prefix matches the bundle's
        # own domain (LLM hallucinating the namespace). Only preserve dotted codes
        # whose prefix is a genuinely different domain.
        bundle_domain = pipelex_bundle_spec.domain

        def _should_strip_ref(ref_code: str, stripped_code: str) -> bool:
            """Decide whether a dotted pipe reference should be stripped.

            Strip if the bare code exists in the bundle's defined pipes, or if
            the dotted prefix matches the bundle's own domain.
            """
            if stripped_code == ref_code:
                return False
            ref_domain = get_root_from_dotted_path(ref_code)
            return stripped_code in defined_pipe_codes or ref_domain == bundle_domain

        for pipe_spec in pipelex_bundle_spec.pipe.values():
            if isinstance(pipe_spec, PipeBatchSpec):
                stripped_branch = strip(pipe_spec.branch_pipe_code)
                if _should_strip_ref(pipe_spec.branch_pipe_code, stripped_branch):
                    log.info(f"Stripped namespace from branch_pipe_code: '{pipe_spec.branch_pipe_code}' → '{stripped_branch}'")
                    pipe_spec.branch_pipe_code = stripped_branch

            elif isinstance(pipe_spec, PipeSequenceSpec):
                for step in pipe_spec.steps:
                    stripped_step = strip(step.pipe_code)
                    if _should_strip_ref(step.pipe_code, stripped_step):
                        log.info(f"Stripped namespace from sequence step pipe_code: '{step.pipe_code}' → '{stripped_step}'")
                        step.pipe_code = stripped_step

            elif isinstance(pipe_spec, PipeParallelSpec):
                for branch in pipe_spec.branches:
                    stripped_branch = strip(branch.pipe_code)
                    if _should_strip_ref(branch.pipe_code, stripped_branch):
                        log.info(f"Stripped namespace from parallel branch pipe_code: '{branch.pipe_code}' → '{stripped_branch}'")
                        branch.pipe_code = stripped_branch

            elif isinstance(pipe_spec, PipeConditionSpec):
                new_outcomes: dict[str, str] = {}
                for condition_key, outcome_value in pipe_spec.outcomes.items():
                    if outcome_value in special_outcome_values:
                        new_outcomes[condition_key] = outcome_value
                    else:
                        stripped_outcome = strip(outcome_value)
                        if _should_strip_ref(outcome_value, stripped_outcome):
                            log.info(f"Stripped namespace from condition outcome: '{outcome_value}' → '{stripped_outcome}'")
                            new_outcomes[condition_key] = stripped_outcome
                        else:
                            new_outcomes[condition_key] = outcome_value
                pipe_spec.outcomes = new_outcomes

                if pipe_spec.default_outcome not in special_outcome_values:
                    stripped_default = strip(pipe_spec.default_outcome)
                    if _should_strip_ref(pipe_spec.default_outcome, stripped_default):
                        log.info(f"Stripped namespace from default_outcome: '{pipe_spec.default_outcome}' → '{stripped_default}'")
                        pipe_spec.default_outcome = stripped_default

        log.debug(f"After namespace stripping: main_pipe='{pipelex_bundle_spec.main_pipe}', pipe keys={list(pipelex_bundle_spec.pipe.keys())}")
        return pipelex_bundle_spec

    def _fix_bundle_validation_error(
        self,
        bundle_error: ValidateBundleError,
        pipelex_bundle_spec: PipelexBundleSpec,
        is_save_second_iteration_enabled: bool,
        output_dir: str | None = None,
    ) -> PipelexBundleSpec:
        fixed_pipes: list[PipeSpecUnion] = []
        added_concepts: list[str] = []
        # Handle pipe factory errors (e.g., missing output concepts)
        for factory_error in bundle_error.pipe_factory_errors:
            match factory_error.error_type:
                case PipeFactoryErrorType.UNKNOWN_CONCEPT:
                    # Fix unknown concept by adding a new concept that refines Text to the bundle
                    unknown_concept_code = factory_error.missing_concept_code
                    if not unknown_concept_code:
                        continue

                    # Create a simple concept that refines Text
                    new_concept = ConceptSpec(
                        the_concept_code=unknown_concept_code,
                        description=unknown_concept_code,
                        refines="Text",
                    )

                    # Add the concept to the bundle
                    if pipelex_bundle_spec.concept is None:
                        pipelex_bundle_spec.concept = {}

                    pipelex_bundle_spec.concept[unknown_concept_code] = new_concept
                    added_concepts.append(unknown_concept_code)
                    log.info(f"🔧 Added unknown concept '{unknown_concept_code}' (refines Text) to bundle for pipe '{factory_error.pipe_code}'")

                case PipeFactoryErrorType.UNKNOWN_FACTORY_ERROR:
                    continue

        # Handle pipe validation errors
        for val_error in bundle_error.pipe_validation_error_data:
            if not val_error.pipe_code or not pipelex_bundle_spec.pipe:
                continue

            pipe_spec = pipelex_bundle_spec.pipe.get(val_error.pipe_code)
            if not pipe_spec:
                continue

            match val_error.error_type:
                case PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH:
                    # Fix input stuff spec mismatch by updating the specific mismatched input(s)
                    # This applies to ALL pipe categories (operators and controllers)
                    if not PipeCategory.is_controller_by_str(category_str=pipe_spec.pipe_category):
                        continue

                    pipe = get_required_pipe(pipe_code=val_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()

                    # Start with existing inputs, we'll only override the mismatched ones
                    new_inputs: dict[str, str] = dict(pipe_spec.inputs) if pipe_spec.inputs else {}

                    # Get the variable names that have mismatches
                    mismatched_variables = val_error.variable_names or []

                    # Update only the mismatched inputs with the correct concept from needed_inputs
                    for variable_name in mismatched_variables:
                        for named_stuff_spec in needed_inputs.named_stuff_specs:
                            if named_stuff_spec.variable_name == variable_name:
                                old_value = new_inputs.get(variable_name, "NOT SET")
                                concept_code_with_multiplicity = format_concept_with_multiplicity(
                                    concept_code_or_string=named_stuff_spec.concept.code,
                                    multiplicity=named_stuff_spec.multiplicity,
                                )
                                new_inputs[variable_name] = concept_code_with_multiplicity
                                # TODO: return a structured report of what was done, let the caller decide if they want to print it or act on it
                                log.info(
                                    f"🔧 Fixed input requirement mismatch for pipe '{val_error.pipe_code}': input '{variable_name}' "
                                    f"changed from '{old_value}' → '{concept_code_with_multiplicity}'"
                                )
                                break

                    pipe_spec.inputs = new_inputs
                    fixed_pipes.append(pipe_spec)

                case PipeValidationErrorType.MISSING_INPUT_VARIABLE | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE:
                    # Fix input variables for PipeController ONLY by copying all requirements from needed_inputs
                    if not PipeCategory.is_controller_by_str(category_str=pipe_spec.pipe_category):
                        continue

                    pipe = get_required_pipe(pipe_code=val_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()
                    old_inputs = dict(pipe_spec.inputs) if pipe_spec.inputs else {}
                    fixed_inputs: dict[str, str] = {}
                    for named_stuff_spec in needed_inputs.named_stuff_specs:
                        concept_code_with_multiplicity = format_concept_with_multiplicity(
                            concept_code_or_string=named_stuff_spec.concept.code,
                            multiplicity=named_stuff_spec.multiplicity,
                        )
                        fixed_inputs[named_stuff_spec.variable_name] = concept_code_with_multiplicity

                    # Only apply fix if it actually changes something (avoid infinite loops)
                    if fixed_inputs != old_inputs:
                        pipe_spec.inputs = fixed_inputs
                        fixed_pipes.append(pipe_spec)
                        log.info(f"🔧 Fixed input variables for pipe '{val_error.pipe_code}': BEFORE={old_inputs} → AFTER={fixed_inputs}")
                    else:
                        variable_names_str = ", ".join(val_error.variable_names) if val_error.variable_names else "unknown"
                        log.warning(
                            f"⚠️ Cannot auto-fix {val_error.error_type.replace('_', ' ')} for pipe '{val_error.pipe_code}': needed_inputs() "
                            f"doesn't include the missing variable '{variable_names_str}'. "
                            f"This might be an intermediate variable that shouldn't be in inputs."
                        )

                case PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY:
                    # Fix output concept/multiplicity mismatch for PipeSequence by updating to match last step's output
                    if isinstance(pipe_spec, PipeSequenceSpec):
                        last_step = pipe_spec.steps[-1]
                        last_step_pipe_code = last_step.pipe_code

                        # Get the last step's pipe spec to retrieve its output
                        last_step_pipe_spec = pipelex_bundle_spec.pipe.get(last_step_pipe_code)
                        if not last_step_pipe_spec:
                            continue

                        old_output = pipe_spec.output
                        new_output = last_step_pipe_spec.output

                        # Set the sequence output to match the last step's output
                        pipe_spec.output = new_output
                        fixed_pipes.append(pipe_spec)
                        # TODO: return a structured report of what was done, let the caller decide if they want to print it or act on it
                        error_kind = "concept" if val_error.error_type == PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT else "multiplicity"
                        log.info(
                            f"🔧 Fixed output {error_kind} for pipe '{val_error.pipe_code}': output changed from '{old_output}' → "
                            f"'{new_output}' (matching last step '{last_step_pipe_code}')"
                        )

                    # Fix output concept for PipeCondition by checking mapped pipes' outputs
                    elif isinstance(pipe_spec, PipeConditionSpec):
                        # Get the PipeCondition instance to access pipe_dependencies()
                        pipe_condition = cast("PipeCondition", get_required_pipe(pipe_code=val_error.pipe_code))
                        mapped_pipe_codes = pipe_condition.pipe_dependencies()

                        if not mapped_pipe_codes:
                            # No mapped pipes (all special outcomes), any output is fine
                            continue

                        # Collect all unique output concept refs from mapped pipes
                        mapped_output_refs: set[str] = set()
                        for mapped_pipe_code in mapped_pipe_codes:
                            mapped_pipe = get_required_pipe(pipe_code=mapped_pipe_code)
                            mapped_output_refs.add(mapped_pipe.output.concept.concept_ref)

                        old_output = pipe_spec.output

                        # If all mapped pipes have same output, use that; otherwise use Anything
                        if len(mapped_output_refs) == 1:
                            new_output = next(iter(mapped_output_refs))
                        else:
                            new_output = "native.Anything"

                        pipe_spec.output = new_output
                        fixed_pipes.append(pipe_spec)
                        log.info(
                            f"🔧 Fixed output concept for PipeCondition '{val_error.pipe_code}': output changed from '{old_output}' → '{new_output}'"
                        )

                case PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX:
                    log.info(f"⚠️ Invalid pipe code syntax detected for pipe '{val_error.pipe_code}' — will be fixed by namespace stripping")
                    continue

                case (
                    PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                    | PipeValidationErrorType.IMG_GEN_INPUT_NOT_TEXT_COMPATIBLE
                    | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
                    | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                    | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                ):
                    continue

        # Handle dry run errors (e.g., PipeCompose multiplicity mismatches)
        if bundle_error.dry_run_error_message:
            dry_run_fixed_pipes = self._fix_dry_run_compose_multiplicity_mismatch(
                dry_run_error_message=bundle_error.dry_run_error_message,
                pipelex_bundle_spec=pipelex_bundle_spec,
            )
            fixed_pipes.extend(dry_run_fixed_pipes)

        # Reconstruct bundle if we made pipe changes
        if fixed_pipes:
            pipelex_bundle_spec = reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec=pipelex_bundle_spec, fixed_pipes=fixed_pipes)

        # Save second iteration if we made any changes (pipes or concepts)
        if (fixed_pipes or added_concepts) and is_save_second_iteration_enabled:
            try:
                mthds_content = MthdsFactory.make_mthds_content(blueprint=pipelex_bundle_spec.to_blueprint())
                second_iteration_path = get_incremental_file_path(
                    base_path=output_dir or "results/pipe-builder",
                    base_name="generated_pipeline_2nd_iteration",
                    extension="mthds",
                )
                save_text_to_path(text=mthds_content, path=str(second_iteration_path))
            except PipelexBundleSpecBlueprintError as exc:
                log.warning(f"Could not save second iteration MTHDS: {exc}")

        return pipelex_bundle_spec

    # --- Dry run multiplicity mismatch fix ---

    def _fix_dry_run_compose_multiplicity_mismatch(
        self,
        dry_run_error_message: str,
        pipelex_bundle_spec: PipelexBundleSpec,
    ) -> list[PipeSpecUnion]:
        """Fix multiplicity mismatches detected in PipeCompose dry run errors.

        Parses dry run error messages to identify cases where a PipeCompose field
        receives ListContent but the concept structure expects a scalar type (e.g., str).
        Fixes by adding [] to the pipe input and changing the concept structure field to list type.

        Args:
            dry_run_error_message: The error message from dry run failure
            pipelex_bundle_spec: The bundle spec to fix (modified in place for concept structure)

        Returns:
            List of fixed pipe specs to include in bundle reconstruction
        """
        fixed_pipes: list[PipeSpecUnion] = []

        if not pipelex_bundle_spec.pipe:
            return fixed_pipes

        # Extract compose pipe code and output concept from error message
        # Pattern: "In pipe 'compose_pipe_code' (output: OutputConcept)"
        pipe_match = re.search(r"In pipe '(\w+)' \(output: (\w+)\)", dry_run_error_message)
        if not pipe_match:
            return fixed_pipes

        compose_pipe_code = pipe_match.group(1)
        output_concept_code = pipe_match.group(2)

        # Find all multiplicity mismatches: "field_name: ListContent (expected str) <-- MISMATCH"
        mismatch_matches = re.findall(r"(\w+): ListContent \(expected (\w+)\) <-- MISMATCH", dry_run_error_message)
        if not mismatch_matches:
            return fixed_pipes

        # Get the PipeComposeSpec
        pipe_spec = pipelex_bundle_spec.pipe.get(compose_pipe_code)
        if not isinstance(pipe_spec, PipeComposeSpec):
            return fixed_pipes

        any_fix_applied = False
        for field_name, _expected_type in mismatch_matches:
            fix_applied = self._fix_single_multiplicity_mismatch(
                pipe_spec=pipe_spec,
                pipelex_bundle_spec=pipelex_bundle_spec,
                compose_pipe_code=compose_pipe_code,
                output_concept_code=output_concept_code,
                field_name=field_name,
            )
            if fix_applied:
                any_fix_applied = True

        if any_fix_applied:
            fixed_pipes.append(pipe_spec)

        return fixed_pipes

    def _fix_single_multiplicity_mismatch(
        self,
        pipe_spec: PipeComposeSpec,
        pipelex_bundle_spec: PipelexBundleSpec,
        compose_pipe_code: str,
        output_concept_code: str,
        field_name: str,
    ) -> bool:
        """Fix a single field's multiplicity mismatch in a PipeCompose.

        Adds [] to the pipe input concept ref and changes the concept structure
        field from its current scalar type to a list type.

        Returns:
            True if a fix was applied, False otherwise
        """
        # Find which input variable maps to this field via construct spec
        input_variable = self._find_input_for_construct_field(
            pipe_spec=pipe_spec,
            field_name=field_name,
        )
        if not input_variable:
            log.warning(f"Could not find input variable for field '{field_name}' in compose pipe '{compose_pipe_code}'")
            return False

        # Get the input's concept ref
        if not pipe_spec.inputs or input_variable not in pipe_spec.inputs:
            log.warning(f"Input variable '{input_variable}' not found in inputs of '{compose_pipe_code}'")
            return False

        old_input_concept = pipe_spec.inputs[input_variable]
        parse_result = parse_concept_with_multiplicity(old_input_concept)

        any_fix_applied = False

        # Fix 1: Add [] to the input concept (skip if already has multiplicity)
        if parse_result.multiplicity is None:
            new_input_concept = format_concept_with_multiplicity(
                concept_code_or_string=parse_result.concept_ref_or_code,
                multiplicity=True,
            )
            pipe_spec.inputs[input_variable] = new_input_concept
            any_fix_applied = True
            log.info(
                f"🔧 Fixed input multiplicity in '{compose_pipe_code}': "
                f"input '{input_variable}' changed from '{old_input_concept}' → '{new_input_concept}'"
            )

        # Fix 2: Update the output concept's structure field to LIST type
        concept_fixed = self._fix_concept_field_to_list(
            pipelex_bundle_spec=pipelex_bundle_spec,
            concept_code=output_concept_code,
            field_name=field_name,
            item_concept_ref=parse_result.concept_ref_or_code,
        )
        if concept_fixed:
            any_fix_applied = True
            log.info(f"🔧 Fixed concept field '{output_concept_code}.{field_name}' changed to list[concept[{parse_result.concept_ref_or_code}]]")

        return any_fix_applied

    def _find_input_for_construct_field(
        self,
        pipe_spec: PipeComposeSpec,
        field_name: str,
    ) -> str | None:
        """Find the input variable that maps to a construct field.

        Examines the construct_spec to find which input variable is used
        for a given field, looking for {"from": "variable_name"} patterns.

        Args:
            pipe_spec: The PipeComposeSpec to examine
            field_name: The field name to look up

        Returns:
            The input variable name, or None if not found
        """
        if not pipe_spec.construct_spec:
            return None

        field_spec = pipe_spec.construct_spec.get(field_name)
        if not field_spec:
            return None

        # Check if it's a {"from": "variable_name"} pattern
        if isinstance(field_spec, dict):
            from_dict = cast("dict[str, str]", field_spec)
            from_value = from_dict.get("from")
            if isinstance(from_value, str):
                # Handle dotted paths like "deal.customer" -> "deal"
                return get_root_from_dotted_path(from_value)

        return None

    def _fix_concept_field_to_list(
        self,
        pipelex_bundle_spec: PipelexBundleSpec,
        concept_code: str,
        field_name: str,
        item_concept_ref: str,
    ) -> bool:
        """Fix a concept's structure field type from scalar to list[concept[X]].

        Args:
            pipelex_bundle_spec: The bundle spec containing concepts
            concept_code: The concept code whose structure field to modify
            field_name: The field name within the concept's structure
            item_concept_ref: The concept reference for list items

        Returns:
            True if the fix was applied, False otherwise
        """
        if not pipelex_bundle_spec.concept:
            return False

        concept_spec = pipelex_bundle_spec.concept.get(concept_code)
        if not isinstance(concept_spec, ConceptSpec):
            return False

        if not concept_spec.structure:
            return False

        field_spec = concept_spec.structure.get(field_name)
        if not field_spec:
            return False

        # Skip if the field is already correctly typed as LIST with the right item_concept_ref
        if (
            field_spec.type == ConceptStructureSpecFieldType.LIST
            and field_spec.item_type == "concept"
            and field_spec.item_concept_ref == item_concept_ref
        ):
            return False

        # Update the field to LIST type and clear fields that are invalid for LIST
        field_spec.type = ConceptStructureSpecFieldType.LIST
        field_spec.item_type = "concept"
        field_spec.item_concept_ref = item_concept_ref
        field_spec.default_value = None
        field_spec.concept_ref = None
        field_spec.choices = None

        return True


def maybe_generate_manifest_for_output(output_dir: Path) -> Path | None:
    """Generate a METHODS.toml if the output directory contains multiple domains.

    Scans all .mthds files in the output directory, parses their headers to
    extract domain and main_pipe information, and generates a METHODS.toml
    if multiple distinct domains are found.

    Args:
        output_dir: Directory to scan for .mthds files

    Returns:
        Path to the generated METHODS.toml, or None if not generated
    """
    mthds_files = sorted(output_dir.rglob("*.mthds"))
    if not mthds_files:
        return None

    # Parse each bundle to extract domain and pipe info
    domain_pipes, domain_main_pipes, errors = scan_bundles_for_domain_info(mthds_files)
    for error in errors:
        log.warning(f"Could not parse {error}")

    # Only generate manifest when multiple domains are present
    if len(domain_pipes) < 2:
        return None

    # Build exports: include main_pipe and all pipes from each domain
    exports = build_domain_exports_from_scan(domain_pipes, domain_main_pipes)

    dir_name = output_dir.name.replace("-", "_").replace(" ", "_").lower()
    manifest = MethodsManifest(
        address=f"example.com/yourorg/{dir_name}",
        version="0.1.0",
        description=f"Package generated from {len(mthds_files)} .mthds file(s)",
        exports=exports,
    )

    manifest_path = output_dir / MANIFEST_FILENAME
    toml_content = serialize_manifest_to_toml(manifest)
    manifest_path.write_text(toml_content, encoding="utf-8")

    return manifest_path
