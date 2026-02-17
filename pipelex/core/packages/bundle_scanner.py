from collections.abc import Iterable
from pathlib import Path

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.packages.manifest import DomainExports


def scan_bundles_for_domain_info(
    mthds_files: Iterable[Path],
) -> tuple[dict[str, list[str]], dict[str, str], list[PipelexBundleBlueprint], list[str]]:
    """Scan .mthds files and extract domain/pipe information from their headers.

    Iterates over the given bundle files, parses each blueprint to collect
    which pipes belong to which domains, and which domain has a main_pipe.

    Args:
        mthds_files: Paths to .mthds files to scan

    Returns:
        A tuple of (domain_pipes, domain_main_pipes, blueprints, errors) where:
        - domain_pipes maps domain codes to their list of pipe codes
        - domain_main_pipes maps domain codes to their main_pipe code
        - blueprints is a list of successfully parsed PipelexBundleBlueprint objects
        - errors is a list of "{path}: {exc}" strings for files that failed parsing
    """
    domain_pipes: dict[str, list[str]] = {}
    domain_main_pipes: dict[str, str] = {}
    blueprints: list[PipelexBundleBlueprint] = []
    errors: list[str] = []

    for mthds_file in mthds_files:
        try:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
        except Exception as exc:
            errors.append(f"{mthds_file}: {exc}")
            continue

        blueprints.append(blueprint)

        domain = blueprint.domain
        if domain not in domain_pipes:
            domain_pipes[domain] = []

        if blueprint.pipe:
            for pipe_code in blueprint.pipe:
                domain_pipes[domain].append(pipe_code)

        if blueprint.main_pipe:
            existing = domain_main_pipes.get(domain)
            if existing and existing != blueprint.main_pipe:
                errors.append(f"Conflicting main_pipe for domain '{domain}': '{existing}' vs '{blueprint.main_pipe}' (from {mthds_file})")
            else:
                domain_main_pipes[domain] = blueprint.main_pipe

    return domain_pipes, domain_main_pipes, blueprints, errors


def build_domain_exports_from_scan(
    domain_pipes: dict[str, list[str]],
    domain_main_pipes: dict[str, str],
) -> list[DomainExports]:
    """Build a list of DomainExports from scan results, placing main_pipe first.

    For each domain (sorted alphabetically), creates a DomainExports entry with
    the main_pipe listed first (if present), followed by remaining pipes sorted
    alphabetically. Domains with zero exportable pipes are skipped.

    Args:
        domain_pipes: Mapping of domain codes to their pipe codes
        domain_main_pipes: Mapping of domain codes to their main_pipe code

    Returns:
        List of DomainExports with deterministic ordering
    """
    exports: list[DomainExports] = []
    for domain, pipe_codes in sorted(domain_pipes.items()):
        exported: list[str] = []
        main_pipe = domain_main_pipes.get(domain)
        if main_pipe and main_pipe not in exported:
            exported.append(main_pipe)
        for pipe_code in sorted(pipe_codes):
            if pipe_code not in exported:
                exported.append(pipe_code)
        if exported:
            exports.append(DomainExports(domain_path=domain, pipes=exported))
    return exports
